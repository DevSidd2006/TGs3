#!/usr/bin/env bash
set -euo pipefail

if ! command -v forge >/dev/null 2>&1; then
  echo "forge is required. Install Foundry first: https://getfoundry.sh" >&2
  exit 1
fi

if [[ -z "${PRIVATE_KEY:-}" ]]; then
  echo "Set PRIVATE_KEY to one of the local Anvil private keys." >&2
  exit 1
fi

RPC_URL="${BLOCKCHAIN_RPC_URL:-http://127.0.0.1:8545}"

cd "$(dirname "$0")/../contracts"
forge build
forge create \
  --rpc-url "$RPC_URL" \
  --private-key "$PRIVATE_KEY" \
  src/FileRegistry.sol:FileRegistry
