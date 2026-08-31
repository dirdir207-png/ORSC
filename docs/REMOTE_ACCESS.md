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

## 5. Renew an expired Crew session

Two options:

### Guided renewal (preferred)

1. Open SimpleCrew Account Settings → Crew Banking → Connection Health.
2. Run **Check Crew connection**. If it reports the connection needs attention, a **Reconnect Crew** button appears.
3. Confirm the Mac-local Crew broker is running, then click **Reconnect Crew on this Mac**. The broker opens an ephemeral browser window at Crew's login page.
4. Log in interactively (including your SMS/email code). The window can be closed as soon as the app reports success.
5. The broker captures only the approved Crew session cookies, validates them with a read-only health query, encrypts them with an AES-GCM key held in macOS Keychain, and only then replaces the stored session. You never see or copy a cookie or token.

The Docker app receives neither decrypted cookies nor the Keychain key. It reaches the broker through the configured host gateway and authenticates with the private capability file. The broker refuses non-loopback binds; do not publish its port through a reverse proxy, Funnel, or LAN interface.

If health says `broker_unavailable`, start or reload `com.simplecrew.crew-broker` on the Mac. If it says `credential_locked`, unlock/repair Keychain access and reconnect; the existing encrypted database record is preserved. A backup contains ciphertext but not the Keychain key, so restoring on another Mac requires a fresh interactive login.

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
