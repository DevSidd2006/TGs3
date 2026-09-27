import asyncio

import pytest

from app.storage import StorageDeleteNotSupported, StorageError, StorageReference, TelegramObjectStorage
from tests.fakes import FakeTelegramStorage


def test_telegram_object_storage_put_returns_storage_reference():
    telegram = FakeTelegramStorage(message_id=42, file_id="tg-42")
    storage = TelegramObjectStorage(telegram, channel_id=-10042)

    reference = asyncio.run(
        storage.put(
            filename="encrypted.bin",
            content=b"ciphertext",
            mime_type="application/octet-stream",
        )
    )

    assert reference.backend == "telegram"
    assert reference.location == "-10042:42"
    assert reference.telegram_channel_id == -10042
    assert reference.telegram_message_id == 42
    assert reference.telegram_file_id == "tg-42"
    assert telegram.uploads[0].filename == "encrypted.bin"
    assert telegram.uploads[0].content == b"ciphertext"


def test_telegram_object_storage_get_downloads_by_reference():
    telegram = FakeTelegramStorage(message_id=42, file_id="tg-42")
    storage = TelegramObjectStorage(telegram, channel_id=-10042)
    reference = StorageReference.telegram(channel_id=-10042, message_id=42, file_id="tg-42")

    stored = asyncio.run(storage.get(reference=reference, filename="plain.txt", mime_type="text/plain"))

    assert stored.filename == "plain.txt"
    assert stored.content == b"downloaded"
    assert stored.mime_type == "text/plain"
    assert stored.reference == reference


def test_telegram_object_storage_rejects_wrong_backend_reference():
    storage = TelegramObjectStorage(FakeTelegramStorage(message_id=42, file_id="tg-42"), channel_id=-10042)
    reference = StorageReference(backend="ipfs", location="cid", metadata={})

    with pytest.raises(StorageError):
        asyncio.run(storage.get(reference=reference, filename="a.bin", mime_type=None))


def test_telegram_object_storage_delete_is_explicitly_unsupported():
    storage = TelegramObjectStorage(FakeTelegramStorage(message_id=42, file_id="tg-42"), channel_id=-10042)
    reference = StorageReference.telegram(channel_id=-10042, message_id=42, file_id="tg-42")

    with pytest.raises(StorageDeleteNotSupported):
        asyncio.run(storage.delete(reference=reference))
