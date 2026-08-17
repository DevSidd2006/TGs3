import os
import time
import urllib.parse
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from telethon import TelegramClient
from telethon.sessions import StringSession


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
        "share_token": getattr(stored, "share_token", None),
        "starred": getattr(stored, "starred", False),
        "deleted_at": getattr(stored, "deleted_at", None),
    }


def serialize_folder(folder) -> dict:
    return {"id": folder.id, "name": folder.name, "parent_id": folder.parent_id, "starred": getattr(folder, "starred", False)}


VIEW_TITLES = {"starred": "Starred", "shared": "Shared with me", "recent": "Recent", "trash": "Trash"}


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
        node = {"id": folder.id, "name": folder.name, "parent_id": folder.parent_id, "starred": folder.starred, "children": children[folder.id]}
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


def build_app(service: StorageService, lifespan=None, preview_renderer: PreviewRenderer | None = None, *, auth_password: str = "", auth_username: str = "admin", auth_repository: AuthRepository | None = None, session_ttl_days: int = 30, secure_cookie: bool = True, sync_cooldown_seconds: int = 60) -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    renderer = preview_renderer or PreviewRenderer(Path(".data") / "previews")
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
    templates.env.filters["format_bytes"] = format_bytes
    app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

    auth = auth_repository or AuthRepository(service._repository._connection)
    if auth_password:
        auth.upsert_user(username=auth_username, password_hash=hash_password(auth_password))

    last_sync_at: float | None = None

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
    def index(request: Request, folder_id: int | None = None, view: str = "home"):
        require_page_route(request)
        if view not in ("home", "starred", "shared", "recent", "trash"):
            view = "home"
        folders = service.list_folders()
        breadcrumb: list = []
        folder_grid_items: list = []
        if view == "starred":
            starred = service.list_starred()
            files = starred["files"]
            folder_grid_items = starred["folders"]
        elif view == "shared":
            files = service.list_shared()
        elif view == "recent":
            files = service.list_recent()
        elif view == "trash":
            files = service.list_trash()
        else:
            files = service.list_files(folder_id=folder_id)
            breadcrumb = service.get_breadcrumb(folder_id) if folder_id is not None else []
            folder_grid_items = [folder for folder in folders if folder.parent_id == folder_id]
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "files": [serialize_file(item) for item in files],
                "folders": [serialize_folder(item) for item in folders],
                "folder_tree": build_folder_tree(folders),
                "subfolders": [serialize_folder(item) for item in folder_grid_items],
                "breadcrumb": [serialize_folder(item) for item in breadcrumb],
                "current_folder_id": folder_id,
                "current_view": view,
                "view_title": VIEW_TITLES.get(view),
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
    def list_files(request: Request, folder_id: int | None = None, view: str = "home"):
        require_auth_route(request)
        if view == "starred":
            starred = service.list_starred()
            return {
                "files": [serialize_file(item) for item in starred["files"]],
                "folders": [serialize_folder(item) for item in starred["folders"]],
            }
        if view == "shared":
            return [serialize_file(item) for item in service.list_shared()]
        if view == "recent":
            return [serialize_file(item) for item in service.list_recent()]
        if view == "trash":
            return [serialize_file(item) for item in service.list_trash()]
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

    @app.post("/folders/{folder_id}/star")
    def star_folder(request: Request, folder_id: int, payload: dict):
        require_auth_route(request)
        folder = service.star_folder(folder_id, bool(payload.get("enabled", False)))
        if folder is None:
            raise HTTPException(status_code=404, detail=f"folder {folder_id} not found")
        return serialize_folder(folder)

    @app.post("/files/{file_id}/move")
    def move_file(request: Request, file_id: int, payload: dict):
        require_auth_route(request)
        try:
            stored = service.move_file(file_id=file_id, folder_id=payload.get("folder_id"))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return serialize_file(stored)

    @app.post("/files/{file_id}/star")
    def star_file(request: Request, file_id: int, payload: dict):
        require_auth_route(request)
        try:
            stored = service.star_file(file_id, bool(payload.get("enabled", False)))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return serialize_file(stored)

    @app.post("/files/{file_id}/trash")
    def trash_file(request: Request, file_id: int):
        require_auth_route(request)
        try:
            stored = service.trash_file(file_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return serialize_file(stored)

    @app.post("/files/{file_id}/restore")
    def restore_file(request: Request, file_id: int):
        require_auth_route(request)
        try:
            stored = service.restore_file(file_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return serialize_file(stored)

    @app.delete("/files/{file_id}", status_code=204)
    def delete_file_forever(request: Request, file_id: int):
        require_auth_route(request)
        service.purge_file(file_id)
        return Response(status_code=204)

    @app.post("/trash/empty")
    def empty_trash(request: Request):
        require_auth_route(request)
        return {"purged_count": service.empty_trash()}

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
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(downloaded.filename)}"},
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
            headers={"Content-Disposition": f"inline; filename*=UTF-8''{urllib.parse.quote(preview.filename)}"},
        )

    @app.post("/files/{file_id}/share")
    def share_file(request: Request, file_id: int, payload: dict):
        require_auth_route(request)
        try:
            stored = service.toggle_share(file_id, payload.get("enabled", False))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return serialize_file(stored)

    @app.get("/s/{token}", response_class=HTMLResponse)
    def shared_file_page(request: Request, token: str):
        stored = service.get_shared_file(token)
        if stored is None:
            raise HTTPException(status_code=404, detail="file not found")
        return templates.TemplateResponse(
            request,
            "shared_file.html",
            {"file": serialize_file(stored), "token": token},
        )

    @app.get("/s/{token}/download")
    async def download_shared_file(request: Request, token: str):
        stored = service.get_shared_file(token)
        if stored is None:
            raise HTTPException(status_code=404, detail="file not found")
        downloaded = await service.download_file(stored.id)
        return Response(
            content=downloaded.content,
            media_type=downloaded.mime_type or "application/octet-stream",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(downloaded.filename)}"},
        )

    @app.get("/s/{token}/{filename}")
    async def direct_shared_file(request: Request, token: str, filename: str):
        stored = service.get_shared_file(token)
        if stored is None:
            raise HTTPException(status_code=404, detail="file not found")
        downloaded = await service.download_file(stored.id)
        # We use inline so that bots/browsers can display or parse it directly
        return Response(
            content=downloaded.content,
            media_type=downloaded.mime_type or "application/octet-stream",
            headers={"Content-Disposition": f"inline; filename*=UTF-8''{urllib.parse.quote(downloaded.filename)}"},
        )

    @app.get("/s/{token}/preview")
    async def preview_shared_file(request: Request, token: str):
        stored = service.get_shared_file(token)
        if stored is None:
            raise HTTPException(status_code=404, detail="file not found")
        try:
            downloaded = await service.download_file(stored.id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        preview = renderer.render(file_id=stored.id, downloaded=downloaded)
        if preview is None:
            raise HTTPException(status_code=415, detail="no preview available for this file type")
        return Response(
            content=preview.content,
            media_type=preview.mime_type or "application/octet-stream",
            headers={"Content-Disposition": f"inline; filename*=UTF-8''{urllib.parse.quote(preview.filename)}"},
        )

    @app.post("/sync")
    async def sync_channel(request: Request):
        nonlocal last_sync_at
        require_auth_route(request)
        now = time.monotonic()
        if sync_cooldown_seconds > 0 and last_sync_at is not None and now - last_sync_at < sync_cooldown_seconds:
            retry_after = int(sync_cooldown_seconds - (now - last_sync_at)) + 1
            raise HTTPException(status_code=429, detail=f"sync in progress or too recent; retry after {retry_after}s")
        count = await service.sync_from_channel()
        last_sync_at = time.monotonic()
        return {"synced_count": count}


    LOGO_DIR = Path(__file__).parent.parent / "logo"

    @app.get("/logo/{name}")
    def serve_logo(name: str):
        allowed = {"tgs3-logo-dark.png", "tgs3-logo-light.png"}
        if name not in allowed:
            raise HTTPException(status_code=404, detail="logo not found")
        return Response(content=(LOGO_DIR / name).read_bytes(), media_type="image/png")

    MOBILE_DIR = Path(__file__).parent.parent / "mobile"

    @app.get("/mobile", response_class=HTMLResponse)
    def mobile_page(request: Request):
        require_page_route(request)
        return HTMLResponse((MOBILE_DIR / "mobile.html").read_text())

    @app.get("/mobile/mobile.css")
    def mobile_css():
        return Response(
            content=(MOBILE_DIR / "mobile.css").read_text(),
            media_type="text/css",
        )

    @app.get("/mobile/mobile.js")
    def mobile_js():
        return Response(
            content=(MOBILE_DIR / "mobile.js").read_text(),
            media_type="application/javascript",
        )

    @app.get("/mobile/manifest.webmanifest")
    def mobile_manifest():
        return Response(
            content=(MOBILE_DIR / "manifest.webmanifest").read_text(),
            media_type="application/manifest+json",
        )

    @app.get("/mobile/sw.js")
    def mobile_sw():
        return Response(
            content=(MOBILE_DIR / "sw.js").read_text(),
            media_type="application/javascript",
            headers={"Service-Worker-Allowed": "/"},
        )

    @app.get("/mobile/icons/{name}")
    def mobile_icon(name: str):
        allowed = {"icon-192.png", "icon-512.png"}
        if name not in allowed:
            raise HTTPException(status_code=404, detail="icon not found")
        return Response(content=(MOBILE_DIR / "icons" / name).read_bytes(), media_type="image/png")

    return app


def create_app(telegram_storage: TelegramStorage | None = None) -> FastAPI:
    settings = load_settings()
    connection = connect_db(settings.database_path)
    ensure_schema(connection)
    client: TelegramClient | None = None
    if telegram_storage is None:
        session_str = os.environ.get("TELEGRAM_SESSION_STRING")
        session_arg = StringSession(session_str) if session_str else str(settings.telegram_session)
        client = TelegramClient(session_arg, settings.telegram_api_id, settings.telegram_api_hash)
        telegram_storage = TelethonStorage(client)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if client is not None:
            bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
            if bot_token:
                await client.start(bot_token=bot_token)
            else:
                await client.connect()
                if not await client.is_user_authorized():
                    raise RuntimeError(
                        "Telegram client is not authorized. Please set TELEGRAM_SESSION_STRING or TELEGRAM_BOT_TOKEN in environment variables, or upload a valid session file."
                    )
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
        sync_cooldown_seconds=settings.sync_cooldown_seconds,
    )
