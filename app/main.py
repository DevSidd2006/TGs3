from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from telethon import TelegramClient

from app.auth import hash_password, verify_password
from app.config import load_settings
from app.db import connect_db, ensure_schema
from app.previews import PreviewRenderer
from app.repository import AuthRepository, FileRepository
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


def format_bytes(num: int | None) -> str:
    if not num:
        return "0 B"
    k = 1024
    sizes = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    value = float(num)
    while value >= k and i < len(sizes) - 1:
        value /= k
        i += 1
    return f"{value:.1f} {sizes[i]}" if i else f"{int(value)} B"


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


class RedirectRequest(Exception):
    def __init__(self, location: str = "/login") -> None:
        self.location = location


def require_auth(request: Request, *, auth_password: str, auth_repo: AuthRepository) -> None:
    """For JSON API endpoints: raise 401 when unauthenticated."""
    if not auth_password:
        return
    token = request.cookies.get("tgs3_session")
    user = auth_repo.get_session_user(token) if token else None
    if user is None:
        raise HTTPException(status_code=401, detail="not authenticated")


def require_page(request: Request, *, auth_password: str, auth_repo: AuthRepository) -> None:
    """For HTML page endpoints: redirect to /login when unauthenticated."""
    if not auth_password:
        return
    token = request.cookies.get("tgs3_session")
    user = auth_repo.get_session_user(token) if token else None
    if user is None:
        raise RedirectRequest("/login")


def build_app(service: StorageService, lifespan=None, preview_renderer: PreviewRenderer | None = None, *, auth_password: str = "", auth_username: str = "admin", auth_repository: AuthRepository | None = None, session_ttl_days: int = 30, secure_cookie: bool = True) -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    renderer = preview_renderer or PreviewRenderer(Path(".data") / "previews")
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
    templates.env.filters["format_bytes"] = format_bytes
    app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

    auth = auth_repository or AuthRepository(service._repository._connection)
    if auth_password:
        auth.upsert_user(username=auth_username, password_hash=hash_password(auth_password))

    @app.exception_handler(RedirectRequest)
    async def _redirect_handler(_request: Request, exc: RedirectRequest):
        return RedirectResponse(exc.location, status_code=303)

    def require_auth_route(request: Request) -> None:
        require_auth(request, auth_password=auth_password, auth_repo=auth)

    def require_page_route(request: Request) -> None:
        require_page(request, auth_password=auth_password, auth_repo=auth)

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request):
        if not auth_password:
            return RedirectResponse("/", status_code=303)
        return templates.TemplateResponse(request, "login.html", {"error": None, "next": request.query_params.get("next", "/")})

    @app.post("/login")
    async def login_submit(request: Request):
        form = await request.form()
        username = form.get("username", "")
        password = form.get("password", "")
        next_url = form.get("next", "/")
        if not auth_password:
            return RedirectResponse(next_url or "/", status_code=303)
        stored_hash = auth.get_user_hash(auth_username)
        if username == auth_username and stored_hash and verify_password(password, stored_hash):
            token = auth.create_session(username=auth_username, ttl=timedelta(days=session_ttl_days))
            response = RedirectResponse(next_url or "/", status_code=303)
            response.set_cookie("tgs3_session", token, httponly=True, samesite="lax", secure=secure_cookie, max_age=session_ttl_days * 86400)
            return response
        return templates.TemplateResponse(request, "login.html", {"error": "Invalid username or password", "next": next_url}, status_code=401)

    @app.post("/logout")
    def logout(request: Request):
        token = request.cookies.get("tgs3_session")
        if token:
            auth.delete_session(token)
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie("tgs3_session")
        return response

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request, folder_id: int | None = None):
        require_page_route(request)
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
        require_page_route(request)
        stored = service.get_file(file_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="file not found")
        return templates.TemplateResponse(
            request,
            "file_detail.html",
            {"file": serialize_file(stored)},
        )

    @app.post("/files/upload", status_code=201)
    async def upload(request: Request, file: UploadFile = File(...), folder_id: int | None = None):
        require_auth_route(request)
        stored = await service.upload_bytes(
            filename=file.filename or "upload.bin",
            content=await file.read(),
            mime_type=file.content_type,
            folder_id=folder_id,
        )
        return JSONResponse(serialize_file(stored), status_code=201)

    @app.get("/files")
    def list_files(request: Request, folder_id: int | None = None):
        require_auth_route(request)
        return [serialize_file(item) for item in service.list_files(folder_id=folder_id)]

    @app.get("/files/search")
    def search_files(request: Request, q: str = Query("")):
        require_auth_route(request)
        return [serialize_file(item) for item in service.search_files(q)]

    @app.get("/folders")
    def folder_tree(request: Request):
        require_auth_route(request)
        return build_folder_tree(service.list_folders())

    @app.post("/folders", status_code=201)
    def create_folder(request: Request, payload: dict):
        require_auth_route(request)
        try:
            folder = service.create_folder(name=payload.get("name"), parent_id=payload.get("parent_id"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(serialize_folder(folder), status_code=201)

    @app.patch("/folders/{folder_id}")
    def rename_folder(request: Request, folder_id: int, payload: dict):
        require_auth_route(request)
        if service.get_folder(folder_id) is None:
            raise HTTPException(status_code=404, detail=f"folder {folder_id} not found")
        try:
            folder = service.rename_folder(folder_id, payload.get("name"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return serialize_folder(folder)

    @app.delete("/folders/{folder_id}", status_code=204)
    def delete_folder(request: Request, folder_id: int):
        require_auth_route(request)
        try:
            service.delete_folder(folder_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return Response(status_code=204)

    @app.post("/files/{file_id}/move")
    def move_file(request: Request, file_id: int, payload: dict):
        require_auth_route(request)
        try:
            stored = service.move_file(file_id=file_id, folder_id=payload.get("folder_id"))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return serialize_file(stored)

    @app.get("/files/{file_id}")
    def file_detail(request: Request, file_id: int):
        require_auth_route(request)
        stored = service.get_file(file_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="file not found")
        return serialize_file(stored)

    @app.get("/files/{file_id}/download")
    async def download_file(request: Request, file_id: int):
        require_auth_route(request)
        downloaded = await service.download_file(file_id)
        return Response(
            content=downloaded.content,
            media_type=downloaded.mime_type or "application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{downloaded.filename}"'},
        )

    @app.get("/files/{file_id}/preview")
    async def preview_file(request: Request, file_id: int):
        require_auth_route(request)
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
    return build_app(
        service,
        lifespan=lifespan,
        preview_renderer=preview_renderer,
        auth_password=settings.tgs3_password,
        auth_username=settings.tgs3_user,
        session_ttl_days=settings.session_ttl_days,
        secure_cookie=settings.secure_cookie,
    )
