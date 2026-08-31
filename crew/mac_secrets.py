import base64
import os
import secrets
import subprocess
from pathlib import Path


class SecretStoreError(RuntimeError):
    pass


class MacKeychainKeyProvider:
    def __init__(
        self,
        service: str = "com.simplecrew.crew-session",
        account: str = "default",
        runner=subprocess.run,
    ):
        self._service = service
        self._account = account
        self._runner = runner

    def get_or_create_key(self) -> bytes:
        def find():
            return self._runner(
                ["security", "find-generic-password", "-s", self._service, "-a", self._account, "-w"],
                capture_output=True,
                text=True,
            )

        def decode(result):
            try:
                value = base64.b64decode(result.stdout.strip(), validate=True)
            except ValueError as exc:
                raise SecretStoreError("Crew session encryption key is invalid") from exc
            if len(value) != 32:
                raise SecretStoreError("Crew session encryption key is invalid")
            return value

        result = find()
        if result.returncode == 0:
            return decode(result)
        if result.returncode != 44:
            raise SecretStoreError("macOS Keychain is unavailable")
        key = secrets.token_bytes(32)
        encoded = base64.b64encode(key).decode()
        created = self._runner(
            [
                "security", "add-generic-password", "-s", self._service,
                "-a", self._account, "-w",
            ],
            input=encoded,
            capture_output=True,
            text=True,
        )
        if created.returncode != 0:
            winner = find()
            if winner.returncode == 0:
                return decode(winner)
            raise SecretStoreError("Crew session encryption key could not be stored")
        return key

    def __repr__(self) -> str:
        return "MacKeychainKeyProvider()"


def load_or_create_capability(path: str | os.PathLike[str]) -> str:
    target = Path(path)
    if target.exists():
        stat = target.lstat()
        if target.is_symlink() or not target.is_file() or stat.st_uid != os.getuid() or stat.st_mode & 0o077:
            raise SecretStoreError("Crew broker capability storage is not private")
        value = target.read_text().strip()
        if len(value) < 43:
            raise SecretStoreError("Crew broker capability is invalid")
        return value
    target.parent.mkdir(parents=True, exist_ok=True)
    value = secrets.token_urlsafe(32)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, value.encode())
    finally:
        os.close(fd)
    os.chmod(target, 0o600)
    return value
