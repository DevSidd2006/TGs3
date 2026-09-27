# README.md

## TGS3

TGS3 is a Telegram-backed file drive with a local-EVM blockchain ownership layer. File bytes stay off-chain in encrypted storage, while the smart contract records the file ID, content hash, owner wallet, access grants, and transaction evidence.

### Local setup

1. Create a virtual environment.
2. Install dependencies with `pip install -e .[dev]`.
3. Copy `.env.example` values into your shell environment.
4. Start the app with `uvicorn app.asgi:app --reload`.
5. Open `http://127.0.0.1:8000`.

### Required Telegram preparation

1. Create a private Telegram channel.
2. Use your Telegram API ID and API hash.
3. Set `TELEGRAM_CHANNEL_ID` to the target channel.
4. On first run, complete the Telethon login flow so the session file is created.

### MVP behavior

- Upload a file from the dashboard.
- Files are sent to Telegram and indexed in SQLite.
- Search filters the local SQLite index.
- Download pulls the file back through the backend.

### Blockchain demo mode

The academic blockchain mode uses a local Anvil chain and the `contracts/src/FileRegistry.sol` registry.

1. Install Foundry and start a local chain:

   ```bash
   bash scripts/start_local_chain.sh
   ```

2. In another terminal, deploy the registry:

   ```bash
   PRIVATE_KEY=<ANVIL_PRIVATE_KEY> bash scripts/deploy_contract.sh
   ```

3. Export the printed contract address and a generated 32-byte master key:

   ```bash
   export BLOCKCHAIN_ENABLED=1
   export BLOCKCHAIN_RPC_URL=http://127.0.0.1:8545
   export BLOCKCHAIN_CHAIN_ID=31337
   export BLOCKCHAIN_CONTRACT_ADDRESS=<DEPLOYED_CONTRACT_ADDRESS>
   export BLOCKCHAIN_ABI_PATH=contracts/out/FileRegistry.sol/FileRegistry.json
   export ENCRYPTION_MASTER_KEY=<urlsafe-base64-32-byte-key>
   ```

   Generate a master key with:

   ```bash
   .venv/bin/python -c "from app.crypto import encode_master_key, generate_master_key; print(encode_master_key(generate_master_key()))"
   ```

4. Import two Anvil accounts into a browser wallet and add the local network:

   - RPC URL: `http://127.0.0.1:8545`
   - Chain ID: `31337`
   - Currency symbol: `ETH`

5. Start the app and connect the owner wallet from the dashboard. Uploaded files are encrypted before Telegram storage and show blockchain evidence on the file detail page.

Demo story: upload as owner, register the file transaction, grant access to the second wallet, download as recipient, revoke access, and show that the recipient is denied while public links remain a separate off-chain access mode.

### Mobile

- Installable PWA at `/mobile` for phone access.
- Requires login when `TGS3_PASSWORD` is set.
- See `docs/HOSTING.md` for free internet access via Cloudflare Tunnel.
