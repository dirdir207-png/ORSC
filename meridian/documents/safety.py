"""Attachment validation performed before storage or parsing."""

import hashlib
import re
from dataclasses import dataclass
from pathlib import PurePath
from typing import BinaryIO, Protocol


class MalwareScanner(Protocol):
    def scan(self, content: bytes) -> bool: ...


@dataclass(frozen=True)
class ValidationResult:
    accepted: bool
    reason: str | None
    sanitized_filename: str
    declared_mime: str
    detected_mime: str | None
    content_hash: str
    size_bytes: int
    duplicate: bool


_SIGNATURES = (
    (b"%PDF-", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
)
_ALLOWED_MIMES = {mime for _, mime in _SIGNATURES}


def _sanitize_filename(filename: str) -> str:
    basename = PurePath(filename.replace("\\", "/")).name
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", basename).strip("._")
    return sanitized[:180] or "attachment"


def _detected_mime(content: bytes) -> str | None:
    return next(
        (mime for signature, mime in _SIGNATURES if content.startswith(signature)), None
    )


def validate_attachment(
    metadata: dict[str, object],
    stream: BinaryIO,
    *,
    scanner: MalwareScanner,
    max_bytes: int = 20 * 1024 * 1024,
    known_hashes: set[str] | None = None,
) -> ValidationResult:
    declared = str(metadata.get("mime_type") or "")
    filename = _sanitize_filename(str(metadata.get("filename") or "attachment"))
    content = stream.read(max_bytes + 1)
    digest = hashlib.sha256(content).hexdigest()
    detected = _detected_mime(content)

    def result(accepted: bool, reason: str | None) -> ValidationResult:
        return ValidationResult(
            accepted,
            reason,
            filename,
            declared,
            detected,
            digest,
            len(content),
            digest in (known_hashes or set()),
        )

    if len(content) > max_bytes:
        return result(False, "size_limit")
    if declared not in _ALLOWED_MIMES or detected != declared:
        return result(False, "mime_mismatch")
    if not scanner.scan(content):
        return result(False, "malware_detected")
    if detected == "application/pdf" and b"/Encrypt" in content:
        return result(False, "encrypted_document")
    if detected == "image/png" and len(content) >= 24:
        width = int.from_bytes(content[16:20], "big")
        height = int.from_bytes(content[20:24], "big")
        if width * height > 100_000_000:
            return result(False, "decompression_bomb")
    return result(True, None)
