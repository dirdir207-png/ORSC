import pytest

from crew.browser_capture import (
    PlaywrightAuthorizationCapturer,
    PlaywrightSessionCapturer,
    _filter_crew_cookies,
    _is_crew_api_url,
    create_mac_capturer,
)
from crew.renewal import CapturerUnavailable

try:
    import playwright  # noqa: F401

    HAS_PLAYWRIGHT = True
except Exception:
    HAS_PLAYWRIGHT = False


def test_crew_api_urls_match_by_host_suffix():
    assert _is_crew_api_url("https://api.trycrew.com/willow/graphql")
    assert _is_crew_api_url("https://api.trycrew.com/")
    assert not _is_crew_api_url("https://app.trycrew.com/login")
    assert not _is_crew_api_url("https://evil.example/api.trycrew.com")
    assert not _is_crew_api_url("not a url")


def test_crew_api_urls_include_current_graphql_host():
    assert _is_crew_api_url("https://crew-prod-api.fly.dev/willow/graphql")


def test_capture_returns_none_after_timeout_without_browser_events():
    capturer = PlaywrightAuthorizationCapturer()
    start = __import__("time").monotonic()
    assert capturer.capture(timeout_seconds=0.05) is None
    assert __import__("time").monotonic() - start < 2.0


def test_on_request_captures_authorization_from_crew_api_only():
    class FakeRequest:
        def __init__(self, url, headers):
            self.url = url
            self.headers = headers

        def header_value(self, name):
            return self.headers.get(name)

    capturer = PlaywrightAuthorizationCapturer()
    capturer._on_request(FakeRequest("https://app.trycrew.com/session", {"authorization": "Bearer nope"}))
    assert not capturer._captured_event.is_set()
    capturer._on_request(FakeRequest("https://api.trycrew.com/willow/graphql", {"authorization": "Bearer yes"}))
    assert capturer._captured_event.is_set()
    assert capturer.capture(timeout_seconds=0.1) == "Bearer yes"


def test_on_request_captures_x_api_key_from_current_crew_api():
    class FakeRequest:
        url = "https://crew-prod-api.fly.dev/willow/graphql"
        headers = {"x-api-key": "current-credential"}

        def header_value(self, name):
            return self.headers.get(name)

    capturer = PlaywrightAuthorizationCapturer()
    capturer._on_request(FakeRequest())
    assert capturer.capture(timeout_seconds=0.1) == "current-credential"


def test_on_request_uses_complete_headers_for_sensitive_authorization():
    class FakeRequest:
        url = "https://api.trycrew.com/willow/graphql"
        headers = {}

        def header_value(self, name):
            return None

        def all_headers(self):
            return {"authorization": "Bearer complete-header"}

    capturer = PlaywrightAuthorizationCapturer()
    capturer._on_request(FakeRequest())
    assert capturer.capture(timeout_seconds=0.1) == "Bearer complete-header"


def test_filter_crew_cookies_keeps_only_exact_approved_domains():
    cookies = [
        {"name": "crew", "value": "one", "domain": ".trycrew.com", "path": "/", "expires": 100},
        {"name": "api", "value": "two", "domain": "api.trycrew.com", "path": "/willow", "expires": -1},
        {"name": "evil", "value": "three", "domain": "eviltrycrew.com", "path": "/", "expires": 100},
        {"name": "other", "value": "four", "domain": "example.com", "path": "/", "expires": 100},
    ]
    assert _filter_crew_cookies(cookies) == (
        {"name": "crew", "value": "one", "domain": ".trycrew.com", "path": "/", "expires": 100},
        {"name": "api", "value": "two", "domain": "api.trycrew.com", "path": "/willow", "expires": -1},
    )


def test_session_capturer_returns_filtered_context_cookies():
    class Context:
        def cookies(self):
            return [{"name": "crew", "value": "opaque", "domain": ".trycrew.com", "path": "/", "expires": -1}]

    capturer = PlaywrightSessionCapturer()
    capturer._context = Context()
    capturer._authenticated_event.set()
    session = capturer.capture(0.1)
    assert session.cookies[0]["name"] == "crew"


@pytest.mark.skipif(HAS_PLAYWRIGHT, reason="playwright installed; absence path untestable here")
def test_factory_reports_unavailable_with_guidance_when_missing():
    with pytest.raises(CapturerUnavailable) as exc:
        create_mac_capturer()
    assert "playwright" in str(exc.value)
