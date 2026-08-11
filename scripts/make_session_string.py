"""Generate a TELEGRAM_SESSION_STRING by logging in interactively.

Usage: .venv/bin/python scripts/make_session_string.py

Optional: set TGS3_TELEGRAM_PHONE in the environment to skip the phone prompt
(you will still need to enter the login code sent to your phone).

Prints a session string to copy into .env / Render env vars.

Note: use a SEPARATE session string for each instance (local vs deployed).
Two instances sharing one session key will trigger AuthKeyDuplicatedError.
"""
import os

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession

load_dotenv()

api_id = int(os.environ["TELEGRAM_API_ID"])
api_hash = os.environ["TELEGRAM_API_HASH"]
phone = os.environ.get("TGS3_TELEGRAM_PHONE")

client = TelegramClient(StringSession(), api_id, api_hash)
client.start(phone=phone)
print("\n=== TELEGRAM_SESSION_STRING ===")
print(client.session.save())
print("================================\n")
client.disconnect()
