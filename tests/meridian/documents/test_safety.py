import io

from meridian.documents.safety import validate_attachment


class CleanScanner:
    def scan(self, content):
        return b"EICAR" not in content


def test_attachment_validation_accepts_pdf_and_sanitizes_filename():
    result = validate_attachment(
        {"filename": "../../August Statement.pdf", "mime_type": "application/pdf"},
        io.BytesIO(b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF"),
        scanner=CleanScanner(),
    )

    assert result.accepted is True
    assert result.sanitized_filename == "August_Statement.pdf"
    assert result.detected_mime == "application/pdf"
    assert len(result.content_hash) == 64


def test_attachment_validation_rejects_spoofing_encryption_malware_and_size():
    spoofed = validate_attachment(
        {"filename": "statement.pdf", "mime_type": "application/pdf"},
        io.BytesIO(b"not a pdf"),
        scanner=CleanScanner(),
    )
    encrypted = validate_attachment(
        {"filename": "locked.pdf", "mime_type": "application/pdf"},
        io.BytesIO(b"%PDF-1.7\n/Encrypt 4 0 R\n%%EOF"),
        scanner=CleanScanner(),
    )
    malware = validate_attachment(
        {"filename": "receipt.png", "mime_type": "image/png"},
        io.BytesIO(b"\x89PNG\r\n\x1a\nEICAR"),
        scanner=CleanScanner(),
    )
    oversized = validate_attachment(
        {"filename": "large.jpg", "mime_type": "image/jpeg"},
        io.BytesIO(b"\xff\xd8\xff" + b"x" * 20),
        scanner=CleanScanner(),
        max_bytes=10,
    )

    assert spoofed.reason == "mime_mismatch"
    assert encrypted.reason == "encrypted_document"
    assert malware.reason == "malware_detected"
    assert oversized.reason == "size_limit"


def test_attachment_validation_marks_known_hash_as_duplicate():
    content = b"%PDF-1.7\n%%EOF"
    first = validate_attachment(
        {"filename": "one.pdf", "mime_type": "application/pdf"},
        io.BytesIO(content),
        scanner=CleanScanner(),
    )
    second = validate_attachment(
        {"filename": "two.pdf", "mime_type": "application/pdf"},
        io.BytesIO(content),
        scanner=CleanScanner(),
        known_hashes={first.content_hash},
    )

    assert second.accepted is True
    assert second.duplicate is True
