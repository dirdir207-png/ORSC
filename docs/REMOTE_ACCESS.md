# Enhanced SimpleCrew Remote Access

## 1. Start SimpleCrew locally

Docker:
```bash
docker-compose up -d --build
```

Manual Python:
```bash
python app.py
```

Verify locally:
```text
http://localhost:8080
```

## 2. Install and sign in to Tailscale on the Mac

Use the official Tailscale macOS app, sign in, and confirm the Mac appears in the same tailnet as the iPhone.

Check the Mac's private Tailscale IPv4 address:
```bash
tailscale ip -4
```

## 3. Access from iPhone

With Tailscale connected on the iPhone, open:
```text
http://<MAC_TAILSCALE_IP>:8080
```

SimpleCrew's own login/passkey is still required.

## 4. Do not expose SimpleCrew publicly

Do not configure router port forwarding, a public reverse proxy, or `tailscale funnel` for Milestone 1.

## 5. Replace an expired Crew token

Two options:

### Guided renewal (preferred)

1. Open SimpleCrew Account Settings → Crew Banking → Connection Health.
2. Run **Check Crew connection**. If it reports the connection needs attention, a **Reconnect Crew** button appears.
3. Click **Reconnect Crew** — a browser window opens at Crew's login page on this Mac.
4. Log in interactively (including your SMS/email code). The window can be closed as soon as the app reports success.
5. SimpleCrew captures the new credential server-side and re-checks health automatically. You never see or copy the token.

One-time helper install (Mac only, not needed in Docker):
```bash
./venv/bin/pip install playwright && ./venv/bin/playwright install chromium
```
Without it, Reconnect explains what to install instead of failing silently.

### Manual replacement

Update Token → paste your bearer token → Save → run **Check Crew connection**.

The token must never be placed in a URL or browser-side script. Health states: `healthy`, `unauthorized`, `unreachable`, `api_error`.

## 6. Disable remote access without stopping SimpleCrew

Disconnect/stop Tailscale on the Mac. SimpleCrew remains available locally at `http://localhost:8080`.

## 7. Run SimpleCrew on Mac startup

Two supported options:

- **Docker:** if your `docker-compose.yml` sets `restart: unless-stopped` (or `always`) and Docker Desktop starts at login, the container comes back automatically after restart.
- **Manual login item:** add a macOS Login Item (System Settings → General → Login Items) that opens Terminal running `python app.py` from this project directory.

A dedicated LaunchAgent script is not included yet; do not invent one until it has been tested.
