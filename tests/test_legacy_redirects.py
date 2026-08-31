import os
import sys
import tempfile
from urllib.parse import parse_qs, urlparse

import pytest

if "app" not in sys.modules:
    os.environ["DB_FILE"] = os.path.join(
        tempfile.mkdtemp(prefix="meridian_redirect_test_"), "savings_data.db"
    )

import app as simplecrew


@pytest.fixture
def authenticated_client(monkeypatch):
    user_id = "legacy-redirect-user"
    monkeypatch.setattr(
        simplecrew.login_manager,
        "_user_callback",
        lambda value: simplecrew.User(value, "owner", "owner@example.com"),
    )
    client = simplecrew.app.test_client()
    with client.session_transaction() as session:
        session["_user_id"] = user_id
        session["_fresh"] = True
    return client


@pytest.mark.parametrize(
    ("legacy_tab", "workspace"),
    [
        ("activity", "activity"),
        ("expenses", "plan"),
        ("bills", "plan"),
        ("goals", "plan"),
        ("pockets", "plan"),
        ("family", "accounts"),
        ("cards", "accounts"),
        ("credit", "accounts"),
        ("splitwise", "accounts"),
        ("account", "accounts"),
    ],
)
def test_legacy_tab_query_redirects_to_meridian_workspace(
    authenticated_client, legacy_tab, workspace
):
    response = authenticated_client.get(f"/?tab={legacy_tab}")

    assert response.status_code == 302
    target = urlparse(response.headers["Location"])
    assert target.path == "/meridian"
    assert parse_qs(target.query) == {"workspace": [workspace]}


@pytest.mark.parametrize("path", ["/expenses", "/bills", "/goals", "/pockets"])
def test_legacy_plan_paths_redirect_to_plan(authenticated_client, path):
    response = authenticated_client.get(path)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/meridian?workspace=plan")


@pytest.mark.parametrize(
    "path", ["/account", "/family", "/cards", "/credit", "/splitwise"]
)
def test_legacy_account_paths_redirect_to_accounts(authenticated_client, path):
    response = authenticated_client.get(path)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/meridian?workspace=accounts")
