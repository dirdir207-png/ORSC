#!/usr/bin/env python3
"""SimpleCrew local assistant.

Turns plain English into action proposals for owner approval:

    ./assistant.py "move $50 from checking to rent for october"

Proposals are inert until approved in the app (Account -> Pending Actions).
"""

import argparse
import os
import sys

from crew.assistant import DEFAULT_BASE_URL, IntentParseError, propose_intent
from crew.propose_key import load_local_key


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Propose a Crew action in plain English.")
    parser.add_argument("text", nargs="?", help='e.g., "move $50 from checking to rent for october"')
    parser.add_argument("--url", default=DEFAULT_BASE_URL, help=f"SimpleCrew base URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--key", default=None, help="Local proposer key (default: auto-read from app database or SIMPLECREW_LOCAL_KEY)")
    parser.add_argument("--db", default=None, help="App database path for key lookup (default: ./data/savings_data.db)")
    args = parser.parse_args(argv)

    if not args.text:
        parser.print_help()
        return 2

    key = (
        args.key
        or os.environ.get("SIMPLECREW_LOCAL_KEY")
        or load_local_key(args.db)
    )

    try:
        result = propose_intent(args.text, base_url=args.url, local_key=key)
    except IntentParseError as exc:
        print(f"✗ {exc}")
        return 1

    print(f"✓ Proposed ({result.get('id', '?')[:8]}…):")
    print(f"    {result.get('summary', '')}")
    print("Approve it in the app: Account → Pending Actions (approvals expire after 1 hour).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
