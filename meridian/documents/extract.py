"""Deterministic text-first extraction with line-level provenance."""

import io
import re
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Provenance:
    page: int
    region: str
    excerpt: str


@dataclass(frozen=True)
class ExtractedValue:
    field: str
    value: float | str
    confidence: float
    provenance: Provenance


@dataclass(frozen=True)
class ExtractedDocument:
    document_type: str
    text: str
    facts: tuple[ExtractedValue, ...]
    candidates: tuple[ExtractedValue, ...]


_LABELED_AMOUNTS = (
    ("amount_due", re.compile(r"amount\s+due\s*:?\s*\$([\d,]+\.\d{2})", re.I)),
    (
        "statement_total",
        re.compile(r"statement\s+total\s*:?\s*\$([\d,]+\.\d{2})", re.I),
    ),
    ("renewal_amount", re.compile(r"renewal\s+amount\s*:?\s*\$([\d,]+\.\d{2})", re.I)),
    ("net_pay", re.compile(r"net\s+pay\s*:?\s*\$([\d,]+\.\d{2})", re.I)),
    ("total", re.compile(r"\btotal\s*:?\s*\$([\d,]+\.\d{2})", re.I)),
)
_ANY_AMOUNT = re.compile(r"\$([\d,]+\.\d{2})")


def _text_from_blob(
    blob: bytes, mime_type: str, ocr: Callable[[bytes, str], str] | None
) -> str:
    if mime_type == "application/pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(blob))
            return "\f".join(page.extract_text() or "" for page in reader.pages)
        except ImportError as exc:
            raise RuntimeError("pypdf is required for PDF extraction") from exc
    if mime_type in {"image/png", "image/jpeg"}:
        if ocr is None:
            raise RuntimeError("An OCR adapter is required for image extraction")
        return ocr(blob, mime_type)
    return blob.decode("utf-8", errors="replace")


def _document_type(text: str) -> str:
    upper = text.upper()
    for marker, kind in (
        ("PAY STUB", "pay_stub"),
        ("RENEWAL", "renewal"),
        ("STATEMENT", "statement"),
        ("RECEIPT", "receipt"),
        ("BILL", "bill"),
    ):
        if marker in upper:
            return kind
    return "unknown"


def extract_document(
    blob: bytes,
    *,
    mime_type: str,
    ocr: Callable[[bytes, str], str] | None = None,
) -> ExtractedDocument:
    text = _text_from_blob(blob, mime_type, ocr)
    facts = []
    candidates = []
    for page_number, page in enumerate(text.split("\f"), start=1):
        for line_number, line in enumerate(page.splitlines(), start=1):
            provenance = Provenance(page_number, f"line:{line_number}", line.strip())
            labeled = False
            for field, pattern in _LABELED_AMOUNTS:
                match = pattern.search(line)
                if match:
                    facts.append(
                        ExtractedValue(
                            field,
                            float(match.group(1).replace(",", "")),
                            0.98,
                            provenance,
                        )
                    )
                    labeled = True
                    break
            if not labeled:
                for match in _ANY_AMOUNT.finditer(line):
                    candidates.append(
                        ExtractedValue(
                            "amount",
                            float(match.group(1).replace(",", "")),
                            0.5,
                            provenance,
                        )
                    )
    return ExtractedDocument(
        _document_type(text), text, tuple(facts), tuple(candidates)
    )
