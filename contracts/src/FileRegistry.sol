// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title FileRegistry
/// @notice Records file ownership, content fingerprints, and wallet access grants.
contract FileRegistry {
    struct FileRecord {
        bytes32 contentHash;
        address owner;
        uint64 createdAt;
        bool active;
    }

    mapping(bytes32 fileId => FileRecord record) private files;
    mapping(bytes32 fileId => mapping(address account => bool allowed)) private access;

    event FileRegistered(
        bytes32 indexed fileId, bytes32 indexed contentHash, address indexed owner, uint64 createdAt
    );
    event AccessGranted(bytes32 indexed fileId, address indexed owner, address indexed recipient);
    event AccessRevoked(bytes32 indexed fileId, address indexed owner, address indexed recipient);
    event FileDeleted(bytes32 indexed fileId, address indexed owner);

    error ZeroFileId();
    error ZeroContentHash();
    error ZeroOwner();
    error ZeroRecipient();
    error FileAlreadyRegistered(bytes32 fileId);
    error FileNotFound(bytes32 fileId);
    error InactiveFile(bytes32 fileId);
    error Unauthorized(bytes32 fileId, address caller);

    function registerFile(bytes32 fileId, bytes32 contentHash) external {
        if (fileId == bytes32(0)) revert ZeroFileId();
        if (contentHash == bytes32(0)) revert ZeroContentHash();
        if (msg.sender == address(0)) revert ZeroOwner();
        if (files[fileId].owner != address(0)) revert FileAlreadyRegistered(fileId);

        uint64 createdAt = uint64(block.timestamp);
        files[fileId] = FileRecord({
            contentHash: contentHash,
            owner: msg.sender,
            createdAt: createdAt,
            active: true
        });

        emit FileRegistered(fileId, contentHash, msg.sender, createdAt);
    }

    function grantAccess(bytes32 fileId, address recipient) external {
        if (recipient == address(0)) revert ZeroRecipient();
        FileRecord memory record = _requireActiveOwner(fileId);

        access[fileId][recipient] = true;
        emit AccessGranted(fileId, record.owner, recipient);
    }

    function revokeAccess(bytes32 fileId, address recipient) external {
        if (recipient == address(0)) revert ZeroRecipient();
        FileRecord memory record = _requireActiveOwner(fileId);

        access[fileId][recipient] = false;
        emit AccessRevoked(fileId, record.owner, recipient);
    }

    function deleteFile(bytes32 fileId) external {
        FileRecord memory record = _requireActiveOwner(fileId);

        files[fileId].active = false;
        emit FileDeleted(fileId, record.owner);
    }

    function canAccess(bytes32 fileId, address account) external view returns (bool) {
        FileRecord memory record = files[fileId];
        if (!record.active || account == address(0)) return false;
        return account == record.owner || access[fileId][account];
    }

    function getFile(bytes32 fileId) external view returns (FileRecord memory) {
        return files[fileId];
    }

    function _requireActiveOwner(bytes32 fileId) private view returns (FileRecord memory record) {
        record = files[fileId];
        if (record.owner == address(0)) revert FileNotFound(fileId);
        if (!record.active) revert InactiveFile(fileId);
        if (record.owner != msg.sender) revert Unauthorized(fileId, msg.sender);
    }
}
