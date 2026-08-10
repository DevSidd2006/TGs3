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

    def get_breadcrumb(self, folder_id: int):
        return self._repository.get_breadcrumb(folder_id)

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
