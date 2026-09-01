"""Local browser-based Crew credential capture for guided renewal.

Opens a real Chromium window via Playwright so the user can authenticate
interactively (credentials + OTP stay inside that window), captures the first
outgoing ``authorization`` header sent to the Crew API, and hands the raw
value to the caller. The value must only travel through server-side storage;
never log it or include it in responses.
"""

import threading
from urllib.parse import urlparse

from .renewal import CapturerUnavailable
from .session_credentials import SessionCredential

CREW_APP_URL = "https://app.trycrew.com"
CREW_API_HOSTS = frozenset({"api.trycrew.com", "crew-prod-api.fly.dev"})
CREW_COOKIE_DOMAINS = frozenset({"trycrew.com", "app.trycrew.com", "api.trycrew.com"})

INSTALL_GUIDANCE = (
    "Local renewal helper is not installed on this Mac. Run: "
    "./venv/bin/pip install playwright && ./venv/bin/playwright install chromium"
)


def _is_crew_api_url(url: str, hosts: frozenset[str] = CREW_API_HOSTS) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return host in hosts


def _filter_crew_cookies(cookies) -> tuple[dict[str, object], ...]:
    filtered = []
    for cookie in cookies or ():
        domain = str(cookie.get("domain") or "").lower().lstrip(".")
        if domain not in CREW_COOKIE_DOMAINS:
            continue
        filtered.append({
            key: cookie[key]
            for key in ("name", "value", "domain", "path", "expires", "httpOnly", "secure", "sameSite")
            if key in cookie
        })
    return tuple(filtered)


class PlaywrightSessionCapturer:
    """Open-frame capturer: uses the installed Chrome (channel="chrome") so the
    Crew login window is presented as a normal browser — Crew's anti-fraud
    sometimes OTP-loops fresh bundled-Chromium sessions."""

    def __init__(self, app_url: str = CREW_APP_URL, headless: bool = False):
        self._app_url = app_url
        self._headless = headless
        self._authenticated_event = threading.Event()
        self._playwright = self._browser = self._context = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch(headless=self._headless, channel="chrome")
        except Exception:
            self._browser = self._playwright.chromium.launch(headless=self._headless)
        self._context = self._browser.new_context()
        page = self._context.new_page()
        self._context.on("response", self._on_response)
        page.goto(self._app_url)
        return self

    def __exit__(self, *args):
        for closer in (
            lambda: self._context.close(), lambda: self._browser.close(), lambda: self._playwright.stop()
        ):
            try:
                closer()
            except Exception:
                pass
        return False

    def _on_response(self, response) -> None:
        if _is_crew_api_url(getattr(response, "url", "")) and getattr(response, "status", 0) < 400:
            self._authenticated_event.set()

    def capture(self, timeout_seconds: float) -> SessionCredential | None:
        if not self._authenticated_event.wait(timeout=max(0.0, float(timeout_seconds))):
            return None
        cookies = _filter_crew_cookies(self._context.cookies())
        return SessionCredential(cookies) if cookies else None

    def __repr__(self) -> str:
        return "PlaywrightSessionCapturer()"


class PlaywrightAuthorizationCapturer:
    """Context-manager capturer compatible with GuidedRenewalService."""

    def __init__(self, app_url: str = CREW_APP_URL, headless: bool = False):
        self._app_url = app_url
        self._headless = headless
        self._captured_header: str | None = None
        self._captured_event = threading.Event()
        self._playwright = None
        self._browser = None
        self._context = None

    def __enter__(self) -> "PlaywrightAuthorizationCapturer":
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch(headless=self._headless, channel="chrome")
        except Exception:
            self._browser = self._playwright.chromium.launch(headless=self._headless)
        self._context = self._browser.new_context()
        page = self._context.new_page()
        page.on("request", self._on_request)
        self._context.on("request", self._on_request)
        page.goto(self._app_url)
        return self

    def __exit__(self, *args) -> bool:
        for closer in (
            lambda: self._context.close(),
            lambda: self._browser.close(),
            lambda: self._playwright.stop(),
        ):
            try:
                closer()
            except Exception:
                pass
        self._context = None
        self._browser = None
        self._playwright = None
        return False

    def _on_request(self, request) -> None:
        if self._captured_event.is_set():
            return
        if not _is_crew_api_url(getattr(request, "url", "")):
            return
        header_value = None
        getter = getattr(request, "header_value", None)
        if callable(getter):
            for name in ("authorization", "x-api-key"):
                header_value = getter(name)
                if header_value:
                    break
        if not header_value:
            headers = getattr(request, "headers", None) or {}
            header_value = headers.get("authorization") or headers.get("x-api-key")
        if not header_value:
            all_headers = getattr(request, "all_headers", None)
            if callable(all_headers):
                headers = all_headers() or {}
                header_value = headers.get("authorization") or headers.get("x-api-key")
        if header_value:
            self._captured_header = header_value
            self._captured_event.set()

    def capture(self, timeout_seconds: float) -> str | None:
        """Block until an authorization header is seen or timeout elapses."""
        if not self._captured_event.wait(timeout=float(max(0.0, timeout_seconds))):
            return None
        return self._captured_header


def create_mac_capturer() -> PlaywrightAuthorizationCapturer:
    """Factory for GuidedRenewalService; fails with guidance when uninstalled."""
    try:
        import playwright.sync_api  # noqa: F401
    except Exception as exc:  # pragma: no cover - exercised via absence of dep
        raise CapturerUnavailable(INSTALL_GUIDANCE) from exc
    return PlaywrightAuthorizationCapturer()

