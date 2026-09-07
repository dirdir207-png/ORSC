#!/usr/bin/env python3
"""Collect the real Crew GraphQL operation + field names from the native app's cache.

The native Crew desktop app (com.trycrew.crew) persists every GraphQL request/response
body in its sandbox-local CFNetwork cache (Cache.db + fsCachedData). This script
decodes those bplists and reports the operation names and field names the app has
actually called — the authoritative source of real Crew schema (no invented mutations).

Re-run it after performing an action in the app (create a bill, create a pocket,
top-up reserve) to capture the mutation the app sends.

Never prints cookie/token values — only operation + field names.
"""

from __future__ import annotations

import os
import plistlib
import re
import sqlite3
from pathlib import Path

CONTAINER = (
    Path.home()
    / "Library/Containers/DDD88BDA-24C9-480F-9494-3752276D0EB4/Data"
)
CACHE_DB = CONTAINER / "Library/Caches/com.trycrew.crew/Cache.db"


def _loads(obj):
    """Decode a plist bytes object, or a JSON string, to a python object."""
    if isinstance(obj, (bytes, bytearray)):
        try:
            return plistlib.loads(obj)
        except Exception:
            try:
                return obj.decode("utf-8", "replace")
            except Exception:
                return None
    if isinstance(obj, str):
        return obj
    return obj


def _json_texts(o, out):
    """Collect all JSON-looking (GraphQL request) strings in a nested plist."""
    if isinstance(o, dict):
        for v in o.values():
            _json_texts(v, out)
    elif isinstance(o, list):
        for v in o:
            _json_texts(v, out)
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


def collect(cache_db: Path | None = None) -> dict:
    cache_db = cache_db or CACHE_DB
    ops: set[str] = set()
    fields: set[str] = set()
    store = sqlite3.connect(str(cache_db))
    try:
        rows = store.execute(
            "SELECT entry_ID, request_object, response_object FROM cfurl_cache_blob_data"
        ).fetchall()
    finally:
        store.close()
    for eid, req, resp in rows:
        for blob in (req, resp):
            texts: list[str] = []
            _json_texts(_loads(blob), texts)
            for t in texts:
                m = re.search(r'"operationName"\s*:\s*"([^"]+)"', t)
                if m:
                    ops.add(m.group(1))
                # Field names: camelCase tokens followed by a colon/brace/paren
                for fm in re.findall(r"\b([a-z][A-Za-z0-9_]{1,40})\s*[:{(\[]", t):
                    fields.add(fm)
    return {"operations": sorted(ops), "fields": sorted(fields)}


def main() -> int:
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Collect native Crew GraphQL op/field names")
    ap.add_argument("--out", default=None, help="write JSON summary here")
    args = ap.parse_args()
    data = collect()
    print(f"== Native Crew GraphQL ops ({len(data['operations'])}) ==")
    for o in data["operations"]:
        print("  -", o)
    print(f"\n== Fields ({len(data['fields'])}) ==")
    print("  ", ", ".join(data["fields"]))
    if args.out:
        Path(args.out).write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
