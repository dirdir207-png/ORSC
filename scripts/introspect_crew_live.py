#!/usr/bin/env python3
"""Capture the complete real Crew GraphQL schema by introspecting with the live session.

The native Crew app (React Native / Expo) actively authenticates against
api.trycrew.com/willow/graphql with a Bearer JWT + session cookie held in its
CFNetwork cache. This script reads that auth in-process (never prints it), posts
a `__schema` introspection query, and reports ONLY the schema structure — every
mutation, input type, object type, enum and field name.

Use this to get the authoritative real Crew schema so Meridian wires only
verified mutations (never invented ones). Re-run after the app has authenticated
(any time you've opened the app).

SECURITY: the Bearer token is read from the app cache and used only for this one
HTTP request in-process. It is never printed, logged, or written to disk.
"""

from __future__ import annotations

import json
import os
import plistlib
import re
import sqlite3
from pathlib import Path

ENDPOINT = "https://api.trycrew.com/willow/graphql"
CACHE_DB = (
    Path.home()
    / "Library/Containers/DDD88BDA-24C9-480F-9494-3752276D0EB4/Data"
    / "Library/Caches/com.trycrew.crew/Cache.db"
)

_INTROSPECTION_QUERY = """
query IntrospectionQuery {
  __schema {
    queryType { name }
    mutationType { name }
    subscriptionType { name }
    types {
      kind name
      fields(includeDeprecated: false) { name args { name } type { kind name ofType { kind name ofType { kind name } } } }
      inputFields { name type { kind name ofType { kind name ofType { kind name } } } }
      enumValues { name }
    }
  }
}
"""


def _walk_strings(o, out):
    if isinstance(o, dict):
        for v in o.values():
            _walk_strings(v, out)
    elif isinstance(o, list):
        for v in o:
            _walk_strings(v, out)
    elif isinstance(o, (bytes, bytearray)):
        try:
            out.append(o.decode("utf-8", "replace"))
        except Exception:
            pass
    elif isinstance(o, str):
        out.append(o)


def extract_auth(cache_db: Path | None = None) -> dict:
    """Return {authorization, cookie} from the app's GraphQL cache entry (in-process).

    The CFNetwork plist stores the request headers as plain string values under a
    dict (e.g. /Array[19]/Authorization = 'Bearer eyJ...'). Walk the parsed plist to
    recover the live auth, then use it for one introspection request. The token is
    never printed or written; only its presence is reported.
    """
    cache_db = cache_db or CACHE_DB
    store = sqlite3.connect(str(cache_db))
    try:
        rows = store.execute(
            "SELECT request_object FROM cfurl_cache_blob_data WHERE request_object IS NOT NULL"
        ).fetchall()
    finally:
        store.close()
    auth = cookie = None

    def find(obj) -> None:
        nonlocal auth, cookie
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, str) and k.lower() == "authorization" and v.startswith("Bearer"):
                    auth = v
                elif isinstance(v, str) and k.lower() == "cookie" and "_crew_sessio" in v:
                    cookie = v
                find(v)
        elif isinstance(obj, list):
            for v in obj:
                find(v)
        elif isinstance(obj, (bytes, bytearray)):
            # fallback: scan raw bytes for the header text
            raw = bytes(obj)
            am = re.search(rb"Authorization[\s:]+Bearer\s+([A-Za-z0-9_\-\.~/+]{20,})", raw)
            if am and auth is None:
                auth = "Bearer " + am.group(1).decode("utf-8", "replace")
            cm = re.search(rb"(?i)Cookie[:\s]+([^\r\n]*?_crew_session[^\r\n]*)", raw)
            if cm and cookie is None:
                cookie = cm.group(1).decode("utf-8", "replace")

    for (blob,) in rows:
        try:
            obj = plistlib.loads(blob)
        except Exception:
            obj = bytes(blob)
        find(obj)
        if auth:
            break
    return {"authorization": auth, "cookie": cookie}


def introspect(auth_headers: dict) -> dict:
    import requests
    headers = {"accept": "*/*", "content-type": "application/json"}
    if auth_headers.get("authorization"):
        headers["authorization"] = auth_headers["authorization"]
    if auth_headers.get("cookie"):
        headers["cookie"] = auth_headers["cookie"]  # keep cookie form as-is
    resp = requests.post(
        ENDPOINT,
        headers=headers,
        json={"operationName": "IntrospectionQuery", "variables": {}, "query": _INTROSPECTION_QUERY},
        timeout=25,
    )
    if resp.status_code in (401, 403):
        raise SystemExit(f"Crew rejected introspection ({resp.status_code}) — auth may be stale; reopen the app then retry")
    if resp.status_code != 200:
        raise SystemExit(f"Crew introspection HTTP {resp.status_code}")
    body = resp.json()
    if body.get("errors"):
        raise SystemExit(f"Crew introspection errors: {json.dumps(body['errors'])[:300]}")
    return body.get("data", {}).get("__schema", {})


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Introspect the real Crew GraphQL schema")
    ap.add_argument("--out", default=None, help="write schema JSON here")
    args = ap.parse_args()
    auth = extract_auth()
    if not auth.get("authorization"):
        raise SystemExit("No live Crew auth found in the app cache — open the Crew app and reopen a screen, then retry")
    schema = introspect(auth)
    if args.out:
        Path(args.out).write_text(json.dumps(schema, indent=2), encoding="utf-8")
        print(f"wrote schema to {args.out}")
    types = schema.get("types", [])
    print(f"== REAL Crew GraphQL schema: {len(types)} types ==")
    by_kind = {}
    for t in types:
        by_kind.setdefault(t.get("kind"), []).append(t)
    for kind in ("QUERY", "MUTATION", "INPUT_OBJECT", "OBJECT", "ENUM", "INTERFACE", "UNION", "SCALAR"):
        names = [t["name"] for t in by_kind.get(kind, []) if t.get("name")]
        if names:
            print(f"[{kind}] {len(names)}: {', '.join(sorted(names))[:1000]}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
