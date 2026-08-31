from meridian.connections import ConnectionRepository, ConnectionState
from meridian.connectors.email import READ_ONLY_GMAIL_SCOPE


def test_connection_repository_never_returns_provider_secrets(tmp_path):
    repository = ConnectionRepository(str(tmp_path / "connections.db"))

    saved = repository.upsert(
        kind="gmail",
        display_name="Gmail",
        state=ConnectionState.PENDING,
        granted_scopes=(READ_ONLY_GMAIL_SCOPE,),
        last_successful_at=None,
        retention_days=365,
    )

    assert saved.public_id.startswith("gmail_")
    assert saved.granted_scopes == (READ_ONLY_GMAIL_SCOPE,)
    assert not hasattr(saved, "access_token")
    assert repository.get(saved.public_id) == saved


def test_connection_repository_updates_state_and_revokes_one_source(tmp_path):
    repository = ConnectionRepository(str(tmp_path / "connections.db"))
    gmail = repository.upsert(
        kind="gmail",
        display_name="Gmail",
        state=ConnectionState.PENDING,
        granted_scopes=(READ_ONLY_GMAIL_SCOPE,),
        last_successful_at=None,
        retention_days=365,
    )
    calendar = repository.upsert(
        kind="calendar",
        display_name="Google Calendar",
        state=ConnectionState.CONNECTED,
        granted_scopes=("calendar.readonly",),
        last_successful_at="2026-08-31T08:00:00Z",
        retention_days=90,
    )

    connected = repository.mark_state(
        gmail.public_id,
        ConnectionState.CONNECTED,
        last_successful_at="2026-08-31T07:47:00Z",
    )
    revoked = repository.revoke(gmail.public_id)

    assert connected.state is ConnectionState.CONNECTED
    assert revoked.state is ConnectionState.REVOKED
    assert repository.get(calendar.public_id).state is ConnectionState.CONNECTED
    assert [record.public_id for record in repository.list_all()] == [
        gmail.public_id,
        calendar.public_id,
    ]
