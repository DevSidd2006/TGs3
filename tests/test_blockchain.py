import json
from pathlib import Path

import pytest

from app.blockchain import (
    BlockchainConfigurationError,
    BlockchainReceiptError,
    BlockchainRevertError,
    InMemoryFileRegistryGateway,
    Web3FileRegistryGateway,
    bytes32_hex,
    encode_bytes32,
    load_contract_abi,
    new_file_id,
    normalize_address,
)


FILE_ID = "0x" + "1" * 64
CONTENT_HASH = "0x" + "2" * 64
OWNER = "0x0000000000000000000000000000000000000001"
RECIPIENT = "0x0000000000000000000000000000000000000002"
OTHER = "0x0000000000000000000000000000000000000003"


def test_load_contract_abi_from_foundry_artifact(tmp_path: Path):
    artifact = tmp_path / "FileRegistry.json"
    artifact.write_text(json.dumps({"abi": [{"type": "function", "name": "getFile"}]}))

    assert load_contract_abi(artifact) == [{"type": "function", "name": "getFile"}]


def test_load_contract_abi_rejects_missing_abi_list(tmp_path: Path):
    artifact = tmp_path / "FileRegistry.json"
    artifact.write_text(json.dumps({"bytecode": "0x1234"}))

    with pytest.raises(BlockchainConfigurationError, match="abi list"):
        load_contract_abi(artifact)


def test_address_and_bytes32_normalization():
    assert normalize_address("0xABCDEFabcdefABCDEFabcdefABCDEFabcdefABCD") == "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
    assert bytes32_hex("1" * 64) == FILE_ID
    assert bytes32_hex(encode_bytes32(FILE_ID)) == FILE_ID
    assert new_file_id(b"seed") == "0x" + "19b25856e1c150ca834cffc8b59b23adbd0ec0389e58eb22b3b64768098d002b"

    with pytest.raises(ValueError, match="invalid wallet"):
        normalize_address("0x123")
    with pytest.raises(ValueError, match="32 bytes"):
        encode_bytes32("0x1234")


def test_in_memory_gateway_enforces_owner_grant_revoke_and_delete():
    gateway = InMemoryFileRegistryGateway()

    receipt = gateway.register_file(file_id=FILE_ID, content_hash=CONTENT_HASH, owner_wallet=OWNER)
    assert receipt.status == 1
    assert gateway.get_file(FILE_ID).owner == OWNER
    assert gateway.can_access(FILE_ID, OWNER) is True
    assert gateway.can_access(FILE_ID, RECIPIENT) is False

    gateway.grant_access(file_id=FILE_ID, owner_wallet=OWNER, recipient_wallet=RECIPIENT)
    assert gateway.can_access(FILE_ID, RECIPIENT) is True

    gateway.revoke_access(file_id=FILE_ID, owner_wallet=OWNER, recipient_wallet=RECIPIENT)
    assert gateway.can_access(FILE_ID, RECIPIENT) is False

    gateway.delete_file(file_id=FILE_ID, owner_wallet=OWNER)
    assert gateway.get_file(FILE_ID).active is False
    assert gateway.can_access(FILE_ID, OWNER) is False


def test_in_memory_gateway_rejects_unauthorized_mutation():
    gateway = InMemoryFileRegistryGateway()
    gateway.register_file(file_id=FILE_ID, content_hash=CONTENT_HASH, owner_wallet=OWNER)

    with pytest.raises(BlockchainRevertError, match="unauthorized"):
        gateway.grant_access(file_id=FILE_ID, owner_wallet=OTHER, recipient_wallet=RECIPIENT)


def test_web3_gateway_reads_contract_and_receipts(tmp_path: Path):
    web3 = FakeWeb3(chain_id=31337)
    abi_path = _artifact(tmp_path)
    gateway = Web3FileRegistryGateway(
        rpc_url="http://127.0.0.1:8545",
        contract_address="0x0000000000000000000000000000000000000009",
        chain_id=31337,
        abi_path=abi_path,
        web3=web3,
    )

    record = gateway.get_file(FILE_ID)
    assert record.file_id == FILE_ID
    assert record.content_hash == CONTENT_HASH
    assert record.owner == OWNER
    assert record.active is True
    assert gateway.can_access(FILE_ID, OWNER) is True

    evidence = gateway.register_file(
        file_id=FILE_ID,
        content_hash=CONTENT_HASH,
        owner_wallet=OWNER,
        tx_hash="0xabc",
    )
    assert evidence.tx_hash == "0xabc"
    assert evidence.block_number == 55
    assert evidence.status == 1


def test_web3_gateway_rejects_chain_id_mismatch(tmp_path: Path):
    with pytest.raises(BlockchainConfigurationError, match="chain id"):
        Web3FileRegistryGateway(
            rpc_url="http://127.0.0.1:8545",
            contract_address="0x0000000000000000000000000000000000000009",
            chain_id=1,
            abi_path=_artifact(tmp_path),
            web3=FakeWeb3(chain_id=31337),
        )


def test_web3_gateway_rejects_failed_receipt(tmp_path: Path):
    web3 = FakeWeb3(chain_id=31337, receipt={"status": 0, "blockNumber": 56})
    gateway = Web3FileRegistryGateway(
        rpc_url="http://127.0.0.1:8545",
        contract_address="0x0000000000000000000000000000000000000009",
        chain_id=31337,
        abi_path=_artifact(tmp_path),
        web3=web3,
    )

    with pytest.raises(BlockchainReceiptError, match="failed"):
        gateway.register_file(
            file_id=FILE_ID,
            content_hash=CONTENT_HASH,
            owner_wallet=OWNER,
            tx_hash="0xabc",
        )


def test_web3_gateway_requires_browser_signed_transaction_hash(tmp_path: Path):
    gateway = Web3FileRegistryGateway(
        rpc_url="http://127.0.0.1:8545",
        contract_address="0x0000000000000000000000000000000000000009",
        chain_id=31337,
        abi_path=_artifact(tmp_path),
        web3=FakeWeb3(chain_id=31337),
    )

    with pytest.raises(BlockchainReceiptError, match="transaction hash"):
        gateway.register_file(file_id=FILE_ID, content_hash=CONTENT_HASH, owner_wallet=OWNER)


def test_web3_gateway_maps_contract_call_errors(tmp_path: Path):
    web3 = FakeWeb3(chain_id=31337, call_error=RuntimeError("execution reverted"))
    gateway = Web3FileRegistryGateway(
        rpc_url="http://127.0.0.1:8545",
        contract_address="0x0000000000000000000000000000000000000009",
        chain_id=31337,
        abi_path=_artifact(tmp_path),
        web3=web3,
    )

    with pytest.raises(BlockchainRevertError, match="execution reverted"):
        gateway.get_file(FILE_ID)


def _artifact(tmp_path: Path) -> Path:
    artifact = tmp_path / "FileRegistry.json"
    artifact.write_text(json.dumps({"abi": [{"type": "function", "name": "getFile"}]}))
    return artifact


class FakeWeb3:
    def __init__(self, *, chain_id: int, receipt=None, call_error=None):
        self.eth = FakeEth(chain_id=chain_id, receipt=receipt, call_error=call_error)

    def to_checksum_address(self, address: str) -> str:
        return normalize_address(address)


class FakeEth:
    def __init__(self, *, chain_id: int, receipt=None, call_error=None):
        self.chain_id = chain_id
        self.receipt = receipt or {"status": 1, "blockNumber": 55}
        self.call_error = call_error

    def contract(self, *, address: str, abi):
        return FakeContract(address=address, abi=abi, call_error=self.call_error)

    def wait_for_transaction_receipt(self, tx_hash: str):
        return self.receipt


class FakeContract:
    def __init__(self, *, address: str, abi, call_error=None):
        self.address = address
        self.abi = abi
        self.functions = FakeFunctions(call_error=call_error)


class FakeFunctions:
    def __init__(self, *, call_error=None):
        self.call_error = call_error

    def getFile(self, file_id: bytes):
        assert file_id == encode_bytes32(FILE_ID)
        return FakeCall((encode_bytes32(CONTENT_HASH), OWNER, 44, True), error=self.call_error)

    def canAccess(self, file_id: bytes, account: str):
        assert file_id == encode_bytes32(FILE_ID)
        assert account == OWNER
        return FakeCall(True, error=self.call_error)


class FakeCall:
    def __init__(self, value, *, error=None):
        self.value = value
        self.error = error

    def call(self):
        if self.error is not None:
            raise self.error
        return self.value
