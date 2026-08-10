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
        "folder_id": getattr(stored, "folder_id", None),
    }


def serialize_folder(folder) -> dict:
    return {"id": folder.id, "name": folder.name, "parent_id": folder.parent_id}


def build_folder_tree(folders: list) -> list[dict]:
    children: dict[int | None, list[dict]] = {f.id: [] for f in folders}
    roots: list[dict] = []
    by_id = {f.id: f for f in folders}
    for folder in folders:
        node = {"id": folder.id, "name": folder.name, "parent_id": folder.parent_id, "children": children[folder.id]}
        if folder.parent_id is None:
            roots.append(node)
        elif folder.parent_id in by_id:
            children[folder.parent_id].append(node)
        else:
            roots.append(node)
    return roots


def build_app(service: StorageService, lifespan=None, preview_renderer: PreviewRenderer | None = None) -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    renderer = preview_renderer or PreviewRenderer(Path(".data") / "previews")
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
    app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request, folder_id: int | None = None):
        files = service.list_files(folder_id=folder_id)
        folders = service.list_folders()
        breadcrumb = service.get_breadcrumb(folder_id) if folder_id is not None else []
        subfolders = [folder for folder in folders if folder.parent_id == folder_id]
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "files": [serialize_file(item) for item in files],
                "folders": [serialize_folder(item) for item in folders],
                "folder_tree": build_folder_tree(folders),
                "subfolders": [serialize_folder(item) for item in subfolders],
                "breadcrumb": [serialize_folder(item) for item in breadcrumb],
                "current_folder_id": folder_id,
            },
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
    async def upload(file: UploadFile = File(...), folder_id: int | None = None):
        stored = await service.upload_bytes(
            filename=file.filename or "upload.bin",
            content=await file.read(),
            mime_type=file.content_type,
            folder_id=folder_id,
        )
        return JSONResponse(serialize_file(stored), status_code=201)

    @app.get("/files")
    def list_files(folder_id: int | None = None):
        return [serialize_file(item) for item in service.list_files(folder_id=folder_id)]

    @app.get("/files/search")
    def search_files(q: str = Query("")):
        return [serialize_file(item) for item in service.search_files(q)]

    @app.get("/folders")
    def folder_tree():
        return build_folder_tree(service.list_folders())

    @app.post("/folders", status_code=201)
    def create_folder(payload: dict):
        try:
            folder = service.create_folder(name=payload.get("name"), parent_id=payload.get("parent_id"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(serialize_folder(folder), status_code=201)

    @app.patch("/folders/{folder_id}")
    def rename_folder(folder_id: int, payload: dict):
        if service.get_folder(folder_id) is None:
            raise HTTPException(status_code=404, detail=f"folder {folder_id} not found")
        try:
            folder = service.rename_folder(folder_id, payload.get("name"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return serialize_folder(folder)

    @app.delete("/folders/{folder_id}", status_code=204)
    def delete_folder(folder_id: int):
        try:
            service.delete_folder(folder_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return Response(status_code=204)

    @app.post("/files/{file_id}/move")
    def move_file(file_id: int, payload: dict):
        try:
            stored = service.move_file(file_id=file_id, folder_id=payload.get("folder_id"))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return serialize_file(stored)

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
