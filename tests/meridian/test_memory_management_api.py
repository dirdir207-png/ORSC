import pytest
from flask import Flask
from flask_login import LoginManager

from meridian.api import meridian_api


class _User:
    is_authenticated = True
    is_active = True
    is_anonymous = False

    def get_id(self):
        return "1"


@pytest.fixture()
def client():
    app = Flask(__name__)
    app.secret_key = "test-secret"
    captured = {}

    def sink(action_type, params):
        captured["type"] = action_type
        captured["params"] = params
        return {"id": "req-1", "state": "proposed"}

    app.config["MERIDIAN_PROPOSAL_SINK_FACTORY"] = lambda: sink
    app.register_blueprint(meridian_api, url_prefix="/api/meridian")
    login = LoginManager(app)

    @login.user_loader
    def load_user(user_id):
        return _User()

    test_client = app.test_client()
    with test_client.session_transaction() as session:
        session["_user_id"] = "1"
    return test_client, captured


def test_create_asset_proposal(client):
    test_client, captured = client
    response = test_client.post("/api/meridian/assets", json={
        "name": "Laptop", "category": "electronics", "purchase_price": 1500.0,
        "confidence": 1.0,
    })
    assert response.status_code == 202
    assert response.get_json()["proposal"]["state"] == "proposed"
    assert captured["type"] == "create_asset"


def test_update_and_delete_contract_proposals(client):
    test_client, captured = client
    assert test_client.patch("/api/meridian/contracts/3", json={
        "name": "Car policy", "kind": "insurance", "confidence": 1.0,
    }).status_code == 202
    assert captured["type"] == "update_contract"
    assert captured["params"]["record_id"] == 3
    assert test_client.delete("/api/meridian/contracts/3",
                              json={"change_reason": "cancelled"}).status_code == 202
    assert captured["type"] == "delete_contract"


def test_invalid_payload_400(client):
    test_client, _ = client
    response = test_client.post("/api/meridian/assets", json={"name": "x"})  # missing category
    assert response.status_code == 400


def test_invalid_asset_id_400(client):
    test_client, _ = client
    response = test_client.patch("/api/meridian/assets/not-a-number", json={
        "name": "Laptop", "category": "electronics",
    })
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_request"


def test_unconfigured_sink_503():
    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.register_blueprint(meridian_api, url_prefix="/api/meridian")
    login = LoginManager(app)

    @login.user_loader
    def load_user(user_id):
        return _User()

    test_client = app.test_client()
    with test_client.session_transaction() as session:
        session["_user_id"] = "1"

    response = test_client.post("/api/meridian/assets",
                                json={"name": "x", "category": "y"})
    assert response.status_code == 503
