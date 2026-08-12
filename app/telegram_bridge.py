from dataclasses import dataclass
from io import BytesIO
from typing import Protocol

from telethon import TelegramClient


@dataclass(frozen=True)
class UploadedTelegramFile:
    message_id: int
    file_id: str


@dataclass(frozen=True)
class DownloadedTelegramFile:
    filename: str
    content: bytes
    mime_type: str | None


class TelegramStorage(Protocol):
    async def upload(self, *, channel_id: int, filename: str, content: bytes, mime_type: str | None) -> UploadedTelegramFile:
        ...

    async def download(self, *, channel_id: int, message_id: int, filename: str, mime_type: str | None) -> DownloadedTelegramFile:
        ...


class TelethonStorage:
    def __init__(self, client: TelegramClient) -> None:
        self._client = client

    async def upload(self, *, channel_id: int, filename: str, content: bytes, mime_type: str | None) -> UploadedTelegramFile:
        file_buffer = BytesIO(content)
        file_buffer.name = filename
        message = await self._client.send_file(
            entity=channel_id,
            file=file_buffer,
            caption=filename,
            force_document=True,
        )
        return UploadedTelegramFile(message_id=message.id, file_id=str(message.file.id))

    async def download(self, *, channel_id: int, message_id: int, filename: str, mime_type: str | None) -> DownloadedTelegramFile:
        message = await self._client.get_messages(channel_id, ids=message_id)
        if message is None or message.file is None:
            raise FileNotFoundError(f"Telegram file not found for message {message_id}")
        content = await self._client.download_media(message, file=bytes)
        if content is None:
            raise FileNotFoundError(f"Telegram content empty for message {message_id}")
        return DownloadedTelegramFile(filename=filename, content=content, mime_type=mime_type)

    async def list_channel_files(self, *, channel_id: int, limit: int = 200) -> list[dict]:
        files: list[dict] = []
        async for message in self._client.iter_messages(channel_id, limit=limit):
            if message.file is None:
                continue
            try:
                file_id = str(message.file.id)
            except Exception:
                file_id = f"msg_{message.id}"
            files.append(
                {
                    "telegram_channel_id": channel_id,
                    "telegram_message_id": message.id,
                    "telegram_file_id": file_id,
                    "name": message.file.name or message.message or f"file_{message.id}",
                    "size_bytes": message.file.size,
                    "mime_type": message.file.mime_type,
                }
            )
        return files
