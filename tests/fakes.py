from dataclasses import dataclass

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

    async def upload(self, *, channel_id: int, filename: str, content: bytes, mime_type: str | None) -> UploadedTelegramFile:
        if self._should_fail:
            raise RuntimeError("telegram upload failed")
        self.uploads.append(UploadStub(filename=filename, content=content, mime_type=mime_type))
        return UploadedTelegramFile(message_id=self._message_id, file_id=self._file_id)

    async def download(self, *, channel_id: int, message_id: int, filename: str, mime_type: str | None) -> DownloadedTelegramFile:
        return DownloadedTelegramFile(filename=filename, content=b"downloaded", mime_type=mime_type)
