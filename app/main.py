from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from telethon import TelegramClient

from app.config import load_settings
from app.db import connect_db, ensure_schema
from app.previews import PreviewRenderer
from app.repository import FileRepository
from app.service import StorageService
from app.telegram_bridge import TelegramStorage, TelethonStorage


def serialize_file(stored) -> dict:
    return {
        "id": stored.id,
        "name": stored.name,
        "size_bytes": stored.size_bytes,
        "mime_type": stored.mime_type,
        "status": stored.status,
        "uploaded_at": stored.uploaded_at.isoformat(),
    }


def build_app(service: StorageService, lifespan=None, preview_renderer: PreviewRenderer | None = None) -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    renderer = preview_renderer or PreviewRenderer(Path(".data") / "previews")
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
    app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        return templates.TemplateResponse(
            request,
            "index.html",
            {"files": [serialize_file(item) for item in service.list_files()]},
        )

    @app.get("/view/files/{file_id}", response_class=HTMLResponse)
    def detail_page(request: Request, file_id: int):
        stored = service.get_file(file_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="file not found")
        return templates.TemplateResponse(
            request,
            "file_detail.html",
            {"file": serialize_file(stored)},
        )

    @app.post("/files/upload", status_code=201)
    async def upload(file: UploadFile = File(...)):
        stored = await service.upload_bytes(
            filename=file.filename or "upload.bin",
            content=await file.read(),
            mime_type=file.content_type,
        )
        return JSONResponse(serialize_file(stored), status_code=201)

    @app.get("/files")
    def list_files():
        return [serialize_file(item) for item in service.list_files()]

    @app.get("/files/search")
    def search_files(q: str = Query("")):
        return [serialize_file(item) for item in service.search_files(q)]

    @app.get("/files/{file_id}")
    def file_detail(file_id: int):
        stored = service.get_file(file_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="file not found")
        return serialize_file(stored)

    @app.get("/files/{file_id}/download")
    async def download_file(file_id: int):
        downloaded = await service.download_file(file_id)
        return Response(
            content=downloaded.content,
            media_type=downloaded.mime_type or "application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{downloaded.filename}"'},
        )

    @app.get("/files/{file_id}/preview")
    async def preview_file(file_id: int):
        stored = service.get_file(file_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="file not found")
        try:
            downloaded = await service.download_file(file_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        preview = renderer.render(file_id=file_id, downloaded=downloaded)
        if preview is None:
            raise HTTPException(status_code=415, detail="no preview available for this file type")
        return Response(
            content=preview.content,
            media_type=preview.mime_type or "application/octet-stream",
            headers={"Content-Disposition": f'inline; filename="{preview.filename}"'},
        )

    return app


def create_app(telegram_storage: TelegramStorage | None = None) -> FastAPI:
    settings = load_settings()
    connection = connect_db(settings.database_path)
    ensure_schema(connection)
    client: TelegramClient | None = None
    if telegram_storage is None:
        client = TelegramClient(str(settings.telegram_session), settings.telegram_api_id, settings.telegram_api_hash)
        telegram_storage = TelethonStorage(client)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if client is not None:
            await client.start()
        yield
        if client is not None:
            await client.disconnect()

    service = StorageService(FileRepository(connection), telegram_storage, channel_id=settings.telegram_channel_id)
    preview_renderer = PreviewRenderer(settings.database_path.parent / "previews")
    return build_app(service, lifespan=lifespan, preview_renderer=preview_renderer)
