# Blockchain File Storage Implementation Plan

> **For agentic workers:** Implement this plan task-by-task with tests first. Do not commit or push changes unless the user explicitly requests it.

**Goal:** Add a local-EVM blockchain ownership and wallet-access layer to TGS3 while encrypting file bytes before Telegram storage and preserving existing public links.

**Architecture:** Keep FastAPI and SQLite as the application layer, add a Solidity `FileRegistry` contract and an isolated blockchain adapter, and add a storage encryption service that wraps per-file keys with a deployment master key. SQLite indexes blockchain IDs and transaction state, but contract reads authorize protected downloads.

**Tech Stack:** Python 3.11+, FastAPI, SQLite, pytest, Solidity, Foundry/Anvil, `web3.py`, browser wallet provider via injected EIP-1193 JavaScript API.

---

## File Map

Create `contracts/src/FileRegistry.sol` for ownership, access mappings, state transitions, and events.

Create `contracts/test/FileRegistry.t.sol` for Foundry contract tests and `contracts/foundry.toml` for the local contract toolchain.

Create `app/blockchain.py` for contract reads, transaction metadata, ABI loading, and a small interface that can be replaced by a fake in Python tests.

Create `app/crypto.py` for streaming encryption, decryption, hashing, and master-key wrapping. Use authenticated encryption and never persist raw per-file keys.

Create `app/storage.py` for a storage adapter protocol so Telegram remains the initial backend and future node backends can be added without changing blockchain logic.

Modify `app/config.py` to load blockchain RPC/contract settings and the encryption master key.

Modify `app/db.py` to add a forward-compatible schema migration for blockchain IDs, content hash, wrapped key, blockchain transaction fields, and storage state.

Modify `app/models.py` and `app/repository.py` to expose and persist the new metadata.

Modify `app/service.py` to encrypt before upload, register the file after storage, check contract permissions before protected downloads, and verify the decrypted content hash.

Modify `app/main.py` to inject the blockchain and encryption services, add wallet-aware JSON endpoints, and expose serialized blockchain evidence.

Modify `app/static/app.js`, `app/static/styles.css`, `app/templates/index.html`, and `app/templates/file_detail.html` for wallet connection, transaction prompts, blockchain status, sharing, revocation, and integrity verification.

Create `tests/test_crypto.py`, `tests/test_blockchain.py`, and `tests/test_blockchain_service.py`. Extend existing route and service tests with fake blockchain and encrypted-storage behavior.

Modify `.env.example`, `README.md`, and add `contracts/README.md` with local-chain setup and the academic demonstration steps.

## Task 1: Add the Contract Toolchain and Registry

**Files:**
- Create: `contracts/foundry.toml`
- Create: `contracts/src/FileRegistry.sol`
- Create: `contracts/test/FileRegistry.t.sol`
- Create: `contracts/README.md`

- [ ] **Step 1: Define the contract API and failure rules.**

Use `bytes32 fileId` and `bytes32 contentHash`. Store `FileRecord { bytes32 contentHash; address owner; uint64 createdAt; bool active; }`, plus `mapping(bytes32 => mapping(address => bool)) access` and `mapping(bytes32 => FileRecord) files`.

Require registration to reject an existing active file ID and zero owner. Require grants and revocations to be owner-only and reject the zero recipient. Require reads for missing files to return a clear inactive record. Deletion sets `active = false` and emits `FileDeleted`; it does not erase history.

- [ ] **Step 2: Write failing Solidity tests.**

Cover registration, duplicate rejection, owner-only mutation, grant, revoke, delete, inactive access denial, event emission, and the owner’s implicit access.

- [ ] **Step 3: Implement the minimal contract.**

Implement `registerFile`, `grantAccess`, `revokeAccess`, `deleteFile`, `canAccess`, and `getFile`, with custom errors and the four specified events: `FileRegistered`, `AccessGranted`, `AccessRevoked`, and `FileDeleted`.

- [ ] **Step 4: Run contract tests.**

Run `cd contracts && forge test -vv`. Expected: all registry tests pass.

- [ ] **Step 5: Document local deployment.**

Document starting Anvil, deploying with Foundry, capturing the deployed contract address and ABI, and importing two Anvil accounts into browser wallets. Do not commit the generated deployment address as a source-of-truth configuration.

## Task 2: Add Encryption, Hashing, and Storage Boundaries

**Files:**
- Create: `app/crypto.py`
- Create: `app/storage.py`
- Create: `tests/test_crypto.py`
- Create: `tests/test_storage.py`
- Modify: `app/telegram_bridge.py`

- [ ] **Step 1: Write crypto tests.**

Test that encrypting and decrypting bytes round-trips, a changed ciphertext fails authentication, a changed plaintext hash is detected, each encryption produces a different data key/nonce, and wrapping/unwrapping with the configured master key recovers only the original data key.

- [ ] **Step 2: Implement authenticated encryption.**

Use a vetted library already available or add `cryptography` as a dependency. Generate a random per-file data key and nonce. Store a versioned envelope containing algorithm version, nonce, ciphertext, and wrapped data key. Use SHA-256 for the original plaintext content hash. Reject invalid envelope versions and authentication failures.

- [ ] **Step 3: Add the storage protocol.**

Define a protocol with `upload`, `download`, and `delete` operations using a storage reference object. Adapt the existing `TelegramStorage` implementation to satisfy it without changing its public behavior. Keep the Telegram message reference out of blockchain records.

- [ ] **Step 4: Run focused tests.**

Run `pytest tests/test_crypto.py tests/test_storage.py -q`. Expected: all focused tests pass before service integration begins.

## Task 3: Add Database and Configuration State

**Files:**
- Modify: `app/config.py`
- Modify: `app/db.py`
- Modify: `app/models.py`
- Modify: `app/repository.py`
- Create: `tests/test_blockchain_repository.py`
- Modify: `.env.example`

- [ ] **Step 1: Define configuration fields.**

Add `BLOCKCHAIN_RPC_URL`, `BLOCKCHAIN_CONTRACT_ADDRESS`, `BLOCKCHAIN_CHAIN_ID`, `ENCRYPTION_MASTER_KEY`, and an explicit feature flag such as `BLOCKCHAIN_ENABLED`. Fail startup with a clear configuration error when blockchain mode is enabled without RPC, contract, or master-key configuration.

- [ ] **Step 2: Add a schema migration.**

Extend `files` with nullable fields for `file_id`/opaque blockchain ID, `content_hash`, `wrapped_key`, `storage_state`, `chain_state`, `register_tx_hash`, `register_block_number`, and `owner_wallet`. Preserve existing databases by applying `ALTER TABLE` only for missing columns.

- [ ] **Step 3: Extend the model and repository.**

Expose the new fields on `StoredFile`. Add repository methods to mark encrypted storage, mark pending registration, mark confirmed registration, mark failed registration, save transaction evidence, and query by opaque blockchain file ID. Ensure existing Telegram sync rows remain usable with null blockchain fields.

- [ ] **Step 4: Test migration and state transitions.**

Verify a fresh database and an existing legacy database both initialize, and verify each state transition preserves the Telegram reference and file metadata.

- [ ] **Step 5: Run the repository suite.**

Run `pytest tests/test_repository.py tests/test_blockchain_repository.py -q`. Expected: legacy repository tests and new state tests pass.

## Task 4: Implement the Blockchain Adapter

**Files:**
- Create: `app/blockchain.py`
- Create: `tests/test_blockchain.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Define the adapter interface and fake.**

Expose typed operations for `get_file`, `can_access`, `register_file`, `grant_access`, `revoke_access`, and `delete_file`. Return transaction hash, block number, and receipt status for mutations. Implement an in-memory fake that enforces owner and recipient behavior for service tests.

- [ ] **Step 2: Write adapter tests.**

Test ABI loading, address normalization, bytes32 encoding, successful reads, receipt failure handling, and conversion of contract reverts into application exceptions. Test that a failed receipt never returns confirmed state.

- [ ] **Step 3: Implement the Web3 adapter.**

Load the compiled ABI from a configured artifact path, connect to `BLOCKCHAIN_RPC_URL`, validate chain ID, checksum the contract address, and use contract calls for reads. For writes, accept a client-provided transaction hash/receipt path or a server-side test signer only for local development; production mutations must be initiated by the browser wallet.

- [ ] **Step 4: Run adapter tests.**

Run `pytest tests/test_blockchain.py -q`. Expected: all adapter tests pass without requiring a live node.

## Task 5: Integrate Encrypted Upload and Verified Download

**Files:**
- Modify: `app/service.py`
- Modify: `app/main.py`
- Create: `tests/test_blockchain_service.py`
- Modify: `tests/test_service.py`

- [ ] **Step 1: Write upload and download integration tests.**

Using fake blockchain and storage implementations, test that upload encrypts before storage, stores a wrapped key, computes a plaintext SHA-256 hash, creates `stored_pending_chain`, registers with the connected owner wallet, and becomes `confirmed` only after a successful receipt. Test failed storage, failed chain registration, unauthorized download, successful owner/recipient download, tampered payload rejection, and public-link compatibility.

- [ ] **Step 2: Implement encrypted upload.**

Update `StorageService.upload_stream` to create the application row, encrypt the incoming content, upload the encrypted envelope through the storage protocol, persist storage metadata and wrapped key, and return a pending blockchain record when blockchain mode is active. Keep the existing non-blockchain path working when the feature flag is disabled.

- [ ] **Step 3: Implement registration finalization.**

Add a service method that accepts the wallet address, opaque file ID, content hash, transaction hash, and receipt result from the browser. Validate the file is in `stored_pending_chain`, validate the receipt succeeded, and mark it confirmed with block evidence.

- [ ] **Step 4: Implement protected download.**

Require a wallet address for confirmed blockchain files, call `can_access`, download only after authorization, decrypt with the wrapped key, recompute the plaintext hash, and reject mismatches with a 409 integrity error. Leave public-link downloads on their existing path and label them as off-chain access.

- [ ] **Step 5: Run service tests.**

Run `pytest tests/test_service.py tests/test_blockchain_service.py -q`. Expected: existing behavior remains green and the new end-to-end service tests pass.

## Task 6: Add Wallet and Blockchain API Routes

**Files:**
- Modify: `app/main.py`
- Modify: `app/templates/file_detail.html`
- Modify: `app/templates/index.html`
- Create or modify: `app/static/app.js`
- Modify: `app/static/styles.css`
- Create: `tests/test_blockchain_web.py`

- [ ] **Step 1: Define route contracts.**

Add authenticated routes for blockchain status, registration finalization, grant, revoke, and integrity verification. Return normalized JSON containing `file_id`, `owner_wallet`, `content_hash`, `chain_state`, transaction hash, block number, and access status. Never accept a private key from the browser or server request body.

- [ ] **Step 2: Write route tests.**

Test authentication, missing files, invalid wallet addresses, owner-only grant/revoke behavior, successful receipt finalization, failed receipt handling, and response serialization. Test that public-share routes remain available without wallet access.

- [ ] **Step 3: Implement route handlers.**

Keep route handlers thin: authenticate, validate payloads, call service methods, map domain errors to 400/403/404/409 responses, and serialize transaction evidence. Add wallet address normalization and strict validation before passing addresses to the contract adapter.

- [ ] **Step 4: Implement browser-wallet interaction.**

Use the injected EIP-1193 provider to request accounts and chain ID, switch to the configured local chain, call the contract for registration/grant/revoke, wait for receipts, and send only receipt metadata to FastAPI. Show pending, confirmed, failed, and revoked states with transaction links or hashes.

- [ ] **Step 5: Add academic evidence to the UI.**

On file detail, display contract address, opaque file ID, hash, owner, current connected wallet, registration transaction, block number, and access events. Add an integrity verification action that calls the server and displays pass/fail without exposing encryption keys.

- [ ] **Step 6: Run web tests and the full suite.**

Run `pytest tests/test_blockchain_web.py tests/test_web.py tests/test_mobile_routes.py -q`, then `pytest -q`. Expected: all route, mobile, and regression tests pass.

## Task 7: Reproducible Local Demonstration and Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/HOSTING.md`
- Modify: `.env.example`
- Modify: `contracts/README.md`
- Create: `scripts/start_local_chain.sh`
- Create: `scripts/deploy_contract.sh`
- Create: `tests/test_demo_configuration.py`

- [ ] **Step 1: Add local-chain scripts.**

Create scripts that start Anvil on a documented port, deploy the contract, print the contract address and test accounts, and write only local generated artifacts under an ignored directory. Make scripts fail clearly when `anvil`, `forge`, or the configured Python environment is missing.

- [ ] **Step 2: Document the academic demo.**

Document environment setup, local chain startup, contract deployment, browser wallet setup, application startup, two-wallet flow, expected transaction evidence, integrity-tampering demonstration, and the distinction between blockchain authorization and Telegram storage.

- [ ] **Step 3: Test configuration behavior.**

Verify disabled blockchain mode preserves current startup behavior and enabled mode rejects missing required values with actionable errors.

- [ ] **Step 4: Run the final verification.**

Run `pytest -q`, then perform the documented two-wallet local-chain scenario manually. Confirm upload, registration, grant, recipient download, revoke, denied download, and tamper detection. Leave all work uncommitted unless the user explicitly asks for a commit.

## Plan Self-Review

- Contract requirements map to Task 1.
- Encryption, key wrapping, plaintext hashing, and storage abstraction map to Task 2.
- Configuration, SQLite state, and legacy compatibility map to Task 3.
- Blockchain reads, writes, receipts, and errors map to Task 4.
- Upload, protected download, revoke behavior, and integrity verification map to Task 5.
- Wallet UX and academic evidence map to Task 6.
- Reproducible local-node setup and acceptance scenario map to Task 7.
- No task requires public-chain deployment, token economics, storage-node incentives, or client-side encryption.
- No placeholder markers or commit steps are included; all verification commands and expected outcomes are specified.
