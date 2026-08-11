FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements/project metadata
COPY pyproject.toml .
COPY README.md .

# Install dependencies
RUN pip install --no-cache-dir .

# Copy application files
COPY app app
COPY tests tests
COPY docs docs

# Create data directory for SQLite & session storage
RUN mkdir -p .data/previews

# Expose port 7860 (default Hugging Face Spaces port)
EXPOSE 7860

# Set environment variables
ENV HOST=0.0.0.0
ENV PORT=7860
ENV DATABASE_PATH=/app/.data/files.db
ENV TELEGRAM_SESSION=/app/.data/telegram.session

# Command to run application
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "7860"]
