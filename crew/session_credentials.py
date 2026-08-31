import json
import sqlite3
from dataclasses import dataclass
from typing import Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class KeyProvider(Protocol):
    def get_or_create_key(self) -> bytes: ...


class CredentialDecryptionError(RuntimeError):
    pass


@dataclass(frozen=True)
class SessionCredential:
    cookies: tuple[dict[str, object], ...]
    expires_at: str | None = None


@dataclass(frozen=True)
class EncryptedCredential:
    version: int
    nonce: bytes
    ciphertext: bytes


class SessionCipher:
    AAD = b"simplecrew:crew-session:v1"

    def __init__(self, key_provider: KeyProvider):
        self._key_provider = key_provider

    def encrypt(self, credential: SessionCredential) -> EncryptedCredential:
        payload = json.dumps(
            {"cookies": credential.cookies, "expires_at": credential.expires_at},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        aes = AESGCM(self._key_provider.get_or_create_key())
        nonce = __import__("secrets").token_bytes(12)
        return EncryptedCredential(1, nonce, aes.encrypt(nonce, payload, self.AAD))

    def decrypt(self, encrypted: EncryptedCredential) -> SessionCredential:
        if encrypted.version != 1:
            raise CredentialDecryptionError("Unsupported Crew credential version")
        try:
            payload = AESGCM(self._key_provider.get_or_create_key()).decrypt(
                encrypted.nonce, encrypted.ciphertext, self.AAD
            )
            parsed = json.loads(payload)
            return SessionCredential(tuple(parsed["cookies"]), parsed.get("expires_at"))
        except (InvalidTag, KeyError, TypeError, ValueError) as exc:
            raise CredentialDecryptionError("Crew session credential could not be decrypted") from exc


class SessionCredentialStore:
    def __init__(self, db_path: str, cipher: SessionCipher):
        self._db_path = db_path
        self._cipher = cipher
        self._init_schema()

    def _init_schema(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS crew_credentials (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    kind TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    nonce BLOB NOT NULL,
                    ciphertext BLOB NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"""
            )

    def save(self, credential: SessionCredential) -> None:
        encrypted = self._cipher.encrypt(credential)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT INTO crew_credentials(id, kind, version, nonce, ciphertext)
                   VALUES(1, 'session_v1', ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET kind='session_v1', version=excluded.version,
                   nonce=excluded.nonce, ciphertext=excluded.ciphertext, updated_at=CURRENT_TIMESTAMP""",
                (encrypted.version, encrypted.nonce, encrypted.ciphertext),
            )

    def load(self) -> SessionCredential | None:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT version, nonce, ciphertext FROM crew_credentials WHERE id=1 AND kind='session_v1'"
            ).fetchone()
        if row is None:
            return None
        return self._cipher.decrypt(EncryptedCredential(int(row[0]), bytes(row[1]), bytes(row[2])))
