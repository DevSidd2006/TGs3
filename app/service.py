from io import BytesIO
import base64
import secrets
from typing import BinaryIO

from app.blockchain import (
    BlockchainError,
    FileRegistryGateway,
    new_file_id,
)
from app.crypto import (
    CryptoError,
    EncryptedFileEnvelope,
    decrypt_file,
    encrypt_file,
    sha256_hexdigest,
)
from app.repository import FileRepository
from app.storage import ObjectStorage, StorageReference, TelegramObjectStorage
from app.telegram_bridge import DownloadedTelegramFile, TelegramStorage


class BlockchainAuthorizationError(PermissionError):
    pass


class BlockchainIntegrityError(ValueError):
    pass


class StorageService:
    def __init__(
        self,
        repository: FileRepository,
        telegram: TelegramStorage,
        channel_id: int,
        *,
        object_storage: ObjectStorage | None = None,
        blockchain: FileRegistryGateway | None = None,
        master_key: bytes | None = None,
        blockchain_enabled: bool = False,
    ) -> None:
        self._repository = repository
        self._telegram = telegram
        self._channel_id = channel_id
        self._object_storage = object_storage or TelegramObjectStorage(telegram, channel_id)
        self._blockchain = blockchain
        self._master_key = master_key
        self._blockchain_enabled = blockchain_enabled

    async def upload_stream(self, *, filename: str, file_obj: BinaryIO, size_bytes: int, mime_type: str | None, folder_id: int | None = None, owner_wallet: str | None = None):
        if self._blockchain_enabled:
            return await self._upload_encrypted(
                filename=filename,
                file_obj=file_obj,
                size_bytes=size_bytes,
                mime_type=mime_type,
                folder_id=folder_id,
                owner_wallet=owner_wallet,
            )
        stored = self._repository.create_uploading(name=filename, size_bytes=size_bytes, mime_type=mime_type)
        if folder_id is not None:
            self._repository.move_file(file_id=stored.id, folder_id=folder_id)
        try:
            uploaded = await self._telegram.upload(
                channel_id=self._channel_id,
                filename=filename,
                content=file_obj,
                mime_type=mime_type,
            )
            self._repository.mark_ready(
                file_id=stored.id,
                telegram_channel_id=self._channel_id,
                telegram_message_id=uploaded.message_id,
                telegram_file_id=uploaded.file_id,
            )
        except Exception:
            self._repository.mark_failed(stored.id)
            raise
        return self._repository.get_file(stored.id)

    async def _upload_encrypted(self, *, filename: str, file_obj: BinaryIO, size_bytes: int, mime_type: str | None, folder_id: int | None, owner_wallet: str | None):
        if self._master_key is None or self._blockchain is None:
            raise RuntimeError("blockchain storage is not configured")
        if not owner_wallet:
            raise BlockchainAuthorizationError("owner wallet is required for blockchain uploads")

        stored = self._repository.create_uploading(name=filename, size_bytes=size_bytes, mime_type=mime_type)
        if folder_id is not None:
            self._repository.move_file(file_id=stored.id, folder_id=folder_id)

        try:
            content = file_obj.read()
            envelope = encrypt_file(content, self._master_key)
            reference = await self._object_storage.put(
                filename=f"{filename}.tgs3.enc",
                content=envelope.to_bytes(),
                mime_type="application/octet-stream",
            )
            self._repository.mark_ready(
                file_id=stored.id,
                telegram_channel_id=reference.telegram_channel_id,
                telegram_message_id=reference.telegram_message_id,
                telegram_file_id=reference.telegram_file_id,
            )
            content_hash = "0x" + envelope.plaintext_sha256
            self._repository.mark_storage_ready(
                file_id=stored.id,
                content_hash=content_hash,
                wrapped_key=_wrapped_key_token(envelope),
            )
            blockchain_file_id = new_file_id(secrets.token_bytes(32) + stored.id.to_bytes(8, "big"))
            self._repository.mark_chain_pending(
                file_id=stored.id,
                blockchain_file_id=blockchain_file_id,
                owner_wallet=owner_wallet,
            )
        except Exception:
            self._repository.mark_storage_failed(stored.id)
            self._repository.mark_failed(stored.id)
            raise
        return self._repository.get_file(stored.id)

    async def upload_bytes(self, *, filename: str, content: bytes, mime_type: str | None, folder_id: int | None = None, owner_wallet: str | None = None):
        return await self.upload_stream(
            filename=filename,
            file_obj=BytesIO(content),
            size_bytes=len(content),
            mime_type=mime_type,
            folder_id=folder_id,
            owner_wallet=owner_wallet,
        )

    def finalize_registration(self, *, file_id: int, tx_hash: str):
        if self._blockchain is None:
            raise RuntimeError("blockchain storage is not configured")
        stored = self._repository.get_file(file_id)
        if stored is None:
            raise FileNotFoundError(f"File {file_id} not found")
        if not stored.blockchain_file_id or not stored.content_hash or not stored.owner_wallet:
            raise ValueError(f"File {file_id} is not ready for blockchain registration")
        try:
            evidence = self._blockchain.register_file(
                file_id=stored.blockchain_file_id,
                content_hash=stored.content_hash,
                owner_wallet=stored.owner_wallet,
                tx_hash=tx_hash,
            )
        except BlockchainError:
            self._repository.mark_chain_failed(file_id)
            raise
        return self._repository.mark_chain_registered(
            file_id=file_id,
            blockchain_file_id=stored.blockchain_file_id,
            owner_wallet=stored.owner_wallet,
            register_tx_hash=evidence.tx_hash,
            register_block_number=evidence.block_number or 0,
        )

    def grant_access(self, *, file_id: int, owner_wallet: str, recipient_wallet: str, tx_hash: str):
        stored = self._require_registered_blockchain_file(file_id)
        assert self._blockchain is not None
        evidence = self._blockchain.grant_access(
            file_id=stored.blockchain_file_id,
            owner_wallet=owner_wallet,
            recipient_wallet=recipient_wallet,
            tx_hash=tx_hash,
        )
        return stored, evidence

    def revoke_access(self, *, file_id: int, owner_wallet: str, recipient_wallet: str, tx_hash: str):
        stored = self._require_registered_blockchain_file(file_id)
        assert self._blockchain is not None
        evidence = self._blockchain.revoke_access(
            file_id=stored.blockchain_file_id,
            owner_wallet=owner_wallet,
            recipient_wallet=recipient_wallet,
            tx_hash=tx_hash,
        )
        return stored, evidence

    def get_blockchain_status(self, *, file_id: int, wallet_address: str | None = None) -> dict:
        stored = self._repository.get_file(file_id)
        if stored is None:
            raise FileNotFoundError(f"File {file_id} not found")
        access_allowed = None
        if wallet_address and stored.blockchain_file_id and self._blockchain is not None:
            access_allowed = self._blockchain.can_access(stored.blockchain_file_id, wallet_address)
        return {
            "file": stored,
            "access_allowed": access_allowed,
        }

    async def verify_integrity(self, *, file_id: int, wallet_address: str | None = None, public_link: bool = False) -> bool:
        await self.download_file(file_id, wallet_address=wallet_address, public_link=public_link)
        return True

    def list_files(self, folder_id: int | None = None):
        return self._repository.list_files(folder_id)

    def create_folder(self, *, name: str, parent_id: int | None):
        return self._repository.create_folder(name=name, parent_id=parent_id)

    def rename_folder(self, folder_id: int, name: str):
        return self._repository.rename_folder(folder_id, name)

    def delete_folder(self, folder_id: int) -> None:
        return self._repository.delete_folder(folder_id)

    def get_folder(self, folder_id: int):
        return self._repository.get_folder(folder_id)

    def list_folders(self):
        return self._repository.list_folders()

    def move_file(self, *, file_id: int, folder_id: int | None):
        return self._repository.move_file(file_id=file_id, folder_id=folder_id)

    def rename_file(self, file_id: int, name: str):
        return self._repository.rename_file(file_id, name)

    def get_breadcrumb(self, folder_id: int):
        return self._repository.get_breadcrumb(folder_id)

    def search_files(self, query: str):
        return self._repository.search_files(query)

    def get_file(self, file_id: int):
        return self._repository.get_file(file_id)

    def toggle_share(self, file_id: int, enable: bool):
        self._repository.set_share_token(file_id, enable)
        stored = self._repository.get_file(file_id)
        if stored is None:
            raise FileNotFoundError(f"File {file_id} not found")
        return stored

    def get_shared_file(self, token: str):
        return self._repository.get_file_by_share_token(token)

    def list_recent(self, limit: int = 50):
        return self._repository.list_recent_files(limit)

    def list_starred(self) -> dict:
        return {
            "files": self._repository.list_starred_files(),
            "folders": self._repository.list_starred_folders(),
        }

    def list_shared(self):
        return self._repository.list_shared_files()

    def list_trash(self):
        return self._repository.list_trashed_files()

    def star_file(self, file_id: int, starred: bool):
        stored = self._repository.set_file_starred(file_id, starred)
        if stored is None:
            raise FileNotFoundError(f"File {file_id} not found")
        return stored

    def star_folder(self, folder_id: int, starred: bool):
        return self._repository.set_folder_starred(folder_id, starred)

    def trash_file(self, file_id: int):
        stored = self._repository.trash_file(file_id)
        if stored is None:
            raise FileNotFoundError(f"File {file_id} not found")
        return stored

    def restore_file(self, file_id: int):
        stored = self._repository.restore_file(file_id)
        if stored is None:
            raise FileNotFoundError(f"File {file_id} not found")
        return stored

    def purge_file(self, file_id: int) -> None:
        self._repository.purge_file(file_id)

    def empty_trash(self) -> int:
        return self._repository.purge_all_trashed()

    def _require_registered_blockchain_file(self, file_id: int):
        if self._blockchain is None:
            raise RuntimeError("blockchain storage is not configured")
        stored = self._repository.get_file(file_id)
        if stored is None:
            raise FileNotFoundError(f"File {file_id} not found")
        if not stored.blockchain_file_id or stored.chain_state != "registered":
            raise ValueError(f"File {file_id} is not registered on-chain")
        return stored

    async def download_file(self, file_id: int, *, wallet_address: str | None = None, public_link: bool = False) -> DownloadedTelegramFile:
        stored = self._repository.get_file(file_id)
        if stored is None or stored.telegram_message_id is None:
            raise FileNotFoundError(f"File {file_id} is unavailable")
        if self._is_encrypted_blockchain_file(stored):
            if not public_link:
                if stored.chain_state != "registered":
                    raise BlockchainAuthorizationError(f"File {file_id} is not confirmed on-chain")
                if not wallet_address:
                    raise BlockchainAuthorizationError("wallet address is required")
                if self._blockchain is None or not self._blockchain.can_access(stored.blockchain_file_id, wallet_address):
                    raise BlockchainAuthorizationError("wallet is not authorized for this file")
            return await self._download_encrypted(stored)
        return await self._telegram.download(
            channel_id=self._channel_id,
            message_id=stored.telegram_message_id,
            filename=stored.name,
            mime_type=stored.mime_type,
        )

    async def _download_encrypted(self, stored) -> DownloadedTelegramFile:
        if self._master_key is None:
            raise RuntimeError("encrypted storage is not configured")
        reference = StorageReference.telegram(
            channel_id=stored.telegram_channel_id,
            message_id=stored.telegram_message_id,
            file_id=stored.telegram_file_id,
        )
        encrypted = await self._object_storage.get(
            reference=reference,
            filename=stored.name,
            mime_type=stored.mime_type,
        )
        try:
            envelope = EncryptedFileEnvelope.from_bytes(encrypted.content)
            content = decrypt_file(envelope, self._master_key)
        except CryptoError as exc:
            raise BlockchainIntegrityError("encrypted file integrity check failed") from exc
        expected_hash = stored.content_hash
        actual_hash = "0x" + sha256_hexdigest(content)
        if expected_hash and actual_hash != expected_hash:
            raise BlockchainIntegrityError("decrypted file hash does not match blockchain record")
        return DownloadedTelegramFile(filename=stored.name, content=content, mime_type=stored.mime_type)

    async def sync_from_channel(self) -> int:
        if not hasattr(self._telegram, "list_channel_files"):
            return 0
        try:
            files = await self._telegram.list_channel_files(channel_id=self._channel_id)
        except Exception:
            return 0
        count = 0
        for item in files:
            self._repository.upsert_synced_file(
                name=item["name"],
                size_bytes=item["size_bytes"],
                mime_type=item["mime_type"],
                telegram_channel_id=item["telegram_channel_id"],
                telegram_message_id=item["telegram_message_id"],
                telegram_file_id=item["telegram_file_id"],
            )
            count += 1
        return count

    @staticmethod
    def _is_encrypted_blockchain_file(stored) -> bool:
        return bool(stored.content_hash and stored.wrapped_key and stored.storage_state == "stored")


def _wrapped_key_token(envelope: EncryptedFileEnvelope) -> str:
    return base64.urlsafe_b64encode(envelope.key_nonce + envelope.wrapped_key).decode("ascii")
