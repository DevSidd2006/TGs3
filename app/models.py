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
    share_token: str | None = None
    starred: bool = False
    deleted_at: str | None = None
    blockchain_file_id: str | None = None
    content_hash: str | None = None
    wrapped_key: str | None = None
    storage_state: str = "pending"
    chain_state: str = "not_submitted"
    register_tx_hash: str | None = None
    register_block_number: int | None = None
    owner_wallet: str | None = None


@dataclass(frozen=True)
class Folder:
    id: int
    name: str
    parent_id: int | None
    starred: bool = False
