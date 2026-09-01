"""Sync live Crew data into the Meridian preview DB.

Uses the CrewWorkAssistant ``crew-readonly snapshot`` CLI (Keychain-backed
mobile/API auth) — the reliable Crew data path that Crew supports (JWT +
Stytch session token, no browser cookie anti-fraud loop).

Usage:  python3 scripts/meridian_sync_live.py [DB_FILE]
"""
import ast
import subprocess
import sys

CREW_READONLY = "/Users/stephenwest/Applications/CrewWorkAssistantOTP/.venv/bin/crew-readonly"
DB_FILE = sys.argv[1] if len(sys.argv) > 1 else "/tmp/gate-preview/gate.db"


def main() -> int:
    sys.path.insert(0, ".")
    from meridian.providers.crewwork import CrewWorkSnapshotAdapter
    from meridian.sync import sync_provider
    from meridian.repository import FinancialRepository

    try:
        result = subprocess.run([CREW_READONLY, "snapshot"], capture_output=True, text=True, timeout=120)
    except Exception as exc:
        print(f"❌ crew-readonly snapshot failed: {exc}")
        return 1
    if result.returncode != 0:
        print(f"❌ crew-readonly error: {result.stderr[:300]}")
        return 1

    try:
        dashboard = ast.literal_eval(result.stdout)
    except Exception as exc:
        print(f"❌ could not parse snapshot: {exc}")
        return 1

    adapter = CrewWorkSnapshotAdapter(dashboard)
    repo = FinancialRepository(DB_FILE)
    report = sync_provider(adapter, repo)
    print(
        f"✅ sync provider={report.provider} status={report.status} "
        f"accounts={report.accounts_synced} transactions={report.transactions_synced} errors={report.errors}"
    )
    return 0 if report.status == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
