import pytest

from meridian.api import meridian_api
from meridian.assets import Asset, AssetRepository


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from flask import Flask
    from flask_login import LoginManager

    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.config["MERIDIAN_REPOSITORY_FACTORY"] = lambda: _Repo(str(tmp_path / "m.db"))
    app.register_blueprint(meridian_api, url_prefix="/api/meridian")
    login = LoginManager(app)

    class User:
        @property
        def is_authenticated(self):
            return True

        @property
        def is_active(self):
            return True

        @property
        def is_anonymous(self):
            return False

        def get_id(self):
            return "1"

    @login.user_loader
    def load_user(user_id):
        return User()

    AssetRepository(str(tmp_path / "m.db")).save_asset(Asset(
        id=None, name="Laptop", category="electronics", purchased_on=None,
        purchase_price=1500.0, return_until=None, maintenance_interval_days=None,
        replacement_reserve=1200.0, evidence_id=None, evidence_span="receipt",
        confidence=0.98,
    ))
    client = app.test_client()
    # flask-login only treats a request as authenticated once _user_id is in the
    # session (see the api_client fixture in tests/meridian/test_api.py).
    with client.session_transaction() as session:
        session["_user_id"] = "1"
        session["_fresh"] = True
    return client


class _Repo:
    def __init__(self, db_path):
        self.db_path = db_path


def test_memory_today_returns_workspace_items(client):
    response = client.get("/api/meridian/memory/today")
    assert response.status_code == 200
    body = response.get_json()
    assert body["workspace"] == "today"
    assert isinstance(body["items"], list)


def test_memory_unknown_workspace_is_404(client):
    response = client.get("/api/meridian/memory/nope")
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "invalid_request"


def test_memory_requires_auth(tmp_path):
    from flask import Flask
    from flask_login import LoginManager

    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.config["MERIDIAN_REPOSITORY_FACTORY"] = lambda: _Repo(str(tmp_path / "a.db"))
    app.register_blueprint(meridian_api, url_prefix="/api/meridian")
    login = LoginManager(app)
    # Without login_view flask-login aborts 401 instead of redirecting; a login
    # view is required for the expected 302 redirect to /login.
    login.login_view = "login_page"

    @app.route("/login")
    def login_page():
        return "login"

    class Anon:
        is_authenticated = False
        is_active = False
        is_anonymous = True

        def get_id(self):
            return None

    @login.user_loader
    def load_user(user_id):
        return None

    response = app.test_client().get("/api/meridian/memory/today")
    assert response.status_code == 302  # redirected to login
