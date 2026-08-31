from pathlib import Path

import pytest

from meridian.storage import EncryptedBlobStore


class StaticKeyProvider:
    def get_or_create_key(self):
        return b"k" * 32


def test_encrypted_blob_store_deduplicates_without_writing_plaintext(tmp_path):
    store = EncryptedBlobStore(tmp_path / "blobs", StaticKeyProvider())
    plaintext = b"statement account 1234 balance 900"

    first = store.put(plaintext, mime_type="application/pdf")
    second = store.put(plaintext, mime_type="application/pdf")

    assert first.content_hash == second.content_hash
    assert first.path == second.path
    assert first.created is True
    assert second.created is False
    assert plaintext not in Path(first.path).read_bytes()
    assert store.read(first.content_hash) == plaintext


def test_encrypted_blob_store_delete_removes_content(tmp_path):
    store = EncryptedBlobStore(tmp_path / "blobs", StaticKeyProvider())
    blob = store.put(b"receipt", mime_type="image/png")

    assert store.delete(blob.content_hash) is True
    assert store.delete(blob.content_hash) is False
    with pytest.raises(FileNotFoundError):
        store.read(blob.content_hash)
