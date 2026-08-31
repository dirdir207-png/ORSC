import base64
import os

import pytest

from crew.mac_secrets import (
    MacKeychainKeyProvider,
    SecretStoreError,
    load_or_create_capability,
)


class Result:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_keychain_returns_existing_base64_key():
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return Result(stdout=base64.b64encode(b"k" * 32).decode() + "\n")

    key = MacKeychainKeyProvider(runner=run).get_or_create_key()
    assert key == b"k" * 32
    assert calls[0][0:2] == ["security", "find-generic-password"]


def test_keychain_creates_missing_key_without_leaking_it():
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return Result(returncode=44) if len(calls) == 1 else Result()

    key = MacKeychainKeyProvider(runner=run).get_or_create_key()
    assert len(key) == 32
    assert calls[1][0:2] == ["security", "add-generic-password"]
    assert base64.b64encode(key).decode() not in calls[1]
    assert calls[1][-1] == "-w"


def test_keychain_concurrent_creation_loads_winning_key():
    winning = base64.b64encode(b"w" * 32).decode()
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        if args[1] == "find-generic-password" and len(calls) == 1:
            return Result(returncode=44)
        if args[1] == "add-generic-password":
            return Result(returncode=45)
        return Result(stdout=winning)

    assert MacKeychainKeyProvider(runner=run).get_or_create_key() == b"w" * 32


def test_keychain_failure_is_sanitized():
    def run(args, **kwargs):
        return Result(returncode=1, stderr="secret diagnostic")

    with pytest.raises(SecretStoreError) as exc:
        MacKeychainKeyProvider(runner=run).get_or_create_key()
    assert "secret diagnostic" not in str(exc.value)


def test_capability_file_is_stable_and_private(tmp_path):
    path = tmp_path / "broker.capability"
    first = load_or_create_capability(path)
    second = load_or_create_capability(path)
    assert first == second
    assert len(first) >= 43
    assert os.stat(path).st_mode & 0o777 == 0o600


def test_existing_world_readable_capability_is_rejected(tmp_path):
    path = tmp_path / "broker.capability"
    path.write_text("weak")
    path.chmod(0o644)
    with pytest.raises(SecretStoreError):
        load_or_create_capability(path)
