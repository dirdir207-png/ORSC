from crew.credentials import MacCredentialProvider, StoredBearerTokenProvider


def test_stored_provider_returns_existing_token():
    provider = StoredBearerTokenProvider(lambda: "secret-token")
    assert provider.get_bearer_token() == "secret-token"
    assert provider.describe() == "stored_bearer_token"


def test_stored_provider_preserves_missing_token():
    provider = StoredBearerTokenProvider(lambda: None)
    assert provider.get_bearer_token() is None


def test_provider_repr_never_contains_token():
    provider = StoredBearerTokenProvider(lambda: "super-secret-token")
    text = repr(provider)
    assert "super-secret-token" not in text


def test_mac_provider_is_a_seam_not_an_automatic_login_flow():
    provider = MacCredentialProvider(lambda: "local-token")
    assert provider.get_bearer_token() == "local-token"
    assert provider.describe() == "mac_credential_provider"


def test_stored_provider_normalizes_bearer_prefixed_token():
    """Existing installs store the full header value ('Bearer xyz').
    The client adds its own prefix, so the provider must strip any."""
    provider = StoredBearerTokenProvider(lambda: " Bearer abc123 ")
    assert provider.get_bearer_token() == "abc123"


def test_stored_provider_leaves_plain_token_untouched():
    provider = StoredBearerTokenProvider(lambda: "abc123")
    assert provider.get_bearer_token() == "abc123"
