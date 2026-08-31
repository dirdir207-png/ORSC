"""Encrypted, content-addressed storage for financial evidence blobs."""

import hashlib
import os
import secrets
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class KeyProvider(Protocol):
    def get_or_create_key(self) -> bytes: ...


class BlobDecryptionError(RuntimeError):
    pass


@dataclass(frozen=True)
class StoredBlob:
    content_hash: str
    mime_type: str
    size_bytes: int
    path: str
    created: bool


class EncryptedBlobStore:
    """Store each unique payload under its SHA-256 identity using envelope encryption."""

    MAGIC = b"MEB1"

    def __init__(self, root: str | os.PathLike[str], key_provider: KeyProvider):
        self._root = Path(root)
        self._key_provider = key_provider
        self._root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self._root, 0o700)

    def _path(self, content_hash: str) -> Path:
        if len(content_hash) != 64 or any(
            char not in "0123456789abcdef" for char in content_hash
        ):
            raise ValueError("content_hash must be a lowercase SHA-256 digest")
        return self._root / content_hash[:2] / f"{content_hash}.blob"

    def put(self, content: bytes, *, mime_type: str) -> StoredBlob:
        if not isinstance(content, bytes):
            raise TypeError("content must be bytes")
        if not mime_type or len(mime_type) > 255:
            raise ValueError("mime_type is required")
        content_hash = hashlib.sha256(content).hexdigest()
        target = self._path(content_hash)
        if target.exists():
            return StoredBlob(content_hash, mime_type, len(content), str(target), False)

        data_key = secrets.token_bytes(32)
        wrap_nonce = secrets.token_bytes(12)
        data_nonce = secrets.token_bytes(12)
        aad = f"meridian:evidence:{content_hash}".encode()
        wrapped_key = AESGCM(self._master_key()).encrypt(wrap_nonce, data_key, aad)
        ciphertext = AESGCM(data_key).encrypt(data_nonce, content, aad)
        payload = self.MAGIC + wrap_nonce + data_nonce + wrapped_key + ciphertext

        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(target.parent, 0o700)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=target.parent, delete=False
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(payload)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.chmod(temporary_path, 0o600)
            try:
                os.link(temporary_path, target)
                created = True
            except FileExistsError:
                created = False
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        return StoredBlob(content_hash, mime_type, len(content), str(target), created)

    def read(self, content_hash: str) -> bytes:
        payload = self._path(content_hash).read_bytes()
        if len(payload) < 4 + 12 + 12 + 48 + 16 or payload[:4] != self.MAGIC:
            raise BlobDecryptionError("Evidence blob has an invalid format")
        wrap_nonce = payload[4:16]
        data_nonce = payload[16:28]
        wrapped_key = payload[28:76]
        ciphertext = payload[76:]
        aad = f"meridian:evidence:{content_hash}".encode()
        try:
            data_key = AESGCM(self._master_key()).decrypt(wrap_nonce, wrapped_key, aad)
            return AESGCM(data_key).decrypt(data_nonce, ciphertext, aad)
        except (InvalidTag, ValueError) as exc:
            raise BlobDecryptionError("Evidence blob could not be decrypted") from exc

    def delete(self, content_hash: str) -> bool:
        path = self._path(content_hash)
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        try:
            path.parent.rmdir()
        except OSError:
            pass
        return True

    def _master_key(self) -> bytes:
        key = self._key_provider.get_or_create_key()
        if len(key) != 32:
            raise ValueError("Evidence encryption key must be 32 bytes")
        return key


class DerivedKeyProvider:
    """Deterministic HKDF-derived evidence key from a stable secret."""

    def __init__(self, secret: bytes, label: str = "meridian.evidence.v1"):
        self._secret = secret
        self._label = label

    def get_or_create_key(self) -> bytes:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF

        return HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=self._label.encode(),
        ).derive(self._secret)
