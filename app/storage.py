from dataclasses import dataclass
from typing import BinaryIO, Protocol

from app.telegram_bridge import DownloadedTelegramFile, TelegramStorage


class StorageError(RuntimeError):
    pass


class StorageDeleteNotSupported(StorageError):
    pass


@dataclass(frozen=True)
class StorageReference:
    backend: str
    location: str
    metadata: dict[str, int | str | None]

    @classmethod
    def telegram(cls, *, channel_id: int, message_id: int, file_id: str) -> "StorageReference":
        return cls(
            backend="telegram",
            location=f"{channel_id}:{message_id}",
            metadata={
                "telegram_channel_id": channel_id,
                "telegram_message_id": message_id,
                "telegram_file_id": file_id,
            },
        )

    @property
    def telegram_channel_id(self) -> int:
        return _require_int(self.metadata, "telegram_channel_id")

    @property
    def telegram_message_id(self) -> int:
        return _require_int(self.metadata, "telegram_message_id")

    @property
    def telegram_file_id(self) -> str:
        return _require_str(self.metadata, "telegram_file_id")


@dataclass(frozen=True)
class StoredObject:
    filename: str
    content: bytes
    mime_type: str | None
    reference: StorageReference


class ObjectStorage(Protocol):
    async def put(self, *, filename: str, content: bytes | BinaryIO, mime_type: str | None) -> StorageReference:
        ...

    async def get(self, *, reference: StorageReference, filename: str, mime_type: str | None) -> StoredObject:
        ...

    async def delete(self, *, reference: StorageReference) -> None:
        ...


class TelegramObjectStorage:
    def __init__(self, telegram: TelegramStorage, channel_id: int) -> None:
        self._telegram = telegram
        self._channel_id = channel_id

    async def put(self, *, filename: str, content: bytes | BinaryIO, mime_type: str | None) -> StorageReference:
        uploaded = await self._telegram.upload(
            channel_id=self._channel_id,
            filename=filename,
            content=content,
            mime_type=mime_type,
        )
        return StorageReference.telegram(
            channel_id=self._channel_id,
            message_id=uploaded.message_id,
            file_id=uploaded.file_id,
        )

    async def get(self, *, reference: StorageReference, filename: str, mime_type: str | None) -> StoredObject:
        _validate_telegram_reference(reference)
        downloaded = await self._telegram.download(
            channel_id=reference.telegram_channel_id,
            message_id=reference.telegram_message_id,
            filename=filename,
            mime_type=mime_type,
        )
        return _downloaded_to_object(downloaded, reference)

    async def delete(self, *, reference: StorageReference) -> None:
        _validate_telegram_reference(reference)
        raise StorageDeleteNotSupported("Telegram storage deletion is not implemented")


def _downloaded_to_object(downloaded: DownloadedTelegramFile, reference: StorageReference) -> StoredObject:
    return StoredObject(
        filename=downloaded.filename,
        content=downloaded.content,
        mime_type=downloaded.mime_type,
        reference=reference,
    )


def _validate_telegram_reference(reference: StorageReference) -> None:
    if reference.backend != "telegram":
        raise StorageError(f"expected telegram storage reference, got {reference.backend!r}")
    _ = reference.telegram_channel_id
    _ = reference.telegram_message_id
    _ = reference.telegram_file_id


def _require_int(metadata: dict[str, int | str | None], key: str) -> int:
    value = metadata.get(key)
    if not isinstance(value, int):
        raise StorageError(f"storage reference metadata {key!r} must be an integer")
    return value


def _require_str(metadata: dict[str, int | str | None], key: str) -> str:
    value = metadata.get(key)
    if not isinstance(value, str) or not value:
        raise StorageError(f"storage reference metadata {key!r} must be a string")
    return value
