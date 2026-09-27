# Blockchain File Storage Design

## Purpose

TGS3 will become an EVM-based decentralized file ownership and access-control system with encrypted off-chain storage. The blockchain will be authoritative for file ownership, wallet permissions, and content fingerprints. File bytes will remain off-chain because large-file storage on-chain is impractical.

The first milestone is an academic, end-to-end demonstration on a local EVM chain: connect a wallet, upload and encrypt a file, register its hash, share it with another wallet, download it, revoke access, demonstrate denial, and verify integrity.

## Scope

Included:

- Local Anvil or Hardhat EVM development chain.
- Hybrid identity: existing TGS3 login plus a linked browser wallet.
- Direct user-signed transactions for registration, sharing, revocation, and deletion.
- Server-side encryption with a unique random data key per file.
- Data keys wrapped by a server master key and stored as wrapped metadata.
- A Solidity `FileRegistry` contract.
- Contract records containing opaque file ID, content hash, owner, creation time, and active status.
- Wallet-based access grants and revocations.
- Existing public share links retained as a separate, weaker access mode.
- Telegram as the first storage adapter for encrypted bytes.
- SQLite as an application index and transaction-status cache, never as the authority for ownership or access.
- UI evidence for wallet, contract, block, transaction, hash, owner, and access history.

Deferred:

- Permissionless storage-node discovery.
- Replication and proofs of storage.
- Token economics, rewards, penalties, and a storage marketplace.
- Client-side encryption and wallet-derived key custody.
- Gas relaying and sponsored transactions.
- Public-chain deployment.

## Architecture

The system has five layers:

1. **Web client**: existing TGS3 interface plus wallet connection, transaction prompts, blockchain status, and integrity verification.
2. **FastAPI application**: authentication, file metadata, encryption/decryption, blockchain reads, and download authorization.
3. **Blockchain adapter**: an isolated Web3 integration layer exposing contract operations to the service layer.
4. **Smart contract**: ownership, access control, active status, and event history.
5. **Storage adapter**: encrypted-byte storage, initially Telegram and replaceable by future decentralized storage nodes.

The trust boundary is:

```text
User wallet -> FileRegistry contract -> FastAPI blockchain adapter -> encrypted storage adapter
```

SQLite stores metadata and transaction references for fast queries. If SQLite conflicts with the contract, the contract wins.

## Contract

The registry stores one record per file:

```solidity
struct FileRecord {
    bytes32 contentHash;
    address owner;
    uint64 createdAt;
    bool active;
}
```

Required operations:

- `registerFile(fileId, contentHash)`
- `grantAccess(fileId, recipient)`
- `revokeAccess(fileId, recipient)`
- `deleteFile(fileId)`
- `canAccess(fileId, account)`
- `getFile(fileId)`

Only the recorded owner can grant, revoke, or delete. The contract emits `FileRegistered`, `AccessGranted`, `AccessRevoked`, and `FileDeleted` events.

## Data Flow

### Upload

1. Generate a unique random data-encryption key.
2. Encrypt the file before sending it to the storage adapter.
3. Store the encrypted bytes through Telegram.
4. Compute the hash of the original file.
5. Request a wallet-signed blockchain registration.
6. Persist the blockchain file ID, transaction hash, wrapped key, and storage reference in SQLite.

### Protected Download

1. Resolve the file through SQLite.
2. Query the contract for current access.
3. Retrieve encrypted bytes only when authorized.
4. Unwrap the file key with the server master key.
5. Decrypt the content.
6. Recompute and verify the content hash before returning it.

### Sharing

The owner signs a `grantAccess` or `revokeAccess` transaction. The application records the transaction and refreshes permission state from contract reads or events. A public link remains independent of this flow and is explicitly treated as weaker access control.

## State and Failure Handling

File records use these application states:

- `pending_storage`
- `stored_pending_chain`
- `confirmed`
- `chain_failed`
- `revoked`
- `deleted`

A protected download requires valid storage and confirmed blockchain registration. A failed transaction must never produce a confirmed blockchain-owned file. Blockchain and storage outages should return actionable errors and preserve recoverable pending state.

## Security

The server master key is supplied through deployment secrets and is never written to source code or the blockchain. Per-file data keys are random and wrapped before persistence. Filenames, sizes, MIME types, storage references, and encryption details remain off-chain. The on-chain hash is public and may reveal whether a known file exists; this is accepted for the first milestone.

## Testing and Academic Demonstration

Contract tests must cover ownership, grants, revocations, deletion, unauthorized mutation, and event emission. Application tests must cover encrypted upload, protected download, access denial, tamper detection, failed-chain states, unavailable backends, and continued public-link behavior.

The demonstration must show the connected wallet, contract address, file ID, content hash, transaction hash, block number, current owner, and access history. The primary live scenario is upload, register, grant, recipient download, revoke, denied recipient download, and integrity verification.

## Acceptance Criteria

The milestone is complete when a local two-wallet demonstration passes the full scenario, all contract and application tests pass, encrypted bytes are not readable directly from Telegram, and a changed stored payload fails content-hash verification.
