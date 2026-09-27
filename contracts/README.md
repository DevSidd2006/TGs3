# TGS3 FileRegistry Contracts

This directory contains the local EVM registry used by the TGS3 blockchain file-storage
milestone. The contract stores file ownership, content fingerprints, active/deleted state, and
wallet access grants. File bytes, filenames, Telegram references, and encryption metadata stay
off-chain in the FastAPI application.

## Install Foundry

Install Foundry if `forge` and `anvil` are not already available:

```bash
curl -L https://foundry.paradigm.xyz | bash
foundryup
```

## Run Tests

From this directory:

```bash
forge test -vv
```

## Start a Local Chain

In one terminal:

```bash
bash ../scripts/start_local_chain.sh
```

Anvil prints funded local accounts and private keys. Use only those local development keys for
the academic demo.

## Deploy Locally

In another terminal:

```bash
PRIVATE_KEY=<ANVIL_PRIVATE_KEY> bash ../scripts/deploy_contract.sh
```

Record the deployed contract address in your local environment, for example:

```bash
BLOCKCHAIN_RPC_URL=http://127.0.0.1:8545
BLOCKCHAIN_CHAIN_ID=31337
BLOCKCHAIN_CONTRACT_ADDRESS=<DEPLOYED_CONTRACT_ADDRESS>
BLOCKCHAIN_ABI_PATH=contracts/out/FileRegistry.sol/FileRegistry.json
```

Do not commit generated deployment addresses as source-of-truth configuration. The ABI is produced
under `out/FileRegistry.sol/FileRegistry.json` after `forge build` or `forge test`; the backend can
load that artifact during local development.

## Browser Wallet Setup

For the two-wallet demo, import two different Anvil private keys into browser wallet accounts and
add the local network:

- RPC URL: `http://127.0.0.1:8545`
- Chain ID: `31337`
- Currency symbol: `ETH`

Use one account as the owner and another as the recipient. The intended demo flow is register,
grant access, recipient download, revoke access, and denied recipient download.
