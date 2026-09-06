"""Gmail -> evidence intake runner (R28/29 pilot).

Fetches a bounded set of recent Gmail messages via the owner's OAuth token and
stores each as an evidence item (source_kind='mail') through the document-intake
pipeline. Read-only: never mutates Gmail; only stores the message body text as
evidence with sane size limits.

This is a pilot: it reads a small, recent slice and records how Gmail data
populates the evidence layer. It is intentionally conservative (no attachment
download, bounded count, quarantine on oversized/empty).
"""

from __future__ import annotations

from .connectors.gmail_read import GmailEvidence, GmailTransport
from .evidence import EvidenceRepository
from .ingest import IntakeRecord, QuarantineError, ingest_record


def ingest_gmail_recent(
    *,
    transport: GmailTransport,
    evidence_repo: EvidenceRepository,
    max_messages: int = 20,
    transactions=None,
) -> dict[str, object]:
    """Fetch recent Gmail messages and store each as evidence.

    When ``transactions`` is supplied, stored mail evidence is linked to a
    matching transaction by amount (documented charge receipts). Returns a
    sanitized summary: counts stored/duplicate/quarantined/error/linked, plus
    the subject + source_id of each stored item (never the body).
    """
    stored: list[dict[str, str]] = []
    duplicate = 0
    quarantined = 0
    errors = 0
    linked = 0

    messages: list[GmailEvidence] = transport.fetch_recent(max_results=max_messages)
    for msg in messages:
        if not msg.body_text.strip():
            quarantined += 1
            continue
        record = IntakeRecord(
            source_kind="mail",
            source_id=msg.message_id,
            blob=msg.body_text.encode("utf-8"),
            mime_type="text/plain",
            title=f"{msg.subject or 'Gmail message'}",
        )
        try:
            result = ingest_record(record, evidence_repo=evidence_repo)
        except QuarantineError:
            quarantined += 1
            continue
        except Exception:  # noqa: BLE001 - a single bad message must not stop the batch
            errors += 1
            continue
        if result.duplicate:
            duplicate += 1
            continue
        if transactions:
            created = link_mail_evidence_to_transactions(
                evidence_repo=evidence_repo,
                transactions=transactions,
                evidence_id=result.item_id,
                subject=msg.subject or "",
                body=msg.body_text,
            )
            linked += created
        stored.append(
            {
                "id": str(result.item_id),
                "subject": msg.subject or "",
                "sender": msg.sender or "",
                "received_at": msg.received_at or "",
            }
        )

    return {
        "fetched": len(messages),
        "stored": len(stored),
        "duplicate": duplicate,
        "quarantined": quarantined,
        "errors": errors,
        "linked": linked,
        "items": stored,
    }


def ingest_all_gmail_accounts(
    *,
    db_path: str,
    evidence_repo: EvidenceRepository,
    token_client,
    max_messages_per_account: int = 10,
) -> dict[str, object]:
    """Ingest recent Gmail from every connected Gmail account.

    Enumerates all stored Gmail OAuth tokens (multi-account), builds a transport
    for each, and stores each account's recent messages as evidence. Read-only
    Gmail; no mutation. Returns a per-account summary plus a total.
    """
    from .connectors.google_auth import OAuthTokenStore

    store = OAuthTokenStore(db_path)
    accounts = store.list_accounts(kind="gmail")
    total_fetched = 0
    total_stored = 0
    per_account: list[dict[str, object]] = []
    for acct in accounts:
        email = str(acct.get("account_email") or "")
        token = store.get(kind="gmail", account_email=email)
        if not token:
            continue

        def _refresh(_tok=token):
            return token_client.refresh(_tok["refresh_token"])

        transport = GmailTransport(access_token=token["access_token"], refresh=_refresh)
        summary = ingest_gmail_recent(
            transport=transport,
            evidence_repo=evidence_repo,
            max_messages=max_messages_per_account,
        )
        per_account.append({"account_email": email, **summary})
        total_fetched += int(summary["fetched"])
        total_stored += int(summary["stored"])

    return {
        "accounts": per_account,
        "total_fetched": total_fetched,
        "total_stored": total_stored,
    }


def link_mail_evidence_to_transactions(
    *,
    evidence_repo,
    transactions,
    evidence_id: int,
    subject: str,
    body: str | None = None,
    provenance: str = "gmail:amount-match",
) -> int:
    """Link a mail evidence item to a matching transaction by amount.

    Best-effort: searches the subject (and optional body) for a dollar amount
    and links the evidence to any transaction with the same amount. Returns the
    number of links created. Read-only — never mutates a transaction, only adds
    an evidence link so the store/receipt can be traced to the charge.
    """
    import re

    text = f"{subject or ''} {body or ''}"
    # Match $92.75 / $1,234.56 — capture the numeric part (no $, no sign).
    amounts = [float(x.replace(",", "")) for x in re.findall(r"\$([\d,]+\.\d{2})", text)]
    if not amounts:
        return 0
    # Compare on absolute amount: a charge is stored negative, a bill email
    # states the positive amount.
    targets = {abs(float(getattr(t, "amount", 0))) for t in transactions if getattr(t, "amount", None) is not None}
    created = 0
    seen = set()
    for amount in amounts:
        if amount in targets and amount not in seen:
            seen.add(amount)
            for tx in transactions:
                if abs(float(getattr(tx, "amount", 0))) != amount:
                    continue
                try:
                    evidence_repo.add_link(
                        evidence_id=evidence_id,
                        target_kind="transaction",
                        target_id=str(getattr(tx, "id", "")),
                        relation="documents",
                        provenance=provenance,
                    )
                    created += 1
                except Exception:  # noqa: BLE001 - a bad link must not stop intake
                    continue
    return created
