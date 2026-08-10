from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class StoredFile:
    id: int
    name: str
    size_bytes: int
    mime_type: str | None
    telegram_channel_id: int | None
    telegram_message_id: int | None
    telegram_file_id: str | None
    status: str
    uploaded_at: datetime
    folder_id: int | None = None


@dataclass(frozen=True)
class Folder:
    id: int
    name: str
    parent_id: int | None
