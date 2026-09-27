# Hosting TGS3 on the Internet (free)

TGS3 runs as a local web app. To reach it from your phone anywhere:

## 1. Set up auth first (required)

Create a `.env` entry:

    TGS3_PASSWORD=your-secret-password
    TGS3_USER=admin            # optional, default admin

Without a password the app runs open (dev mode). With a password,
every page (including /mobile) requires login.

## 2. Install Cloudflare Tunnel (free)

1. Download `cloudflared` (https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)
2. Run the app: `cd ~/s3 && .venv/bin/uvicorn app.asgi:app --host 127.0.0.1 --port 8000`
3. Expose it: `cloudflared tunnel --url http://localhost:8000`
4. Cloudflare prints a public HTTPS URL (e.g. `https://xxxx.trycloudflare.com`)

That URL is temporary (changes on restart). For a permanent URL use a
named tunnel + your own domain on the Cloudflare free plan.

## 3. Use it on your phone

1. Open the public URL in a mobile browser.
2. Sign in (username/password from step 1).
3. Add to home screen (Android: menu → Add to Home screen; iOS: Share → Add to Home Screen).
4. Open the installed "TGS3" icon — it launches fullscreen.

## Notes

- Your home computer must stay on and online while the tunnel is running.
- Session cookie lasts 30 days by default (`TGS3_SESSION_TTL_DAYS`).
- `TGS3_SECURE_COOKIE=1` (default) works over the tunnel's HTTPS.
- For LAN-only use (no tunnel), visit `http://<home-ip>:8000` and set
  `TGS3_SECURE_COOKIE=0` so the cookie works over plain HTTP.
- Blockchain demo mode is intended for a local Anvil network. Do not expose
  local private keys or Anvil RPC endpoints through a public tunnel.
