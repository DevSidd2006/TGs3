#!/usr/bin/env bash
set -e

echo "=== Building TGS3 Google Drive Application ==="
pip install --upgrade pip
pip install .

echo "=== Ensuring data directories exist ==="
mkdir -p /tmp/.data/previews

echo "=== Starting FastAPI Server on Port ${PORT:-8000} ==="
exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port "${PORT:-8000}"
