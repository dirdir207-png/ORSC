import os

import pytest


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_FILE", str(tmp_path / "app.db"))
    import app as app_module
    app_module.DB_FILE = str(tmp_path / "app.db")
    app_module.init_db()
    app_module.app.secret_key = "0123456789abcdef0123456789abcdef"
    from meridian.evidence import EvidenceRepository
    from meridian.storage import DerivedKeyProvider, EncryptedBlobStore

    root = os.path.join(tmp_path, "evidence")
    store = EncryptedBlobStore(root, DerivedKeyProvider(app_module.app.secret_key.encode()))
    repo = EvidenceRepository(app_module.DB_FILE)
    blob = store.put(b"hello evidence", mime_type="text/plain")
    repo.add_item(
        source_kind="manual", source_id="seed-1", content_hash=blob.content_hash,
        mime_type="text/plain", size_bytes=blob.size_bytes, title="Note",
    )

    # The /content route is @login_required, so register/login a user on the
    # same client to establish the session cookie before the request.
    client = app_module.app.test_client()
    response = client.post(
        "/api/auth/register",
        json={
            "username": "testuser",
            "email": "testuser@example.com",
            "password": "test-password-123",
        },
    )
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["success"] is True
    return client, repo


def test_evidence_content_resolves(app):
    client, repo = app
    items = repo._connect().execute("SELECT id FROM evidence_items").fetchall()
    item_id = items[0]["id"]
    response = client.get(f"/api/meridian/evidence/{item_id}/content")
    assert response.status_code == 200
    assert response.data == b"hello evidence"
