"""Mitmproxy addon: capture Crew GraphQL operations (op name + input vars).

Scoped to api.trycrew.com /w illow/graphql. Logs every request's operationName,
kind (query/mutation), and — for mutations — the sanitized input variables, plus
the GraphQL field names in the response. Never logs the Authorization token or
cookie values.

Run:
  mitmdump -s crew_mitm_capture.py --listen-port 8899
then route the Crew app's traffic through 127.0.0.1:8899 (and trust the CA).
"""

import json
import os
import re

CREW_HOSTS = ("api.trycrew.com", "crew-prod-api.fly.dev")

# Durable archive: append every captured operation here so verified contracts are
# not lost when the live capture log is rotated. Path override via CAPTURE_ARCHIVE.
_ARCHIVE = os.environ.get(
    "CAPTURE_ARCHIVE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "project", "captures", "crew_ops.jsonl"),
)
_ARCHIVE = os.path.abspath(_ARCHIVE)
_ARCHIVE_DIR = os.path.dirname(_ARCHIVE)


def _write_archive(entry):
    """Append a sanitized operation entry to the durable archive (best-effort)."""
    try:
        os.makedirs(_ARCHIVE_DIR, exist_ok=True)
        with open(_ARCHIVE, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")
    except Exception:  # noqa: BLE001 - capture must never crash the proxy
        pass


def _redact(obj):
    """Deep-copy with auth/token values replaced by <redacted>."""
    if isinstance(obj, dict):
        return {
            k: ("<redacted>" if any(x in k.lower() for x in ("authorization", "cookie", "token", "key", "secret")) else _redact(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact(v) for v in obj]
    return obj


def _op_fields(graphql_text):
    """Extract operation name + a sample of field names from a query document."""
    name = None
    m = re.search(r"(query|mutation|subscription)\s+([A-Za-z_]\w*)", graphql_text)
    kind = m.group(1) if m else "?"
    if m:
        name = m.group(2)
    fields = re.findall(r"\b([a-z][A-Za-z0-9_]{1,40})\s*[:({\[]", graphql_text)
    return kind, name, list(dict.fromkeys(fields))[:80]


def request(flow):
    host = flow.request.host
    if not any(h in host for h in CREW_HOSTS):
        return
    if not flow.request.path or "graphql" not in flow.request.path:
        return
    try:
        body = json.loads(flow.request.content.decode("utf-8", "replace"))
    except Exception:
        return
    kind, name, fields = _op_fields(body.get("query", ""))
    entry = {
        "host": host,
        "operation": name,
        "kind": kind,
        "variables": _redact(body.get("variables") or {}),
        "fields_sample": fields,
    }
    _write_archive(entry)
    # Print a compact but complete line so we can grep by operation name.
    print(json.dumps(entry), flush=True)


def response(flow):
    host = flow.request.host
    if not any(h in host for h in CREW_HOSTS):
        return
    if not flow.request.path or "graphql" not in flow.request.path:
        return
    kind, name, fields = _op_fields(flow.request.text or "")
    print(f"RESP kind={kind} op={name} fields={len(fields)}", flush=True)
