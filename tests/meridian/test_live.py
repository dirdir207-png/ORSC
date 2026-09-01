"""Tests for meridian.live sync_live_crew."""

from meridian.live import build_sync_once, sync_live_crew
from meridian.providers.crewwork import CrewWorkSnapshotAdapter

SNAPSHOT = {
    "mode": "read-only",
    "source": "crew",
    "captured_at": "2026-09-01T14:00:00Z",
    "complete": True,
    "mutations_enabled": False,
    "data": {
        "accounts": {"data": {"currentUser": {"accounts": [{"id": "acc1", "displayName": "Checking"}]}}},
        "pockets": {
            "data": {
                "currentUser": {
                    "accounts": [
                        {
                            "id": "acc1",
                            "displayName": "Checking",
                            "subaccounts": [
                                {
                                    "id": "pock1",
                                    "displayName": "Checking",
                                    "overallBalance": 12000,
                                    "clearedBalance": 12000,
                                    "isPrimary": True,
                                    "status": "ACTIVATED",
                                }
                            ],
                        }
                    ]
                }
            }
        },
        "transactions": {
            "data": {
                "account": {
                    "id": "acc1",
                    "cashTransactions": {
                        "edges": [],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    },
                }
            }
        },
    },
}


def test_sync_live_crew_with_injected_snapshot(tmp_path):
    db = tmp_path / "meridian.db"
    report = sync_live_crew(str(db), snapshot=SNAPSHOT)
    assert report.status == "complete"
    assert report.errors == 0
    # One pocket account plus the synthetic parent-account fallback.
    assert report.accounts_synced == 2


def test_build_sync_once_is_a_callable(tmp_path):
    db = tmp_path / "meridian.db"
    sync_once = build_sync_once(str(db))
    report = sync_once()
    assert report.provider == "crew"
