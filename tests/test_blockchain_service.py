import asyncio
from pathlib import Path

import pytest

from app.blockchain import BlockchainReceiptError, InMemoryFileRegistryGateway
from app.crypto import EncryptedFileEnvelope, generate_master_key
from app.db import connect_db, ensure_schema
from app.repository import FileRepository
from app.service import (
    BlockchainAuthorizationError,
    BlockchainIntegrityError,
    StorageService,
)
from app.storage import StorageReference, StoredObject
from tests.fakes import FakeTelegramStorage


OWNER = "0x0000000000000000000000000000000000000001"
RECIPIENT = "0x0000000000000000000000000000000000000002"
OTHER = "0x0000000000000000000000000000000000000003"


def test_blockchain_upload_encrypts_storage_and_records_pending_chain(tmp_path: Path):
    service, repository, storage, _gateway = _service(tmp_path)

    stored = asyncio.run(
        service.upload_bytes(
            filename="secret.txt",
            content=b"plain-secret",
            mime_type="text/plain",
            owner_wallet=OWNER,
        )
    )

    assert stored.status == "ready"
    assert stored.storage_state == "stored"
    assert stored.chain_state == "pending"
    assert stored.owner_wallet == OWNER
    assert stored.blockchain_file_id is not None
    assert stored.content_hash is not None
    assert stored.content_hash.startswith("0x")
    assert stored.wrapped_key is not None
    assert repository.get_file(stored.id).telegram_message_id == 1
    assert storage.objects[1].content != b"plain-secret"
    assert EncryptedFileEnvelope.from_bytes(storage.objects[1].content).plaintext_sha256 == stored.content_hash[2:]


def test_finalize_registration_confirms_only_successful_receipt(tmp_path: Path):
    service, _repository, _storage, _gateway = _service(tmp_path)
    stored = asyncio.run(
        service.upload_bytes(
            filename="proof.txt",
            content=b"chain-proof",
            mime_type="text/plain",
            owner_wallet=OWNER,
        )
    )

    confirmed = service.finalize_registration(file_id=stored.id, tx_hash="0xabc")

    assert confirmed.chain_state == "registered"
    assert confirmed.register_tx_hash == "0xabc"
    assert confirmed.register_block_number is not None


def test_failed_registration_marks_chain_failed(tmp_path: Path):
    gateway = FailingRegisterGateway()
    service, repository, _storage, _gateway = _service(tmp_path, gateway=gateway)
    stored = asyncio.run(
        service.upload_bytes(
            filename="proof.txt",
            content=b"chain-proof",
            mime_type="text/plain",
            owner_wallet=OWNER,
        )
    )

    with pytest.raises(BlockchainReceiptError):
        service.finalize_registration(file_id=stored.id, tx_hash="0xfailed")

    assert repository.get_file(stored.id).chain_state == "failed"


def test_confirmed_blockchain_download_requires_wallet_access(tmp_path: Path):
    service, _repository, _storage, gateway = _service(tmp_path)
    stored = asyncio.run(
        service.upload_bytes(
            filename="shared.txt",
            content=b"recipient-data",
            mime_type="text/plain",
            owner_wallet=OWNER,
        )
    )
    confirmed = service.finalize_registration(file_id=stored.id, tx_hash="0xabc")
    gateway.grant_access(file_id=confirmed.blockchain_file_id, owner_wallet=OWNER, recipient_wallet=RECIPIENT)

    downloaded = asyncio.run(service.download_file(stored.id, wallet_address=RECIPIENT))

    assert downloaded.filename == "shared.txt"
    assert downloaded.content == b"recipient-data"
    assert downloaded.mime_type == "text/plain"


def test_grant_revoke_and_status_report_contract_access(tmp_path: Path):
    service, _repository, _storage, _gateway = _service(tmp_path)
    stored = asyncio.run(
        service.upload_bytes(
            filename="access.txt",
            content=b"access-data",
            mime_type="text/plain",
            owner_wallet=OWNER,
        )
    )
    service.finalize_registration(file_id=stored.id, tx_hash="0xabc")

    _stored, grant_evidence = service.grant_access(
        file_id=stored.id,
        owner_wallet=OWNER,
        recipient_wallet=RECIPIENT,
        tx_hash="0xgrant",
    )
    granted_status = service.get_blockchain_status(file_id=stored.id, wallet_address=RECIPIENT)

    assert grant_evidence.status == 1
    assert granted_status["access_allowed"] is True

    _stored, revoke_evidence = service.revoke_access(
        file_id=stored.id,
        owner_wallet=OWNER,
        recipient_wallet=RECIPIENT,
        tx_hash="0xrevoke",
    )
    revoked_status = service.get_blockchain_status(file_id=stored.id, wallet_address=RECIPIENT)

    assert revoke_evidence.status == 1
    assert revoked_status["access_allowed"] is False


def test_confirmed_blockchain_download_denies_missing_or_unauthorized_wallet(tmp_path: Path):
    service, _repository, _storage, _gateway = _service(tmp_path)
    stored = asyncio.run(
        service.upload_bytes(
            filename="private.txt",
            content=b"owner-only",
            mime_type="text/plain",
            owner_wallet=OWNER,
        )
    )
    service.finalize_registration(file_id=stored.id, tx_hash="0xabc")

    with pytest.raises(BlockchainAuthorizationError):
        asyncio.run(service.download_file(stored.id))
    with pytest.raises(BlockchainAuthorizationError):
        asyncio.run(service.download_file(stored.id, wallet_address=OTHER))


def test_public_link_download_bypasses_wallet_but_keeps_decryption(tmp_path: Path):
    service, _repository, _storage, _gateway = _service(tmp_path)
    stored = asyncio.run(
        service.upload_bytes(
            filename="public.txt",
            content=b"public-link-content",
            mime_type="text/plain",
            owner_wallet=OWNER,
        )
    )
    service.finalize_registration(file_id=stored.id, tx_hash="0xabc")

    downloaded = asyncio.run(service.download_file(stored.id, public_link=True))

    assert downloaded.content == b"public-link-content"


def test_verify_integrity_uses_protected_download(tmp_path: Path):
    service, _repository, _storage, _gateway = _service(tmp_path)
    stored = asyncio.run(
        service.upload_bytes(
            filename="verify.txt",
            content=b"verify-content",
            mime_type="text/plain",
            owner_wallet=OWNER,
        )
    )
    service.finalize_registration(file_id=stored.id, tx_hash="0xabc")

    assert asyncio.run(service.verify_integrity(file_id=stored.id, wallet_address=OWNER)) is True


def test_tampered_encrypted_payload_fails_integrity_check(tmp_path: Path):
    service, _repository, storage, _gateway = _service(tmp_path)
    stored = asyncio.run(
        service.upload_bytes(
            filename="tamper.txt",
            content=b"do-not-change",
            mime_type="text/plain",
            owner_wallet=OWNER,
        )
    )
    service.finalize_registration(file_id=stored.id, tx_hash="0xabc")
    storage.objects[1] = StoredObject(
        filename=storage.objects[1].filename,
        content=storage.objects[1].content[:-1] + bytes([storage.objects[1].content[-1] ^ 1]),
        mime_type=storage.objects[1].mime_type,
        reference=storage.objects[1].reference,
    )

    with pytest.raises(BlockchainIntegrityError):
        asyncio.run(service.download_file(stored.id, wallet_address=OWNER))


def _service(tmp_path: Path, *, gateway=None):
    connection = connect_db(tmp_path / "files.db")
    ensure_schema(connection)
    repository = FileRepository(connection)
    storage = MemoryObjectStorage()
    gateway = gateway or InMemoryFileRegistryGateway()
    service = StorageService(
        repository,
        FakeTelegramStorage(message_id=99, file_id="unused"),
        channel_id=-10099,
        object_storage=storage,
        blockchain=gateway,
        master_key=generate_master_key(),
        blockchain_enabled=True,
    )
    return service, repository, storage, gateway


class MemoryObjectStorage:
    def __init__(self) -> None:
        self.next_message_id = 1
        self.objects: dict[int, StoredObject] = {}

    async def put(self, *, filename: str, content, mime_type: str | None) -> StorageReference:
        message_id = self.next_message_id
        self.next_message_id += 1
        if not isinstance(content, bytes):
            content = content.read()
        reference = StorageReference.telegram(
            channel_id=-10099,
            message_id=message_id,
            file_id=f"memory-{message_id}",
        )
        self.objects[message_id] = StoredObject(
            filename=filename,
            content=content,
            mime_type=mime_type,
            reference=reference,
        )
        return reference

    async def get(self, *, reference: StorageReference, filename: str, mime_type: str | None) -> StoredObject:
        return self.objects[reference.telegram_message_id]

    async def delete(self, *, reference: StorageReference) -> None:
        self.objects.pop(reference.telegram_message_id, None)


class FailingRegisterGateway(InMemoryFileRegistryGateway):
    def register_file(self, **kwargs):
        raise BlockchainReceiptError("receipt failed")
