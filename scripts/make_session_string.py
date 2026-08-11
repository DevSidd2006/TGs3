"""Generate a TELEGRAM_SESSION_STRING by logging in interactively.

Usage: .venv/bin/python scripts/make_session_string.py

Creates .data/telegram.session, logs in once (you enter phone + code),
then prints a session string to copy into .env / Render env vars.

Note: use a SEPARATE session string for each instance (local vs deployed).
Two instances sharing one session key will trigger AuthKeyDuplicatedError.
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession

load_dotenv()

api_id = int(os.environ["TELEGRAM_API_ID"])
api_hash = os.environ["TELEGRAM_API_HASH"]
session_path = Path(os.environ.get("TELEGRAM_SESSION", ".data/telegram.session"))

session_path.parent.mkdir(parents=True, exist_ok=True)

client = TelegramClient(StringSession(), api_id, api_hash)
client.start()
print("\n=== TELEGRAM_SESSION_STRING ===")
print(client.session.save())
print("================================\n")
client.disconnect()
