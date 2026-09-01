"""Live Crew snapshot collector for automatic refresh.

Provides a single ``sync_live_crew(db_path)`` callable that the
MeridianRefreshService invokes on its cadence. It shells out to the
CrewWorkAssistant ``crew-readonly snapshot`` CLI (the Keychain-backed
mobile/API auth that Crew supports) and syncs the normalized result into
the Meridian graph. Never logs or returns credential material.
"""

import ast
import subprocess
from typing import Optional

from .sync import SyncReport

# The CrewWorkAssistant connector ships with its own venv; this binary is the
# sanctioned read-only snapshot producer on this Mac.
CREW_READONLY = (
    "/Users/stephenwest/Applications/CrewWorkAssistantOTP/.venv/bin/crew-readonly"
)


def capture_crew_snapshot(binary: str = CREW_READONLY, timeout_seconds: int = 120) -> dict:
    """Run the crew-readonly snapshot CLI and parse its dashboard payload."""
    if not binary:
        # Importing here so the helper can be constructed without the binary.
        from .providers.crewwork import CrewWorkSnapshotAdapter

        raise RuntimeError("crew-readonly binary path is not configured")
    try:
        result = subprocess.run(
            [binary, "snapshot"], capture_output=True, text=True, timeout=timeout_seconds
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("crew-readonly snapshot timed out") from exc
    except OSError as exc:
        raise RuntimeError("crew-readonly binary is not available") from exc
    if result.returncode != 0:
        raise RuntimeError("crew-readonly snapshot failed")
    try:
        return ast.literal_eval(result.stdout)
    except (ValueError, SyntaxError) as exc:
        raise RuntimeError("crew-readonly returned an invalid snapshot") from exc


def sync_live_crew(db_path: str, *, snapshot: Optional[dict] = None, binary: str = CREW_READONLY) -> SyncReport:
    """Pull a live Crew snapshot (or accept one) and sync into ``db_path``."""
    from .providers.crewwork import CrewWorkSnapshotAdapter
    from .repository import FinancialRepository
    from .sync import sync_provider

    dashboard = snapshot if snapshot is not None else capture_crew_snapshot(binary=binary)
    adapter = CrewWorkSnapshotAdapter(dashboard)
    repository = FinancialRepository(db_path)
    return sync_provider(adapter, repository)


def build_sync_once(db_path: str, *, binary: str = CREW_READONLY):
    """Zero-arg callable for MeridianRefreshService tied to ``db_path``."""
    def sync_once() -> SyncReport:
        return sync_live_crew(db_path, binary=binary)
    return sync_once
