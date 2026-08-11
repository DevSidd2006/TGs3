from dataclasses import dataclass
from typing import BinaryIO

from app.telegram_bridge import DownloadedTelegramFile, UploadedTelegramFile


@dataclass(frozen=True)
class UploadStub:
    filename: str
    content: bytes
    mime_type: str | None


class FakeTelegramStorage:
    def __init__(self, *, message_id: int, file_id: str, should_fail: bool = False) -> None:
        self._message_id = message_id
        self._file_id = file_id
        self._should_fail = should_fail
        self.uploads: list[UploadStub] = []

    async def upload(self, *, channel_id: int, filename: str, content: bytes | BinaryIO, mime_type: str | None) -> UploadedTelegramFile:
        if self._should_fail:
            raise RuntimeError("telegram upload failed")
        if hasattr(content, "read"):
            raw_content = content.read()
        else:
            raw_content = content
        self.uploads.append(UploadStub(filename=filename, content=raw_content, mime_type=mime_type))
        return UploadedTelegramFile(message_id=self._message_id, file_id=self._file_id)

    async def download(self, *, channel_id: int, message_id: int, filename: str, mime_type: str | None) -> DownloadedTelegramFile:
        return DownloadedTelegramFile(filename=filename, content=b"downloaded", mime_type=mime_type)

    async def list_channel_files(self, *, channel_id: int) -> list[dict]:
        return [
            {
                "telegram_channel_id": channel_id,
                "telegram_message_id": 101,
                "telegram_file_id": "file_101",
                "name": "synced_doc.pdf",
                "size_bytes": 2048,
                "mime_type": "application/pdf",
            }
        ]


class _AsyncMessages:
    def __init__(self, messages: list) -> None:
        self._iterator = iter(messages)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration:
            raise StopAsyncIteration


class FakeTelethonClient:
    def __init__(self, messages: list) -> None:
        self._messages = messages
        self.iter_kwargs: dict | None = None

    def iter_messages(self, entity, **kwargs):
        self.iter_kwargs = kwargs
        return _AsyncMessages(self._messages)


def make_file_message(message_id: int, *, name: str | None = None, size: int | None = None, mime: str | None = None, has_file: bool = True):
    class _File:
        def __init__(self, name: str | None, size: int | None, mime_type: str | None) -> None:
            self.id = f"file_{message_id}"
            self.name = name
            self.size = size
            self.mime_type = mime_type

    class _Message:
        id = message_id
        message = f"caption_{message_id}"

        def __init__(self) -> None:
            self.file = _File(name, size, mime) if has_file else None

    return _Message()

