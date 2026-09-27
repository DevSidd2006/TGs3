// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import { FileRegistry } from "../src/FileRegistry.sol";

interface Vm {
    function expectRevert(bytes calldata revertData) external;
    function expectRevert(bytes4 revertData) external;
    function expectEmit(bool checkTopic1, bool checkTopic2, bool checkTopic3, bool checkData) external;
    function prank(address sender) external;
    function warp(uint256 newTimestamp) external;
}

contract Test {
    Vm internal constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    function assertTrue(bool value) internal pure {
        if (!value) revert("assertTrue failed");
    }

    function assertFalse(bool value) internal pure {
        if (value) revert("assertFalse failed");
    }

    function assertEq(bytes32 actual, bytes32 expected) internal pure {
        if (actual != expected) revert("assertEq bytes32 failed");
    }

    function assertEq(address actual, address expected) internal pure {
        if (actual != expected) revert("assertEq address failed");
    }

    function assertEq(uint64 actual, uint64 expected) internal pure {
        if (actual != expected) revert("assertEq uint64 failed");
    }
}

contract FileRegistryTest is Test {
    event FileRegistered(
        bytes32 indexed fileId, bytes32 indexed contentHash, address indexed owner, uint64 createdAt
    );
    event AccessGranted(bytes32 indexed fileId, address indexed owner, address indexed recipient);
    event AccessRevoked(bytes32 indexed fileId, address indexed owner, address indexed recipient);
    event FileDeleted(bytes32 indexed fileId, address indexed owner);

    FileRegistry private registry;

    address private constant OWNER = address(0xA11CE);
    address private constant RECIPIENT = address(0xB0B);
    address private constant STRANGER = address(0xE0E);
    bytes32 private constant FILE_ID = keccak256("tgs3:file:1");
    bytes32 private constant CONTENT_HASH = keccak256("plaintext bytes");

    function setUp() public {
        registry = new FileRegistry();
    }

    function testRegisterFileStoresOwnerHashTimestampAndEmits() public {
        vm.warp(42);
        vm.expectEmit(true, true, true, true);
        emit FileRegistered(FILE_ID, CONTENT_HASH, OWNER, 42);

        vm.prank(OWNER);
        registry.registerFile(FILE_ID, CONTENT_HASH);

        FileRegistry.FileRecord memory record = registry.getFile(FILE_ID);
        assertEq(record.contentHash, CONTENT_HASH);
        assertEq(record.owner, OWNER);
        assertEq(record.createdAt, uint64(42));
        assertTrue(record.active);
    }

    function testDuplicateRegistrationReverts() public {
        _register();

        vm.expectRevert(abi.encodeWithSelector(FileRegistry.FileAlreadyRegistered.selector, FILE_ID));
        vm.prank(OWNER);
        registry.registerFile(FILE_ID, keccak256("other hash"));
    }

    function testOwnerHasImplicitAccess() public {
        _register();

        assertTrue(registry.canAccess(FILE_ID, OWNER));
    }

    function testGrantAccessAllowsRecipientAndEmits() public {
        _register();

        vm.expectEmit(true, true, true, true);
        emit AccessGranted(FILE_ID, OWNER, RECIPIENT);

        vm.prank(OWNER);
        registry.grantAccess(FILE_ID, RECIPIENT);

        assertTrue(registry.canAccess(FILE_ID, RECIPIENT));
    }

    function testRevokeAccessDeniesRecipientAndEmits() public {
        _register();
        vm.prank(OWNER);
        registry.grantAccess(FILE_ID, RECIPIENT);

        vm.expectEmit(true, true, true, true);
        emit AccessRevoked(FILE_ID, OWNER, RECIPIENT);

        vm.prank(OWNER);
        registry.revokeAccess(FILE_ID, RECIPIENT);

        assertFalse(registry.canAccess(FILE_ID, RECIPIENT));
    }

    function testOnlyOwnerCanMutateAccessOrDelete() public {
        _register();

        vm.expectRevert(abi.encodeWithSelector(FileRegistry.Unauthorized.selector, FILE_ID, STRANGER));
        vm.prank(STRANGER);
        registry.grantAccess(FILE_ID, RECIPIENT);

        vm.expectRevert(abi.encodeWithSelector(FileRegistry.Unauthorized.selector, FILE_ID, STRANGER));
        vm.prank(STRANGER);
        registry.revokeAccess(FILE_ID, RECIPIENT);

        vm.expectRevert(abi.encodeWithSelector(FileRegistry.Unauthorized.selector, FILE_ID, STRANGER));
        vm.prank(STRANGER);
        registry.deleteFile(FILE_ID);
    }

    function testGrantAndRevokeRejectZeroRecipient() public {
        _register();

        vm.expectRevert(FileRegistry.ZeroRecipient.selector);
        vm.prank(OWNER);
        registry.grantAccess(FILE_ID, address(0));

        vm.expectRevert(FileRegistry.ZeroRecipient.selector);
        vm.prank(OWNER);
        registry.revokeAccess(FILE_ID, address(0));
    }

    function testDeleteMakesFileInactiveAndEmits() public {
        _register();
        vm.prank(OWNER);
        registry.grantAccess(FILE_ID, RECIPIENT);

        vm.expectEmit(true, true, false, true);
        emit FileDeleted(FILE_ID, OWNER);

        vm.prank(OWNER);
        registry.deleteFile(FILE_ID);

        FileRegistry.FileRecord memory record = registry.getFile(FILE_ID);
        assertEq(record.contentHash, CONTENT_HASH);
        assertEq(record.owner, OWNER);
        assertFalse(record.active);
        assertFalse(registry.canAccess(FILE_ID, OWNER));
        assertFalse(registry.canAccess(FILE_ID, RECIPIENT));
    }

    function testInactiveFileCannotBeMutatedOrReregistered() public {
        _register();
        vm.prank(OWNER);
        registry.deleteFile(FILE_ID);

        vm.expectRevert(abi.encodeWithSelector(FileRegistry.InactiveFile.selector, FILE_ID));
        vm.prank(OWNER);
        registry.grantAccess(FILE_ID, RECIPIENT);

        vm.expectRevert(abi.encodeWithSelector(FileRegistry.InactiveFile.selector, FILE_ID));
        vm.prank(OWNER);
        registry.revokeAccess(FILE_ID, RECIPIENT);

        vm.expectRevert(abi.encodeWithSelector(FileRegistry.InactiveFile.selector, FILE_ID));
        vm.prank(OWNER);
        registry.deleteFile(FILE_ID);

        vm.expectRevert(abi.encodeWithSelector(FileRegistry.FileAlreadyRegistered.selector, FILE_ID));
        vm.prank(OWNER);
        registry.registerFile(FILE_ID, CONTENT_HASH);
    }

    function testMissingFileReturnsClearInactiveRecordAndDeniesAccess() public {
        FileRegistry.FileRecord memory record = registry.getFile(FILE_ID);

        assertEq(record.contentHash, bytes32(0));
        assertEq(record.owner, address(0));
        assertEq(record.createdAt, uint64(0));
        assertFalse(record.active);
        assertFalse(registry.canAccess(FILE_ID, OWNER));
    }

    function testRegistrationRejectsZeroValues() public {
        vm.expectRevert(FileRegistry.ZeroFileId.selector);
        vm.prank(OWNER);
        registry.registerFile(bytes32(0), CONTENT_HASH);

        vm.expectRevert(FileRegistry.ZeroContentHash.selector);
        vm.prank(OWNER);
        registry.registerFile(FILE_ID, bytes32(0));
    }

    function _register() private {
        vm.prank(OWNER);
        registry.registerFile(FILE_ID, CONTENT_HASH);
    }
}
