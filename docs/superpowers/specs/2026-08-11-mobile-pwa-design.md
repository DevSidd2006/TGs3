# TGS3 Mobile PWA — Design

**Date:** 2026-08-11
**Status:** Approved
**Base:** TGS3 — see `2026-08-11-telegram-storage-design.md` and `2026-08-11-folders-design.md`

## Goal

Give TGS3 a phone-friendly, installable Progressive Web App so files can be accessed from anywhere on a mobile device. Deliver a core PWA (responsive UI + install to home screen + offline app shell), add a simple login layer so the publicly reachable server stays private, and document free hosting via Cloudflare Tunnel. No changes to the storage/Telegram layer — the mobile app is a new client over the existing REST API.

## Approach

Build a **standalone mobile PWA inside the existing repo** at `s3/mobile/`, served same-origin by the TGS3 FastAPI server. Same origin means the session cookie just works (no CORS), the service worker caches one domain, and login state is shared.

## Scope (Core PWA)

1. Mobile-optimized single-page UI for browsing/searching/uploading/previewing/downloading files and folders.
2. Installable: `manifest.webmanifest` + icons + service worker (offline app shell, network-first for API).
3. Login (username/password) protecting `/` and `/mobile*` routes when enabled.
4. Free hosting doc: Cloudflare Tunnel from the home machine.

Out of scope for this phase: auto photo backup, background sync, push notifications, native app-store builds, multi-user support, offline file content caching.

## Project Structure

```
s3/mobile/
  manifest.webmanifest      # app name TGS3, icons, standalone, theme color
  sw.js                     # service worker (cache shell, network-first API)
  icons/icon-192.png        # install icon
  icons/icon-512.png
  mobile.html               # phone-first single page app
  mobile.css                # mobile styles (self-contained, no dep on desktop CSS)
  mobile.js                 # app logic, talks to existing REST API
```

Served by FastAPI:
- `GET /mobile` → `mobile.html`
- `GET /mobile/manifest.webmanifest`
- `GET /mobile/sw.js`
- `GET /mobile/icons/*`
- Static assets mounted (or inlined) so the shell works standalone.

The desktop UI at `/` stays unchanged.

## Backend Changes

### Auth

- `users` table: `id`, `username`, `password_hash` (PBKDF2-HMAC-SHA256, per-user salt), `created_at`.
- Single user seeded from `.env`: `TGS3_USER` (default `admin`), `TGS3_PASSWORD` (required; refuse to start without it? — no: start but show a setup warning).
- Session cookie: signed value (HMAC via `itsdangerous` or a random token stored in a `sessions` table) with `HttpOnly`, `SameSite=Lax`, `Secure` (when behind HTTPS; configurable for LAN use), and an expiry (default 30 days).
- Routes:
  - `GET /login` → login page (Jinja template `login.html`).
  - `POST /login` → validate; set session cookie; redirect to `/?next=...`.
  - `POST /logout` → clear session; redirect to `/login`.
  - Dependency `require_auth` on `/`, `/mobile`, `/files*`, `/folders*`, `/view/*` when auth is enabled; exempt `/static`, `/login`, and manifest/sw/icons.
- 401 handling: HTML routes redirect to `/login`; JSON API routes return `401 {"detail": "not authenticated"}`.
- Auth is enabled by default once `TGS3_PASSWORD` is set; when unset, app runs open (dev mode) with a console warning.

### Mobile routes

- `GET /mobile` → `mobile.html`.
- `GET /mobile/manifest.webmanifest`, `GET /mobile/sw.js`, `GET /mobile/icons/{name}`.
- No data-model changes: mobile uses existing `/files`, `/files/search`, `/folders`, `/files/upload`, `/files/{id}/download`, `/files/{id}/preview`, `/files/{id}/move`.

## Mobile App (s3/mobile/)

### UI (single page)

- **Top bar**: TGS3 brand, search input, logout button.
- **Upload**: prominent "+" button → hidden file input (works with camera/photo picker on mobile).
- **Folder nav**: breadcrumb (All Files › …) + collapsible folder list; tap folder to enter; long-press/menu for rename/delete/new subfolder (reuses existing endpoints).
- **File list**: rows with type icon, name, size (human-readable), date, and actions (download, preview, move). Tap name → detail/preview.
- **Preview**: embedded iframe for supported types; image inline; otherwise link to download.
- **States**: empty view, loading, error toast (upload failure, 401 → redirect to login).
- **Offline**: service worker serves cached shell + JS/CSS so the app opens offline; API calls fail with a toast ("You're offline").

### Manifest

- `name: "TGS3"`, `short_name: "TGS3"`, `start_url: "/mobile"`, `display: "standalone"`, `background_color` / `theme_color` from the TGS3 palette, icons 192 + 512 (and maskable).

### Service worker

- **Precache**: `/mobile`, `/mobile/mobile.css`, `/mobile/mobile.js`, icons, manifest.
- **Strategy**: cache-first for precached shell; network-first falling back to cache for navigation; do not cache API responses (privacy; logged-out users must not see cached data).

## Behavior Details

- Opening `https://your.tunnel.url/mobile` on a phone → install prompt (Android) or "Add to Home Screen" (iOS) → launches fullscreen standalone.
- First run prompts login (session persists 30 days).
- Browsing, searching, uploading, moving, previewing all work over the API with the session cookie.
- Auth + same-origin means no CORS config anywhere.

## Testing

- **Web tests:**
  - Login: valid creds → 200 + session cookie set; invalid → 401/redirect; protected page without cookie → redirect to `/login`.
  - Logout: clears session.
  - `/mobile` serves HTML; manifest and sw reachable.
  - Existing 34 tests stay green (auth disabled by default in tests).
- **Manual (phone):** install to home screen, browse/search/upload/preview/download, log out, offline shell loads.

## Free Hosting

- Cloudflare Tunnel (free, no credit card): `cloudflared tunnel --url http://localhost:8000` → public HTTPS URL.
- Requires the home machine to be on and connected; document this constraint.
- For LAN-only fallback, phone can hit `http://<home-ip>:8000` directly (auth still enforced; note: cookie `Secure` flag must be off for plain HTTP LAN use).

## Out of Scope

Auto photo backup, background sync, push notifications, app-store builds, multi-user, offline file-content caching, encryption at rest.
