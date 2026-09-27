from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Protocol


ZERO_HASH = "0x" + "0" * 64
ZERO_ADDRESS = "0x" + "0" * 40
ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


class BlockchainError(Exception):
    """Base class for blockchain adapter failures."""


class BlockchainConfigurationError(BlockchainError):
    pass


class BlockchainRevertError(BlockchainError):
    pass


class BlockchainReceiptError(BlockchainError):
    pass


@dataclass(frozen=True)
class ChainFileRecord:
    file_id: str
    content_hash: str
    owner: str
    created_at: int
    active: bool


@dataclass(frozen=True)
class TransactionEvidence:
    tx_hash: str
    block_number: int | None
    status: int


class FileRegistryGateway(Protocol):
    def get_file(self, file_id: str | bytes) -> ChainFileRecord:
        ...

    def can_access(self, file_id: str | bytes, account: str) -> bool:
        ...

    def register_file(
        self,
        *,
        file_id: str | bytes,
        content_hash: str | bytes,
        owner_wallet: str,
        tx_hash: str | None = None,
    ) -> TransactionEvidence:
        ...

    def grant_access(
        self,
        *,
        file_id: str | bytes,
        owner_wallet: str,
        recipient_wallet: str,
        tx_hash: str | None = None,
    ) -> TransactionEvidence:
        ...

    def revoke_access(
        self,
        *,
        file_id: str | bytes,
        owner_wallet: str,
        recipient_wallet: str,
        tx_hash: str | None = None,
    ) -> TransactionEvidence:
        ...

    def delete_file(
        self,
        *,
        file_id: str | bytes,
        owner_wallet: str,
        tx_hash: str | None = None,
    ) -> TransactionEvidence:
        ...


def normalize_address(address: str) -> str:
    if not ADDRESS_RE.fullmatch(address):
        raise ValueError(f"invalid wallet address: {address}")
    return address.lower()


def encode_bytes32(value: str | bytes) -> bytes:
    if isinstance(value, bytes):
        if len(value) != 32:
            raise ValueError("bytes32 values must be exactly 32 bytes")
        return value
    candidate = value[2:] if value.startswith("0x") else value
    if len(candidate) != 64:
        raise ValueError("bytes32 hex values must be 32 bytes")
    try:
        return bytes.fromhex(candidate)
    except ValueError as exc:
        raise ValueError("bytes32 values must be hex encoded") from exc


def bytes32_hex(value: str | bytes) -> str:
    return "0x" + encode_bytes32(value).hex()


def new_file_id(seed: bytes) -> str:
    return "0x" + hashlib.sha256(seed).hexdigest()


def load_contract_abi(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise BlockchainConfigurationError(f"contract ABI artifact not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise BlockchainConfigurationError(f"contract ABI artifact is invalid JSON: {path}") from exc
    abi = payload.get("abi") if isinstance(payload, dict) else payload
    if not isinstance(abi, list):
        raise BlockchainConfigurationError(f"contract ABI artifact does not contain an abi list: {path}")
    return abi


class Web3FileRegistryGateway:
    def __init__(
        self,
        *,
        rpc_url: str,
        contract_address: str,
        chain_id: int,
        abi_path: Path,
        web3: Any | None = None,
    ) -> None:
        self._web3 = web3 if web3 is not None else self._build_web3(rpc_url)
        observed_chain_id = self._web3.eth.chain_id
        if observed_chain_id != chain_id:
            raise BlockchainConfigurationError(
                f"connected chain id {observed_chain_id} does not match configured {chain_id}"
            )
        checksum_address = self._checksum_address(contract_address)
        self._contract = self._web3.eth.contract(address=checksum_address, abi=load_contract_abi(abi_path))

    @staticmethod
    def _build_web3(rpc_url: str) -> Any:
        try:
            from web3 import Web3
        except ImportError as exc:
            raise BlockchainConfigurationError("web3.py is required when blockchain mode is enabled") from exc
        return Web3(Web3.HTTPProvider(rpc_url))

    def _checksum_address(self, address: str) -> str:
        normalize_address(address)
        checksum = getattr(self._web3, "to_checksum_address", None) or getattr(self._web3, "toChecksumAddress", None)
        return checksum(address) if checksum else address

    def get_file(self, file_id: str | bytes) -> ChainFileRecord:
        file_id_bytes = encode_bytes32(file_id)
        try:
            result = self._contract.functions.getFile(file_id_bytes).call()
        except Exception as exc:  # web3 raises provider-specific exception classes.
            raise BlockchainRevertError(str(exc)) from exc
        content_hash, owner, created_at, active = self._coerce_file_record(result)
        return ChainFileRecord(
            file_id=bytes32_hex(file_id_bytes),
            content_hash=bytes32_hex(content_hash) if content_hash else ZERO_HASH,
            owner=normalize_address(owner) if owner != ZERO_ADDRESS else ZERO_ADDRESS,
            created_at=int(created_at),
            active=bool(active),
        )

    def can_access(self, file_id: str | bytes, account: str) -> bool:
        file_id_bytes = encode_bytes32(file_id)
        account_address = self._checksum_address(account)
        try:
            return bool(self._contract.functions.canAccess(file_id_bytes, account_address).call())
        except Exception as exc:
            raise BlockchainRevertError(str(exc)) from exc

    def register_file(
        self,
        *,
        file_id: str | bytes,
        content_hash: str | bytes,
        owner_wallet: str,
        tx_hash: str | None = None,
    ) -> TransactionEvidence:
        encode_bytes32(file_id)
        encode_bytes32(content_hash)
        self._checksum_address(owner_wallet)
        return self._confirmed_receipt(tx_hash)

    def grant_access(
        self,
        *,
        file_id: str | bytes,
        owner_wallet: str,
        recipient_wallet: str,
        tx_hash: str | None = None,
    ) -> TransactionEvidence:
        encode_bytes32(file_id)
        self._checksum_address(owner_wallet)
        self._checksum_address(recipient_wallet)
        return self._confirmed_receipt(tx_hash)

    def revoke_access(
        self,
        *,
        file_id: str | bytes,
        owner_wallet: str,
        recipient_wallet: str,
        tx_hash: str | None = None,
    ) -> TransactionEvidence:
        encode_bytes32(file_id)
        self._checksum_address(owner_wallet)
        self._checksum_address(recipient_wallet)
        return self._confirmed_receipt(tx_hash)

    def delete_file(
        self,
        *,
        file_id: str | bytes,
        owner_wallet: str,
        tx_hash: str | None = None,
    ) -> TransactionEvidence:
        encode_bytes32(file_id)
        self._checksum_address(owner_wallet)
        return self._confirmed_receipt(tx_hash)

    def _confirmed_receipt(self, tx_hash: str | None) -> TransactionEvidence:
        if not tx_hash:
            raise BlockchainReceiptError("transaction hash is required for browser-signed mutations")
        try:
            receipt = self._web3.eth.wait_for_transaction_receipt(tx_hash)
        except Exception as exc:
            raise BlockchainReceiptError(str(exc)) from exc
        status = int(_receipt_get(receipt, "status", 0))
        block_number = _receipt_get(receipt, "blockNumber", None)
        if status != 1:
            raise BlockchainReceiptError(f"transaction {tx_hash} failed with status {status}")
        return TransactionEvidence(tx_hash=tx_hash, block_number=block_number, status=status)

    @staticmethod
    def _coerce_file_record(result: Any) -> tuple[bytes | str, str, int, bool]:
        if isinstance(result, dict):
            return result["contentHash"], result["owner"], result["createdAt"], result["active"]
        return result[0], result[1], result[2], result[3]


class InMemoryFileRegistryGateway:
    def __init__(self) -> None:
        self._files: dict[str, ChainFileRecord] = {}
        self._access: dict[str, set[str]] = {}
        self._block_number = 1

    def get_file(self, file_id: str | bytes) -> ChainFileRecord:
        normalized_id = bytes32_hex(file_id)
        return self._files.get(
            normalized_id,
            ChainFileRecord(
                file_id=normalized_id,
                content_hash=ZERO_HASH,
                owner=ZERO_ADDRESS,
                created_at=0,
                active=False,
            ),
        )

    def can_access(self, file_id: str | bytes, account: str) -> bool:
        record = self.get_file(file_id)
        account_address = normalize_address(account)
        return record.active and (account_address == record.owner or account_address in self._access[record.file_id])

    def register_file(
        self,
        *,
        file_id: str | bytes,
        content_hash: str | bytes,
        owner_wallet: str,
        tx_hash: str | None = None,
    ) -> TransactionEvidence:
        normalized_id = bytes32_hex(file_id)
        normalized_hash = bytes32_hex(content_hash)
        owner = normalize_address(owner_wallet)
        if normalized_id == ZERO_HASH:
            raise BlockchainRevertError("file id must not be zero")
        if normalized_hash == ZERO_HASH:
            raise BlockchainRevertError("content hash must not be zero")
        if self._files.get(normalized_id, self.get_file(normalized_id)).owner != ZERO_ADDRESS:
            raise BlockchainRevertError(f"file already registered: {normalized_id}")
        self._files[normalized_id] = ChainFileRecord(
            file_id=normalized_id,
            content_hash=normalized_hash,
            owner=owner,
            created_at=self._block_number,
            active=True,
        )
        self._access[normalized_id] = set()
        return self._next_receipt(tx_hash)

    def grant_access(
        self,
        *,
        file_id: str | bytes,
        owner_wallet: str,
        recipient_wallet: str,
        tx_hash: str | None = None,
    ) -> TransactionEvidence:
        record = self._require_active_owner(file_id, owner_wallet)
        recipient = normalize_address(recipient_wallet)
        if recipient == ZERO_ADDRESS:
            raise BlockchainRevertError("recipient must not be zero")
        self._access[record.file_id].add(recipient)
        return self._next_receipt(tx_hash)

    def revoke_access(
        self,
        *,
        file_id: str | bytes,
        owner_wallet: str,
        recipient_wallet: str,
        tx_hash: str | None = None,
    ) -> TransactionEvidence:
        record = self._require_active_owner(file_id, owner_wallet)
        recipient = normalize_address(recipient_wallet)
        if recipient == ZERO_ADDRESS:
            raise BlockchainRevertError("recipient must not be zero")
        self._access[record.file_id].discard(recipient)
        return self._next_receipt(tx_hash)

    def delete_file(
        self,
        *,
        file_id: str | bytes,
        owner_wallet: str,
        tx_hash: str | None = None,
    ) -> TransactionEvidence:
        record = self._require_active_owner(file_id, owner_wallet)
        self._files[record.file_id] = ChainFileRecord(
            file_id=record.file_id,
            content_hash=record.content_hash,
            owner=record.owner,
            created_at=record.created_at,
            active=False,
        )
        return self._next_receipt(tx_hash)

    def _require_active_owner(self, file_id: str | bytes, owner_wallet: str) -> ChainFileRecord:
        record = self.get_file(file_id)
        owner = normalize_address(owner_wallet)
        if record.owner == ZERO_ADDRESS:
            raise BlockchainRevertError(f"file not found: {record.file_id}")
        if not record.active:
            raise BlockchainRevertError(f"inactive file: {record.file_id}")
        if record.owner != owner:
            raise BlockchainRevertError(f"unauthorized owner: {owner}")
        return record

    def _next_receipt(self, tx_hash: str | None) -> TransactionEvidence:
        self._block_number += 1
        return TransactionEvidence(
            tx_hash=tx_hash or f"0x{self._block_number:064x}",
            block_number=self._block_number,
            status=1,
        )


def _receipt_get(receipt: Any, key: str, default: Any) -> Any:
    if isinstance(receipt, dict):
        return receipt.get(key, default)
    return getattr(receipt, key, default)
