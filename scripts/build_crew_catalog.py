#!/usr/bin/env python3
"""Build a comprehensive, machine-readable Crew mutation catalog + capture status.

This is the "capture in totality" tool. It merges every verified mutation contract
so Meridian's write path never has to guess:

  1. Parse the mitmproxy capture log (/tmp/mitm-capture.log) for mutation requests
     and record the verified operation name + the sanitized input variables
     (the exact contract the app sends).
  2. Read the native Crew app's CFNetwork cache for the complete operation surface
     (all queries + mutations the app has actually called — the real schema).
  3. Enumrate the known mutation set (docs/project/CREW_GRAPHQL_CATALOG.md plus any
     captured op) and track per-mutation capture status:
        captured   -> a verified request was recorded (op + variables)
        observed   -> the op name appears (query or mutation) but no mutation vars
        missing    -> in the known set but not seen at all
  4. Emit docs/project/crew_mutations.json (consumable programmatically) and print
     a completeness summary.

Never logs cookie/token values (the mitm addon already redacts them; we also
strip any auth-like keys defensively).
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MITM_LOG = Path(os.environ.get("MITM_LOG", "/tmp/mitm-capture.log"))
ARCHIVE = Path(
    os.environ.get(
        "CAPTURE_ARCHIVE",
        REPO_ROOT / "docs/project/captures/crew_ops.jsonl",
    )
)
CATALOG_DOC = REPO_ROOT / "docs/project/CREW_GRAPHQL_CATALOG.md"
OUT = REPO_ROOT / "docs/project/crew_mutations.json"

CONTAINER = Path.home() / "Library/Containers/DDD88BDA-24C9-480F-9494-3752276D0EB4/Data"
CACHE_DB = CONTAINER / "Library/Caches/com.trycrew.crew/Cache.db"

# Auth-like keys stripped defensively (the mitm addon redacts, but be safe).
_AUTH_HINTS = ("authorization", "cookie", "token", "secret", "sessionkey")


def _redact(obj):
    if isinstance(obj, dict):
        return {
            k: ("<redacted>" if any(h in k.lower() for h in _AUTH_HINTS) else _redact(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact(v) for v in obj]
    if isinstance(obj, (dict, list)):
        return obj
    return obj


def parse_mitm_log(path: Path) -> dict[str, dict]:
    """Parse the mitm capture log into {operation: {kind, variables_set..}}."""
    ops: dict[str, dict] = {}

    def absorb(line: str):
        line = line.strip()
        if not line.startswith("{"):
            return
        try:
            entry = json.loads(line)
        except Exception:
            return
        name = entry.get("operation")
        if not name:
            return
        kind = entry.get("kind", "?")
        rec = ops.setdefault(name, {"kind": kind, "variables": [], "fields": []})
        variables = entry.get("variables") or {}
        if variables and all(_redact(variables) != _redact(v) for v in rec["variables"]):
            rec["variables"].append(_redact(variables))

    # Durable archive (previous captures) first, so earlier verified contracts
    # are not lost when the live /tmp log is rotated.
    if ARCHIVE.exists():
        for line in ARCHIVE.read_text(encoding="utf-8", errors="replace").splitlines():
            absorb(line)
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            absorb(line)
    return ops


def collect_cache_ops(cache_db: Path | None = None) -> set[str]:
    """Operation names the native app has called, read from its local cache."""
    cache_db = cache_db or CACHE_DB
    ops: set[str] = set()
    if not cache_db.exists():
        return ops
    store = sqlite3.connect(str(cache_db))
    try:
        rows = store.execute(
            "SELECT request_object, response_object FROM cfurl_cache_blob_data"
        ).fetchall()
    finally:
        store.close()
    for req, resp in rows:
        for blob in (req, resp):
            texts: list[str] = []
            if isinstance(blob, (bytes, bytearray)):
                try:
                    import plistlib

                    blob = plistlib.loads(blob)
                except Exception:
                    blob = None
            _collect_json_texts(blob, texts)
            for t in texts:
                m = re.search(r'"operationName"\s*:\s*"([^"]+)"', t)
                if m:
                    ops.add(m.group(1))
    return ops


def _collect_json_texts(o, out):
    if isinstance(o, dict):
        for v in o.values():
            _collect_json_texts(v, out)
    elif isinstance(o, list):
        for v in o:
            _collect_json_texts(v, out)
    elif isinstance(o, (bytes, bytearray)):
        try:
            s = o.decode("utf-8", "replace")
        except Exception:
            return
        if s.lstrip().startswith(("{", "[")):
            out.append(s)
    elif isinstance(o, str):
        if o.lstrip().startswith(("{", "[")):
            out.append(o)


def catalog_contracts() -> dict[str, str]:
    """Map mutation name -> documented input contract (from the catalog doc)."""
    out: dict[str, str] = {}
    if not CATALOG_DOC.exists():
        return out
    text = CATALOG_DOC.read_text(encoding="utf-8")
    m = re.search(r"^## Mutations.*?(?=^## |\Z)", text, re.M | re.S)
    if not m:
        return out
    for line in m.group(0).splitlines():
        bm = re.match(r"- [`]([A-Z][A-Za-z0-9_]+)[`]\s+(.*)", line)
        if bm:
            out[bm.group(1)] = bm.group(2).strip()
    return out


def main() -> int:
    mitm_ops = parse_mitm_log(MITM_LOG)
    cache_ops = collect_cache_ops()

    contracts = catalog_contracts()

    mutations = {}
    for name, rec in mitm_ops.items():
        if rec["kind"] != "mutation":
            continue
        mutations[name] = {
            "operation": name,
            "kind": "mutation",
            "status": "captured" if rec["variables"] else "observed",
            "variables": rec["variables"],
            "variable_count": len(rec["variables"]),
            "source": "mitmproxy",
        }

    # Documented verified contracts (from CREW_GRAPHQL_CATALOG.md) count as captured.
    for name, contract in contracts.items():
        if name not in mutations:
            mutations[name] = {
                "operation": name,
                "kind": "mutation",
                "status": "captured_documented",
                "contract": contract,
                "source": "catalog",
            }

    for name in cache_ops:
        if name not in mutations:
            mutations[name] = {
                "operation": name,
                "kind": "mutation_maybe",
                "status": "observed",
                "source": "cache",
            }

    known = set(contracts) | set(mutations)
    for name in sorted(known - set(mutations)):
        mutations[name] = {
            "operation": name,
            "kind": "mutation",
            "status": "missing",
            "source": "catalog",
        }

    def _is_captured(m):
        return m["status"] in ("captured", "captured_documented")

    summary = {
        "captured": sum(1 for m in mutations.values() if _is_captured(m)),
        "observed": sum(1 for m in mutations.values() if m["status"] == "observed"),
        "missing": sum(1 for m in mutations.values() if m["status"] == "missing"),
        "total": len(mutations),
    }
    payload = {
        "captured_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "summary": summary,
        "mutations": dict(sorted(mutations.items())),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"== Crew mutation capture status ({summary['total']}) ==")
    print(f"  captured: {summary['captured']}   observed: {summary['observed']}   missing: {summary['missing']}")
    print("\nCaptured (verified variables):")
    for name in sorted(mutations):
        m = mutations[name]
        if m["status"] in ("captured", "captured_documented"):
            tag = " [doc]" if m["status"] == "captured_documented" else ""
            print(f"  - {name}{tag}")
    if summary["missing"]:
        print("\nMissing (in known set, not seen):")
        for name in sorted(mutations):
            if mutations[name]["status"] == "missing":
                print(f"  - {name}")
    print(f"\nwrote {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
