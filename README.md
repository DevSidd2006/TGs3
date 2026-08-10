# README.md

## Telegram Storage MVP

### Local setup

1. Create a virtual environment.
2. Install dependencies with `pip install -e .[dev]`.
3. Copy `.env.example` values into your shell environment.
4. Start the app with `uvicorn app.asgi:app --reload`.
5. Open `http://127.0.0.1:8000`.

### Required Telegram preparation

1. Create a private Telegram channel.
2. Use your Telegram API ID and API hash.
3. Set `TELEGRAM_CHANNEL_ID` to the target channel.
4. On first run, complete the Telethon login flow so the session file is created.

### MVP behavior

- Upload a file from the dashboard.
- Files are sent to Telegram and indexed in SQLite.
- Search filters the local SQLite index.
- Download pulls the file back through the backend.
