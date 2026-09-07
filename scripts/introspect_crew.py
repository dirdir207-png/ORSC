#!/usr/bin/env python3
"""Introspect the live Crew GraphQL schema to capture real operation/field names.

Runs a `__schema { ... }` introspection query against the Crew endpoint using the
stored (Keychain-encrypted) session cookie, then prints every type name, its
kind (OBJECT/INPUT_OBJECT/ENUM/etc.), and — for object/input/enum types — the
field or value names. This is how we capture the REAL mutation + field names so
Meridian wires only verified operations (never invented ones).

The session cookie is loaded via the same SessionCredentialStore the broker uses
(encrypted in the Keychain). If the session is stale the endpoint returns 401 and
we re-authenticate through the browser capturer.

Never prints cookie values or tokens — only schema structure.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from crew.mac_secrets import MacKeychainKeyProvider
from crew.session_credentials import SessionCipher, SessionCredentialStore

# Only these keys are captured from the introspection result; never the raw body.
_INTROSPECTION_QUERY = """
query IntrospectionQuery {
  __schema {
    queryType { name }
    mutationType { name }
    subscriptionType { name }
    types {
      kind
      name
      fields(includeDeprecated: false) {
        name
        type { kind name ofType { kind name ofType { kind name } } }
      }
      inputFields {
        name
        type { kind name ofType { kind name ofType { kind name } } }
      }
      enumValues { name }
    }
  }
}
"""


def load_credential(database: Path):
    store = SessionCredentialStore(
        str(database), SessionCipher(MacKeychainKeyProvider())
    )
    return store.load()


def introspect(database: Path, endpoint: str, timeout: int = 20) -> dict:
    import requests

    from crew.transports import SessionCookieTransport

    credential = load_credential(database)
    if credential is None:
        raise SystemExit("No stored Crew session credential — run the browser capturer to authenticate")
    transport = SessionCookieTransport(
        lambda: credential, endpoint=endpoint, timeout_seconds=timeout
    )
    response = transport.session.post(
        endpoint,
        headers={"accept": "*/*", "content-type": "application/json"},
        json={
            "operationName": "IntrospectionQuery",
            "variables": {},
            "query": _INTROSPECTION_QUERY,
        },
        timeout=timeout,
    )
    if response.status_code in (401, 403):
        raise SystemExit(
            "Crew session is stale (401/403) — re-authenticate via the browser "
            "capturer, then re-run this script."
        )
    if response.status_code != 200:
        raise SystemExit(f"Crew introspection returned HTTP {response.status_code}")
    body = response.json()
    if body.get("errors"):
        raise SystemExit(f"Crew introspection errors: {json.dumps(body['errors'])[:400]}")
    return body.get("data") or {}


def shape(kind, name, oftype):
    """Render a type reference compactly."""
    if kind == "NON_NULL":
        return f"{shape(oftype['kind'], oftype['name'], oftype.get('ofType'))}!"
    if kind == "LIST":
        return f"[{shape(oftype['kind'], oftype['name'], oftype.get('ofType'))}]"
    return name or kind


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Capture the real Crew GraphQL schema")
    ap.add_argument("--database", default=None, help="path to simplecrew.db (session store)")
    ap.add_argument("--endpoint", default="https://api.trycrew.com/willow/graphql")
    ap.add_argument("--out", default=None, help="write the full schema JSON here")
    args = ap.parse_args()

    db = Path(args.database) if args.database else (
        Path.home() / "Library/Application Support/SimpleCrew/simplecrew.db"
    )
    data = introspect(db, args.endpoint)
    schema = data.get("__schema", {})
    if args.out:
        Path(args.out).write_text(json.dumps(schema, indent=2), encoding="utf-8")
        print(f"wrote full schema to {args.out}")

    types = schema.get("types", [])
    print(f"== Crew GraphQL schema: {len(types)} types ==")
    print(f"query: {schema.get('queryType', {}).get('name')}  "
          f"mutation: {schema.get('mutationType', {}).get('name')}")
    print()

    # Grouped summary for quick reading.
    by_kind = {}
    for t in types:
        by_kind.setdefault(t.get("kind"), []).append(t)
    for kind in ("MUTATION", "INPUT_OBJECT", "OBJECT", "ENUM", "INTERFACE", "UNION", "SCALAR"):
        names = [t["name"] for t in by_kind.get(kind, []) if t.get("name")]
        if names:
            print(f"[{kind}] {len(names)}: {', '.join(sorted(names))[:900]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
