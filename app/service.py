from app.repository import FileRepository
from app.telegram_bridge import DownloadedTelegramFile, TelegramStorage


class StorageService:
    def __init__(self, repository: FileRepository, telegram: TelegramStorage, channel_id: int) -> None:
        self._repository = repository
        self._telegram = telegram
        self._channel_id = channel_id

    async def upload_bytes(self, *, filename: str, content: bytes, mime_type: str | None):
        stored = self._repository.create_uploading(name=filename, size_bytes=len(content), mime_type=mime_type)
        try:
            uploaded = await self._telegram.upload(
                channel_id=self._channel_id,
                filename=filename,
                content=content,
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

    def list_files(self):
        return self._repository.list_files()

    def search_files(self, query: str):
        return self._repository.search_files(query)

    def get_file(self, file_id: int):
        return self._repository.get_file(file_id)

    async def download_file(self, file_id: int) -> DownloadedTelegramFile:
        stored = self._repository.get_file(file_id)
        if stored is None or stored.telegram_message_id is None:
            raise FileNotFoundError(f"File {file_id} is unavailable")
        return await self._telegram.download(
            channel_id=self._channel_id,
            message_id=stored.telegram_message_id,
            filename=stored.name,
            mime_type=stored.mime_type,
        )
