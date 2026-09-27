#!/usr/bin/env bash
set -euo pipefail

if ! command -v anvil >/dev/null 2>&1; then
  echo "anvil is required. Install Foundry first: https://getfoundry.sh" >&2
  exit 1
fi

echo "Starting local TGS3 blockchain on http://127.0.0.1:8545"
echo "Use the printed Anvil accounts only for local development."
exec anvil --host 127.0.0.1 --port 8545 --chain-id 31337
