from io import BytesIO
from typing import BinaryIO

from app.repository import FileRepository
from app.telegram_bridge import DownloadedTelegramFile, TelegramStorage


class StorageService:
    def __init__(self, repository: FileRepository, telegram: TelegramStorage, channel_id: int) -> None:
        self._repository = repository
        self._telegram = telegram
        self._channel_id = channel_id

    async def upload_stream(self, *, filename: str, file_obj: BinaryIO, size_bytes: int, mime_type: str | None, folder_id: int | None = None):
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

    async def upload_bytes(self, *, filename: str, content: bytes, mime_type: str | None, folder_id: int | None = None):
        return await self.upload_stream(
            filename=filename,
            file_obj=BytesIO(content),
            size_bytes=len(content),
            mime_type=mime_type,
            folder_id=folder_id,
        )

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

