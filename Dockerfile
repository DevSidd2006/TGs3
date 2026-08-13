FROM python:3.13-slim

WORKDIR /app

# Install system build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libreoffice-core libreoffice-writer libreoffice-calc libreoffice-impress \
    && rm -rf /var/lib/apt/lists/*

# Copy project specification & requirements
COPY pyproject.toml .
COPY README.md .

# Install Python dependencies
RUN pip install --no-cache-dir .

# Copy application code, templates, static assets, and mobile PWA
COPY app app
COPY mobile mobile

# Create data directory for SQLite database & preview cache
RUN mkdir -p /app/.data/previews

# Set environment defaults
ENV HOST=0.0.0.0
ENV PORT=8000
ENV DATABASE_PATH=/app/.data/files.db
ENV TELEGRAM_SESSION=/app/.data/telegram.session

EXPOSE 8000

# Entrypoint script or command with dynamic PORT support for Render/Koyeb/HF
CMD ["sh", "-c", "uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000}"]
