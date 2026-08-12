import asyncio

from app.telegram_bridge import TelethonStorage
from tests.fakes import FakeTelethonClient, make_file_message


def test_list_channel_files_caps_scan_and_skips_non_files():
    messages = [
        make_file_message(1, name="a.pdf", size=10, mime="application/pdf"),
        make_file_message(2, name="b.txt", size=5, mime="text/plain"),
        make_file_message(3, has_file=False),
    ]
    client = FakeTelethonClient(messages)
    storage = TelethonStorage(client)

    files = asyncio.run(storage.list_channel_files(channel_id=-1009))

    assert client.iter_kwargs == {"limit": 200}
    assert [(f["telegram_message_id"], f["name"]) for f in files] == [(1, "a.pdf"), (2, "b.txt")]
    assert all(f["telegram_channel_id"] == -1009 for f in files)


class _UnpackableFile:
    name = "photo.png"
    size = 10
    mime_type = "image/png"

    @property
    def id(self):
        raise AttributeError("'PhotoSize' object has no attribute 'location'")


def make_unpackable_message(message_id: int):
    class _Message:
        id = message_id
        message = "caption"
        file = _UnpackableFile()

    return _Message()


def test_list_channel_files_falls_back_when_file_id_unpackable():
    client = FakeTelethonClient([make_unpackable_message(5)])
    storage = TelethonStorage(client)

    files = asyncio.run(storage.list_channel_files(channel_id=-1009))

    assert len(files) == 1
    assert files[0]["telegram_message_id"] == 5
    assert files[0]["telegram_file_id"] == "msg_5"
    assert files[0]["name"] == "photo.png"
