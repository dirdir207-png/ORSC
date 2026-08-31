# Task 26 — Meridian Evidence Memory Across Workspaces + Asset/Contract Management — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete Task 26: compose asset/contract/evidence memory into Today, Plan, Activity, and Accounts via per-workspace API endpoints, make evidence content resolve end-to-end, and let the owner manage assets/contracts through the propose→approve→execute pipeline.

**Architecture:** Refactor `meridian/services/memory.py` into a per-workspace composer behind four new `/api/meridian/memory/{workspace}` routes. Add six pipeline action types (`create/update/delete_asset`, `create/update/delete_contract`) with local executors/verifiers so management writes stay approval-gated. Configure the existing `EncryptedBlobStore` in `app.py` so evidence content resolves. Rework `memory.js` to the per-workspace contract and add management forms + approval rendering. No new migration; audit rides the action pipeline.

**Tech Stack:** Python 3.11, Flask 3.1, SQLite, pytest, Playwright, vanilla JS/CSS.

**Spec:** `docs/superpowers/specs/2026-08-31-task26-evidence-memory-design.md`

## Global Constraints

- Work only on branch `feat/meridian-implementation` of `dirdir207-png/ORSC` (local checkout `simplecrew-latest/`). Never touch `main`, the SimpleCrew repos, or anything outside this workspace.
- Proposal-only: no asset/contract change applies without an approved action. Never bypass the pipeline with direct writes.
- No money-movement, commitment, or funding-rule gating changes. No real financial mutation in tests.
- Credentials and secrets never enter payloads, logs, fixtures, docs, or source control. Evidence encryption key derives from `app.secret_key` (already in DB); never log it.
- Evidence integrity: deleting an asset/contract unlinks `evidence_links` but never deletes `evidence_items`; revocation stays soft.
- TDD: every behavior change starts with a failing test; watch it fail; minimal code; watch it pass.
- Migrations: none expected; if one becomes necessary it must be forward-only, idempotent, `BEGIN IMMEDIATE`, numbered `015_*`.
- Sensitive contract kinds (medical/insurance/lease/tax) yield quoted facts/deadlines only — `advisory_boundary` behavior is preserved, never weakened.
- Release gate before claiming done: `ruff check app.py crew meridian tests`, full `pytest`, `pytest tests/meridian`, browser suite, `pip-audit -r requirements.txt`, `docker build -t meridian:task26 .`.
- No fifth primary navigation item; memory lives inside the four workspaces.
- Frontend: existing Editorial-Wealth tokens/primitives; 44px targets; keyboard access; dark + light themes; honest empty states.
- Update `docs/project/CURRENT_STATUS.md` at the end with actual test counts and this plan's commit.

---

### Task 1: Repository update/delete support + evidence unlink

**Files:**
- Modify: `meridian/assets.py`
- Modify: `meridian/contracts.py`
- Modify: `meridian/evidence.py`
- Test: `tests/meridian/test_assets.py`, `tests/meridian/test_contracts.py`, `tests/meridian/test_evidence.py`

**Interfaces:**
- Consumes: existing `AssetRepository`/`ContractRepository`/`EvidenceRepository` patterns (`_connect`, `_asset`/`_record` helpers, `run_migrations`).
- Produces (consumed by Tasks 2, 5, 6):
  - `AssetRepository.update_asset(asset: Asset) -> Asset`
  - `AssetRepository.delete_asset(asset_id: int) -> None`
  - `AssetRepository.replace_warranties(asset_id: int, warranties: list[Warranty]) -> list[Warranty]`
  - `ContractRepository.update_contract(contract: Contract) -> Contract`
  - `ContractRepository.delete_contract(contract_id: int) -> None`
  - `ContractRepository.replace_obligations(contract_id: int, obligations: list[Obligation]) -> list[Obligation]`
  - `EvidenceRepository.remove_links_for_target(target_kind: str, target_id: str) -> int`

- [ ] **Step 1: Write failing tests**

Add to `tests/meridian/test_assets.py`:

```python
def test_update_asset_persists_changed_fields(tmp_path):
    repo = AssetRepository(str(tmp_path / "a.db"))
    saved = repo.save_asset(Asset(
        id=None, name="Laptop", category="electronics",
        purchased_on=None, purchase_price=1500.0, return_until=None,
        maintenance_interval_days=None, replacement_reserve=1200.0,
        evidence_id=None, evidence_span="receipt", confidence=0.98,
    ))
    updated = repo.update_asset(Asset(
        id=saved.id, name="Laptop", category="electronics",
        purchased_on=None, purchase_price=1400.0, return_until=None,
        maintenance_interval_days=180, replacement_reserve=1000.0,
        evidence_id=None, evidence_span="receipt", confidence=1.0,
    ))
    assert updated.id == saved.id
    assert updated.purchase_price == 1400.0
    assert repo.get_asset(saved.id).maintenance_interval_days == 180


def test_delete_asset_cascades_warranties(tmp_path):
    db = str(tmp_path / "a.db")
    repo = AssetRepository(db)
    saved = repo.save_asset(Asset(
        id=None, name="Bike", category="sport", purchased_on=None,
        purchase_price=800.0, return_until=None, maintenance_interval_days=None,
        replacement_reserve=None, evidence_id=None, evidence_span="owner", confidence=1.0,
    ))
    repo.save_warranty(Warranty(
        id=None, asset_id=saved.id, provider="VendorCo",
        expires_on="2027-01-01", deductible=100.0,
        evidence_id=None, evidence_span="owner", confidence=1.0,
    ))
    repo.delete_asset(saved.id)
    assert repo.get_asset(saved.id) is None
    assert repo.list_warranties(saved.id) == []


def test_replace_warranties_replaces_stale(tmp_path):
    db = str(tmp_path / "a.db")
    repo = AssetRepository(db)
    asset = repo.save_asset(Asset(
        id=None, name="Phone", category="electronics", purchased_on=None,
        purchase_price=900.0, return_until=None, maintenance_interval_days=None,
        replacement_reserve=None, evidence_id=None, evidence_span="owner", confidence=1.0,
    ))
    old = repo.save_warranty(Warranty(
        id=None, asset_id=asset.id, provider="OldCo", expires_on="2026-09-01",
        deductible=50.0, evidence_id=None, evidence_span="owner", confidence=1.0,
    ))
    result = repo.replace_warranties(asset.id, [
        Warranty(id=None, asset_id=asset.id, provider="NewCo", expires_on="2027-09-01",
                 deductible=75.0, evidence_id=None, evidence_span="owner", confidence=1.0),
    ])
    assert len(result) == 1 and result[0].provider == "NewCo"
    assert all(w.id != old.id for w in repo.list_warranties(asset.id))
```

Add to `tests/meridian/test_contracts.py`:

```python
def test_update_and_delete_contract_cascades_obligations(tmp_path):
    db = str(tmp_path / "c.db")
    repo = ContractRepository(db)
    saved = repo.save_contract(Contract(
        id=None, kind="lease", name="Apartment lease", starts_on="2026-01-01",
        ends_on="2026-12-31", renews_on=None, cancel_by="2026-11-30",
        escalation_percent=3.0, deductible=None,
        evidence_id=None, evidence_span="owner", confidence=1.0,
    ))
    repo.save_obligation(Obligation(
        id=None, contract_id=saved.id, name="Rent", amount=1800.0,
        due_on="2026-09-01", recurrence="monthly", commitment_id=None,
        evidence_id=None, evidence_span="owner", confidence=1.0,
    ))
    updated = repo.update_contract(Contract(
        id=saved.id, kind="lease", name="Apartment lease", starts_on="2026-01-01",
        ends_on="2027-12-31", renews_on=None, cancel_by="2027-11-30",
        escalation_percent=3.0, deductible=None,
        evidence_id=None, evidence_span="owner", confidence=1.0,
    ))
    assert updated.ends_on == "2027-12-31"
    repo.delete_contract(saved.id)
    assert repo.list_contracts() == []
    assert repo.list_obligations(saved.id) == []


def test_replace_obligations_replaces_stale(tmp_path):
    db = str(tmp_path / "c.db")
    repo = ContractRepository(db)
    contract = repo.save_contract(Contract(
        id=None, kind="insurance", name="Car policy", starts_on="2026-01-01",
        ends_on="2026-12-31", renews_on=None, cancel_by=None,
        escalation_percent=None, deductible=500.0,
        evidence_id=None, evidence_span="owner", confidence=1.0,
    ))
    repo.save_obligation(Obligation(
        id=None, contract_id=contract.id, name="Premium", amount=120.0,
        due_on="2026-09-01", recurrence="monthly", commitment_id=None,
        evidence_id=None, evidence_span="owner", confidence=1.0,
    ))
    result = repo.replace_obligations(contract.id, [
        Obligation(id=None, contract_id=contract.id, name="Premium", amount=125.0,
                   due_on="2026-10-01", recurrence="monthly", commitment_id=None,
                   evidence_id=None, evidence_span="owner", confidence=1.0),
    ])
    assert len(result) == 1 and result[0].amount == 125.0
```

Add to `tests/meridian/test_evidence.py`:

```python
def test_remove_links_for_target_keeps_items(tmp_path):
    db = str(tmp_path / "e.db")
    repo = EvidenceRepository(db)
    item = repo.add_item(source_kind="manual", source_id="seed-1",
                         content_hash="a" * 64, mime_type="text/plain", size_bytes=3)
    repo.add_link(evidence_id=item.id, target_kind="asset", target_id="7",
                  relation="supports", provenance="owner")
    repo.add_link(evidence_id=item.id, target_kind="asset", target_id="8",
                  relation="supports", provenance="owner")
    removed = repo.remove_links_for_target("asset", "7")
    assert removed == 1
    assert repo.list_links_for_target("asset", "7") == []
    assert len(repo.list_links_for_target("asset", "8")) == 1
    assert repo.get_item(item.id) is not None  # item untouched
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/meridian/test_assets.py tests/meridian/test_contracts.py tests/meridian/test_evidence.py -q`
Expected: FAIL — `AttributeError: 'AssetRepository' object has no attribute 'update_asset'` etc.

- [ ] **Step 3: Implement `update_asset` / `delete_asset` / `replace_warranties` in `meridian/assets.py`**

Append inside `AssetRepository` (after `list_corrections`):

```python
    def update_asset(self, asset: Asset) -> Asset:
        if asset.id is None:
            raise ValueError("asset id is required for update")
        timestamp = _now()
        with self._connect() as connection:
            cursor = connection.execute(
                """UPDATE assets SET
                       name=?, category=?, purchased_on=?, purchase_price=?,
                       return_until=?, maintenance_interval_days=?, replacement_reserve=?,
                       evidence_id=?, evidence_span=?, confidence=?, updated_at=?
                   WHERE id=?""",
                (
                    asset.name, asset.category, asset.purchased_on, asset.purchase_price,
                    asset.return_until, asset.maintenance_interval_days,
                    asset.replacement_reserve, asset.evidence_id, asset.evidence_span,
                    asset.confidence, timestamp, asset.id,
                ),
            )
            if cursor.rowcount == 0:
                raise ValueError("asset not found")
            row = connection.execute(
                "SELECT * FROM assets WHERE id=?", (asset.id,)
            ).fetchone()
        return self._asset(row)

    def delete_asset(self, asset_id: int) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM assets WHERE id=?", (asset_id,))

    def replace_warranties(
        self, asset_id: int, warranties: list[Warranty]
    ) -> list[Warranty]:
        timestamp = _now()
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM warranties WHERE asset_id=?", (asset_id,)
            )
            stored = []
            for warranty in warranties:
                cursor = connection.execute(
                    """INSERT INTO warranties(
                           asset_id, provider, expires_on, deductible, evidence_id,
                           evidence_span, confidence, created_at, updated_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        asset_id, warranty.provider, warranty.expires_on,
                        warranty.deductible, warranty.evidence_id,
                        warranty.evidence_span, warranty.confidence, timestamp, timestamp,
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM warranties WHERE id=?", (cursor.lastrowid,)
                ).fetchone()
                values = dict(row)
                values.pop("created_at")
                values.pop("updated_at")
                stored.append(Warranty(**values))
        return stored
```

- [ ] **Step 4: Implement `update_contract` / `delete_contract` / `replace_obligations` in `meridian/contracts.py`**

Append inside `ContractRepository` (after `list_obligations`):

```python
    def get_contract(self, contract_id: int) -> Contract | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM contracts WHERE id=?", (contract_id,)
            ).fetchone()
        return self._record(row, Contract) if row is not None else None

    def update_contract(self, contract: Contract) -> Contract:
        if contract.id is None:
            raise ValueError("contract id is required for update")
        timestamp = _now()
        with self._connect() as connection:
            cursor = connection.execute(
                """UPDATE contracts SET
                       kind=?, name=?, starts_on=?, ends_on=?, renews_on=?, cancel_by=?,
                       escalation_percent=?, deductible=?, evidence_id=?, evidence_span=?,
                       confidence=?, updated_at=?
                   WHERE id=?""",
                (
                    contract.kind, contract.name, contract.starts_on, contract.ends_on,
                    contract.renews_on, contract.cancel_by, contract.escalation_percent,
                    contract.deductible, contract.evidence_id, contract.evidence_span,
                    contract.confidence, timestamp, contract.id,
                ),
            )
            if cursor.rowcount == 0:
                raise ValueError("contract not found")
            row = connection.execute(
                "SELECT * FROM contracts WHERE id=?", (contract.id,)
            ).fetchone()
        return self._record(row, Contract)

    def delete_contract(self, contract_id: int) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM contracts WHERE id=?", (contract_id,)
            )

    def replace_obligations(
        self, contract_id: int, obligations: list[Obligation]
    ) -> list[Obligation]:
        timestamp = _now()
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM obligations WHERE contract_id=?", (contract_id,)
            )
            stored = []
            for obligation in obligations:
                cursor = connection.execute(
                    """INSERT INTO obligations(
                           contract_id, name, amount, due_on, recurrence, commitment_id,
                           evidence_id, evidence_span, confidence, created_at, updated_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        contract_id, obligation.name, obligation.amount, obligation.due_on,
                        obligation.recurrence, obligation.commitment_id,
                        obligation.evidence_id, obligation.evidence_span,
                        obligation.confidence, timestamp, timestamp,
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM obligations WHERE id=?", (cursor.lastrowid,)
                ).fetchone()
                values = dict(row)
                values.pop("created_at")
                values.pop("updated_at")
                stored.append(Obligation(**values))
        return stored
```

- [ ] **Step 5: Implement `remove_links_for_target` in `meridian/evidence.py`**

Append inside `EvidenceRepository` (after `list_links_for_target`):

```python
    def remove_links_for_target(self, target_kind: str, target_id: str) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM evidence_links WHERE target_kind=? AND target_id=?",
                (target_kind, target_id),
            )
        return cursor.rowcount
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python3 -m pytest tests/meridian/test_assets.py tests/meridian/test_contracts.py tests/meridian/test_evidence.py -q`
Expected: PASS (all, including pre-existing).

- [ ] **Step 7: Run the meridian suite and commit**

Run: `python3 -m pytest tests/meridian -q`
Then:

```bash
git add meridian/assets.py meridian/contracts.py meridian/evidence.py \
        tests/meridian/test_assets.py tests/meridian/test_contracts.py tests/meridian/test_evidence.py
git commit -m "feat: asset/contract repository update+delete and evidence unlink"
```

---

### Task 2: Per-workspace memory composer

**Files:**
- Modify: `meridian/services/memory.py`
- Test: `tests/meridian/services/test_memory.py`

**Interfaces:**
- Consumes: `AssetRepository`, `ContractRepository`, `EvidenceRepository`, `asset_events(asset, warranties, *, as_of)`, `contract_events(contract, obligations, *, as_of)`, dataclasses `Asset`, `Contract`, `Warranty`, `Obligation`, `MemoryEvent`.
- Produces (consumed by Task 3):
  - `build_memory(db_path: str, workspace: str, *, as_of: date | None = None) -> dict` — `{"workspace": <str>, "items": [item, ...]}`; raises `ValueError` for unknown workspace.
  - Item dict keys (all workspaces): `id, kind, title, due_on, amount, confidence, urgency, why_it_matters, evidence, reference_transaction_id, escalation_percent`.
  - `evidence` is a list of `{"id": int, "span": str, "confidence": float | None}` resolved from `EvidenceRepository` (`get_item` + link provenance; revoked/expired omitted).
  - Accounts items: `kind` is `"asset"` or `"contract"` and carry the full record fields plus nested `warranties` / `obligations` lists.

- [ ] **Step 1: Rewrite the failing test for the per-workspace contract**

Replace `tests/meridian/services/test_memory.py`:

```python
from datetime import date

from meridian.assets import Asset, AssetRepository
from meridian.contracts import Contract, ContractRepository
from meridian.services.memory import build_memory


def _seed(db_path):
    assets = AssetRepository(db_path)
    saved_asset = assets.save_asset(Asset(
        id=None, name="Laptop", category="electronics", purchased_on="2026-08-01",
        purchase_price=1500, return_until="2026-08-31", maintenance_interval_days=180,
        replacement_reserve=1200, evidence_id=9, evidence_span="receipt", confidence=0.98,
    ))
    assets.save_warranty(_warranty(saved_asset.id))
    contracts = ContractRepository(db_path)
    contracts.save_contract(Contract(
        id=None, kind="insurance", name="Home policy", starts_on="2026-01-01",
        ends_on="2026-12-31", renews_on="2027-01-01", cancel_by="2026-11-30",
        escalation_percent=None, deductible=1000, evidence_id=10,
        evidence_span="declarations", confidence=0.96,
    ))
    return saved_asset


def _warranty(asset_id):
    from meridian.assets import Warranty
    return Warranty(
        id=None, asset_id=asset_id, provider="VendorCo", expires_on="2027-01-01",
        deductible=100.0, evidence_id=None, evidence_span="owner", confidence=1.0,
    )


def test_today_memory_orders_by_urgency_and_carries_evidence(tmp_path):
    db_path = str(tmp_path / "m.db")
    _seed(db_path)
    result = build_memory(db_path, "today", as_of=date(2026, 8, 20))
    assert result["workspace"] == "today"
    kinds = [item["kind"] for item in result["items"]]
    assert kinds[0] == "return_deadline"  # overdue first
    first = result["items"][0]
    assert first["why_it_matters"]
    assert first["evidence"] == [{"id": 9, "span": "receipt", "confidence": 0.98}]
    assert all("reference_transaction_id" in item for item in result["items"])


def test_plan_memory_reserves_and_obligations_with_escalation_field(tmp_path):
    db_path = str(tmp_path / "m.db")
    _seed(db_path)
    result = build_memory(db_path, "plan", as_of=date(2026, 8, 20))
    kinds = {item["kind"] for item in result["items"]}
    assert "replacement_reserve" in kinds
    reserve = next(i for i in result["items"] if i["kind"] == "replacement_reserve")
    assert reserve["amount"] == 1200
    assert "escalation_percent" in reserve  # always present, possibly None


def test_activity_memory_lists_lifecycle_events_without_transactions(tmp_path):
    db_path = str(tmp_path / "m.db")
    _seed(db_path)
    result = build_memory(db_path, "activity", as_of=date(2026, 8, 20))
    assert result["workspace"] == "activity"
    assert all(item["reference_transaction_id"] is None for item in result["items"])


def test_accounts_memory_assets_contracts_with_nested_children(tmp_path):
    db_path = str(tmp_path / "m.db")
    _seed(db_path)
    result = build_memory(db_path, "accounts", as_of=date(2026, 8, 20))
    kinds = {item["kind"] for item in result["items"]}
    assert {"asset", "contract"} <= kinds
    asset = next(i for i in result["items"] if i["kind"] == "asset")
    assert asset["warranties"][0]["provider"] == "VendorCo"


def test_unknown_workspace_raises(tmp_path):
    db_path = str(tmp_path / "m.db")
    _seed(db_path)
    try:
        build_memory(db_path, "nope")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/meridian/services/test_memory.py -q`
Expected: FAIL — `build_memory` accepts no `workspace` argument.

- [ ] **Step 3: Refactor `meridian/services/memory.py`**

Replace the entire file body after the imports with:

```python
from datetime import date
from typing import Any, Dict, List

from meridian.assets import Asset, AssetRepository, Warranty, asset_events
from meridian.contracts import Contract, ContractRepository, contract_events
from meridian.evidence import EvidenceRepository

WORKSPACES = ("today", "plan", "activity", "accounts")


def _evidence_entries(db_path: str, evidence_id: int | None, span: str | None) -> list[Dict[str, Any]]:
    if evidence_id is None:
        return []
    item = EvidenceRepository(db_path).get_item(evidence_id)
    if item is None:
        return []
    return [{"id": item.id, "span": span or item.title or "record", "confidence": None}]


def _urgency(due_on: str | None, as_of: date) -> str | None:
    if due_on is None:
        return None
    try:
        due_date = date.fromisoformat(due_on)
    except ValueError:
        return None
    if due_date < as_of:
        return "overdue"
    if due_date <= as_of.replace(day=15):
        return "upcoming"
    return "future"


def _why_it_matters(event: Any) -> str:
    why = {
        "return_deadline": lambda: f"Return window closes; refund of ${event.amount:.2f} at risk",
        "maintenance_due": lambda: "Scheduled maintenance to preserve asset value and warranty",
        "replacement_reserve": lambda: f"${event.amount:.2f} reserve needed for future replacement",
        "warranty_expiration": lambda: f"Warranty expires; ${event.amount:.2f} deductible applies if claim needed",
        "obligation_due": lambda: f"${event.amount:.2f} payment due under contract",
        "cancellation_deadline": lambda: "Must cancel by this date to avoid auto-renewal charges",
        "renewal": lambda: "Contract renews; review terms and pricing before commitment",
        "escalation_review": lambda: f"{event.amount:.1f}% escalation clause triggers at renewal",
    }.get(event.kind)
    return why() if why else "Requires attention"


def _base_item(event: Any, db_path: str, as_of: date) -> Dict[str, Any]:
    return {
        "id": f"{event.title.lower().replace(' ', '-')}:{event.kind}",
        "kind": event.kind,
        "title": event.title,
        "due_on": event.due_on,
        "amount": event.amount,
        "confidence": event.confidence,
        "urgency": _urgency(event.due_on, as_of),
        "why_it_matters": _why_it_matters(event) if event.due_on else None,
        "evidence": _evidence_entries(db_path, event.evidence_id, None),
        "reference_transaction_id": None,
        "escalation_percent": None,
    }


def _compose_today(events: List[Any], db_path: str, as_of: date) -> List[Dict[str, Any]]:
    items = [_base_item(e, db_path, as_of) for e in events if e.due_on is not None]
    items.sort(key=lambda x: (
        0 if x["urgency"] == "overdue" else (1 if x["urgency"] == "upcoming" else 2),
        x["due_on"] or "9999-12-31",
    ))
    return items


def _compose_plan(events: List[Any], db_path: str) -> List[Dict[str, Any]]:
    items = []
    for event in events:
        item = _base_item(event, db_path, date.today())
        if event.kind == "replacement_reserve" and event.amount is not None:
            item["urgency"] = None
            items.append(item)
        elif event.kind in ("obligation_due", "escalation_review") and event.amount is not None:
            item["urgency"] = None
            items.append(item)
    return items


def _compose_activity(events: List[Any], db_path: str, as_of: date) -> List[Dict[str, Any]]:
    return [_base_item(e, db_path, as_of) for e in events]


def _compose_accounts(
    assets: List[Asset], contracts: List[Contract],
    warranties: List[Warranty], obligations: List[Any], db_path: str,
) -> List[Dict[str, Any]]:
    items = []
    for asset in assets:
        items.append({
            "id": f"asset:{asset.id}",
            "kind": "asset",
            "title": asset.name,
            "due_on": None,
            "amount": asset.purchase_price,
            "confidence": asset.confidence,
            "urgency": None,
            "why_it_matters": None,
            "evidence": _evidence_entries(db_path, asset.evidence_id, asset.evidence_span),
            "reference_transaction_id": None,
            "escalation_percent": None,
            "category": asset.category,
            "purchased_on": asset.purchased_on,
            "return_until": asset.return_until,
            "maintenance_interval_days": asset.maintenance_interval_days,
            "replacement_reserve": asset.replacement_reserve,
            "warranties": [
                {
                    "id": w.id, "provider": w.provider, "expires_on": w.expires_on,
                    "deductible": w.deductible, "confidence": w.confidence,
                    "evidence": _evidence_entries(db_path, w.evidence_id, w.evidence_span),
                }
                for w in warranties if w.asset_id == asset.id
            ],
        })
    for contract in contracts:
        items.append({
            "id": f"contract:{contract.id}",
            "kind": "contract",
            "title": contract.name,
            "due_on": None,
            "amount": None,
            "confidence": contract.confidence,
            "urgency": None,
            "why_it_matters": None,
            "evidence": _evidence_entries(db_path, contract.evidence_id, contract.evidence_span),
            "reference_transaction_id": None,
            "escalation_percent": contract.escalation_percent,
            "contract_kind": contract.kind,
            "starts_on": contract.starts_on,
            "ends_on": contract.ends_on,
            "renews_on": contract.renews_on,
            "cancel_by": contract.cancel_by,
            "deductible": contract.deductible,
            "obligations": [
                {
                    "id": o.id, "name": o.name, "amount": o.amount, "due_on": o.due_on,
                    "recurrence": o.recurrence, "confidence": o.confidence,
                    "evidence": _evidence_entries(db_path, o.evidence_id, o.evidence_span),
                }
                for o in obligations if o.contract_id == contract.id
            ],
        })
    return items


def build_memory(db_path: str, workspace: str, *, as_of: date | None = None) -> Dict[str, Any]:
    if workspace not in WORKSPACES:
        raise ValueError(f"unknown workspace: {workspace}")
    as_of = as_of or date.today()

    asset_repo = AssetRepository(db_path)
    contract_repo = ContractRepository(db_path)
    assets = asset_repo.list_assets()
    warranties = asset_repo.list_warranties()
    contracts = contract_repo.list_contracts()
    obligations = contract_repo.list_obligations()

    all_asset_events = []
    for asset in assets:
        asset_warranties = [w for w in warranties if w.asset_id == asset.id]
        all_asset_events.extend(asset_events(asset, asset_warranties, as_of=as_of))
    all_contract_events = []
    for contract in contracts:
        contract_obligations = [o for o in obligations if o.contract_id == contract.id]
        all_contract_events.extend(contract_events(contract, contract_obligations, as_of=as_of))

    events = all_asset_events + all_contract_events
    composers = {
        "today": lambda: _compose_today(events, db_path, as_of),
        "plan": lambda: _compose_plan(events, db_path),
        "activity": lambda: _compose_activity(events, db_path, as_of),
        "accounts": lambda: _compose_accounts(
            assets, contracts, warranties, obligations, db_path
        ),
    }
    return {"workspace": workspace, "items": composers[workspace]()}
```

> Note: `contract_events` currently drops its `as_of` argument (a pre-existing quirk). Do not fix it in this task; the composer passes `as_of` as today.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/meridian/services/test_memory.py tests/meridian -q`
Expected: PASS. If the existing `tests/meridian/test_contracts.py`/`test_assets.py` rely on old `build_memory` call shapes, they were already updated in Task 1; fix any other caller of `build_memory` (grep `build_memory` — only `memory.py`, tests, and no API route yet).

- [ ] **Step 5: Commit**

```bash
git add meridian/services/memory.py tests/meridian/services/test_memory.py
git commit -m "feat: per-workspace memory composer"
```

---

### Task 3: Memory API routes

**Files:**
- Modify: `meridian/api.py`
- Test: `tests/meridian/test_memory_api.py` (new)

**Interfaces:**
- Consumes: `build_memory(db_path, workspace, *, as_of=None)` (Task 2), `_repository()` returning a repository with `.db_path`, `_safe_read`, `_error`, `meridian_api` blueprint.
- Produces (consumed by Task 8): four routes `GET /api/meridian/memory/{today|plan|activity|accounts}`.

- [ ] **Step 1: Write the failing test**

Create `tests/meridian/test_memory_api.py`:

```python
import pytest

from meridian.api import meridian_api
from meridian.assets import Asset, AssetRepository


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from flask import Flask
    from flask_login import LoginManager

    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.config["MERIDIAN_REPOSITORY_FACTORY"] = lambda: _Repo(str(tmp_path / "m.db"))
    app.register_blueprint(meridian_api, url_prefix="/api/meridian")
    login = LoginManager(app)

    class User:
        @property
        def is_authenticated(self):
            return True

        @property
        def is_active(self):
            return True

        @property
        def is_anonymous(self):
            return False

        def get_id(self):
            return "1"

    @login.user_loader
    def load_user(user_id):
        return User()

    AssetRepository(str(tmp_path / "m.db")).save_asset(Asset(
        id=None, name="Laptop", category="electronics", purchased_on=None,
        purchase_price=1500.0, return_until=None, maintenance_interval_days=None,
        replacement_reserve=1200.0, evidence_id=None, evidence_span="receipt",
        confidence=0.98,
    ))
    return app.test_client()


class _Repo:
    def __init__(self, db_path):
        self.db_path = db_path


def test_memory_today_returns_workspace_items(client):
    response = client.get("/api/meridian/memory/today")
    assert response.status_code == 200
    body = response.get_json()
    assert body["workspace"] == "today"
    assert isinstance(body["items"], list)


def test_memory_unknown_workspace_is_404(client):
    response = client.get("/api/meridian/memory/nope")
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "invalid_request"


def test_memory_requires_auth(tmp_path):
    from flask import Flask
    from flask_login import LoginManager

    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.config["MERIDIAN_REPOSITORY_FACTORY"] = lambda: _Repo(str(tmp_path / "a.db"))
    app.register_blueprint(meridian_api, url_prefix="/api/meridian")
    login = LoginManager(app)

    class Anon:
        is_authenticated = False
        is_active = False
        is_anonymous = True

        def get_id(self):
            return None

    @login.user_loader
    def load_user(user_id):
        return None

    response = app.test_client().get("/api/meridian/memory/today")
    assert response.status_code == 302  # redirected to login
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/meridian/test_memory_api.py -q`
Expected: FAIL — 404 (route missing).

- [ ] **Step 3: Implement the routes in `meridian/api.py`**

Add near the other read routes (after `evidence_content`, line ~548):

```python
@meridian_api.get("/memory/<workspace>")
@login_required
@_safe_read
def memory_workspace(workspace: str):
    from meridian.services.memory import WORKSPACES, build_memory

    if workspace not in WORKSPACES:
        return _error(
            "invalid_request",
            f"Unknown memory workspace: {workspace}",
            "Choose today, plan, activity, or accounts.",
            404,
        )
    payload = build_memory(_repository().db_path, workspace)
    return jsonify(payload)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/meridian/test_memory_api.py tests/meridian/test_api.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add meridian/api.py tests/meridian/test_memory_api.py
git commit -m "feat: per-workspace memory API routes"
```

---

### Task 4: Evidence blob store configured end-to-end

**Files:**
- Modify: `meridian/storage.py`
- Modify: `app.py`
- Test: `tests/test_app_evidence_integration.py` (new)

**Interfaces:**
- Consumes: `EncryptedBlobStore(root, key_provider)` with `read(content_hash)` / `write(...)`; `KeyProvider` protocol (`get_or_create_key() -> bytes`); `app.secret_key` (hex str, app.py:129); route `/api/meridian/evidence/<id>/content` (api.py:513).
- Produces (consumed by Task 7): `DerivedKeyProvider` in `meridian/storage.py`; `MERIDIAN_EVIDENCE_BLOB_STORE_FACTORY` config in `app.py`.

- [ ] **Step 1: Write the failing integration test**

Create `tests/test_app_evidence_integration.py`:

```python
import os

import pytest


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_FILE", str(tmp_path / "app.db"))
    import app as app_module
    app_module.DB_FILE = str(tmp_path / "app.db")
    app_module.app.secret_key = "0123456789abcdef0123456789abcdef"
    from meridian.evidence import EvidenceRepository
    from meridian.storage import EncryptedBlobStore, DerivedKeyProvider

    root = os.path.join(tmp_path, "evidence")
    store = EncryptedBlobStore(root, DerivedKeyProvider(app_module.app.secret_key.encode()))
    repo = EvidenceRepository(app_module.DB_FILE)
    blob = store.put(b"hello evidence", mime_type="text/plain")
    repo.add_item(
        source_kind="manual", source_id="seed-1", content_hash=blob.content_hash,
        mime_type="text/plain", size_bytes=blob.size_bytes, title="Note",
    )
    return app_module.app, repo


def test_evidence_content_resolves(app):
    flask_app, repo = app
    items = repo._connect().execute("SELECT id FROM evidence_items").fetchall()
    item_id = items[0]["id"]
    with flask_app.test_client() as client:
        response = client.get(f"/api/meridian/evidence/{item_id}/content")
        assert response.status_code == 200
        assert response.data == b"hello evidence"
```

> Note: the fixture relies on `app.py` registering `MERIDIAN_EVIDENCE_BLOB_STORE_FACTORY` at import time (Step 3); until then this test fails with 503.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_app_evidence_integration.py -q`
Expected: FAIL — 503 `evidence_storage_unavailable` (factory unset) or import error on `DerivedKeyProvider`.

- [ ] **Step 3: Add `DerivedKeyProvider` to `meridian/storage.py`**

Append to `meridian/storage.py` (after `EncryptedBlobStore`):

```python
import hashlib


class DerivedKeyProvider:
    """Deterministic HKDF-derived evidence key from a stable secret."""

    def __init__(self, secret: bytes, label: str = "meridian.evidence.v1"):
        self._secret = secret
        self._label = label

    def get_or_create_key(self) -> bytes:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF

        return HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=self._label.encode(),
        ).derive(self._secret)
```

- [ ] **Step 4: Configure the factory in `app.py`**

After `app.config["MERIDIAN_REPOSITORY_FACTORY"] = ...` (line 97) add:

```python
def _evidence_store_factory():
    from meridian.storage import DerivedKeyProvider, EncryptedBlobStore

    evidence_root = os.path.join(os.path.dirname(os.path.abspath(DB_FILE)), "evidence")
    return EncryptedBlobStore(evidence_root, DerivedKeyProvider(app.secret_key.encode()))


app.config["MERIDIAN_EVIDENCE_BLOB_STORE_FACTORY"] = _evidence_store_factory
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_app_evidence_integration.py -q`
Expected: PASS.

- [ ] **Step 6: Run app-level tests and commit**

Run: `python3 -m pytest tests/test_app_crew_integration.py tests/test_production_config.py tests/test_legacy_redirects.py -q`
Then:

```bash
git add meridian/storage.py app.py tests/test_app_evidence_integration.py
git commit -m "feat: configure encrypted evidence store end-to-end"
```

---

### Task 5: Pipeline action types and executors for asset/contract management

**Files:**
- Create: `meridian/memory_actions.py`
- Modify: `app.py`
- Test: `tests/meridian/test_memory_actions.py` (new)

**Interfaces:**
- Consumes: `AssetRepository`/`ContractRepository` (Task 1 methods), `EvidenceRepository.remove_links_for_target`, `ActionStore.propose(action_type, params, rationale, requested_by, dedup_key=None)` (crew/actions.py:107), `ExecutorSpec(execute, verifier)` (crew/executors.py:17), `execute_approved_action` / `approve` paths.
- Produces (consumed by Task 6):
  - `MEMORY_ACTION_TYPES: tuple[str, ...]` = `("create_asset","update_asset","delete_asset","create_contract","update_contract","delete_contract")`
  - `asset_executors(db_path: str) -> dict[str, tuple[Callable[[dict], dict], Callable[[dict, dict], dict] | None]]`
  - `contract_executors(db_path: str) -> dict[str, tuple[Callable[[dict], dict], Callable[[dict, dict], dict] | None]]`
  - Executor params contract: create/update carry full record fields; update/delete carry `"record_id"`; delete carries `"change_reason"`; all executors return `{"success": True, ...}`; verifiers return `{"ok": bool, "check": str}`.

- [ ] **Step 1: Write failing tests**

Create `tests/meridian/test_memory_actions.py`:

```python
from crew.actions import ActionStore
from crew.executors import ExecutorSpec, execute_approved_action
from meridian.evidence import EvidenceRepository
from meridian.memory_actions import MEMORY_ACTION_TYPES, asset_executors, contract_executors


def _store_and_executors(db_path):
    store = ActionStore(db_path, allowed_types=MEMORY_ACTION_TYPES)
    executors = {
        **asset_executors(db_path),
        **contract_executors(db_path),
    }
    wrapped = {key: ExecutorSpec(execute=fn, verifier=vf) for key, (fn, vf) in executors.items()}
    return store, wrapped


def test_create_asset_propose_approve_execute_verify(tmp_path):
    db_path = str(tmp_path / "a.db")
    store, executors = _store_and_executors(db_path)
    request = store.propose(
        "create_asset",
        {"name": "Laptop", "category": "electronics", "purchase_price": 1500.0,
         "replacement_reserve": 1200.0, "evidence_span": "owner", "confidence": 1.0},
        "Owner records laptop",
        requested_by="owner",
    )
    store.approve(request["id"], approved_by="owner")
    result = execute_approved_action(store, request["id"], executors)
    assert result["state"] == "verified"
    assert result["result"]["asset_id"]
    from meridian.assets import AssetRepository
    assert AssetRepository(db_path).get_asset(result["result"]["asset_id"]).name == "Laptop"


def test_update_asset_changes_fields(tmp_path):
    from meridian.assets import Asset, AssetRepository

    db_path = str(tmp_path / "u.db")
    repo = AssetRepository(db_path)
    saved = repo.save_asset(Asset(
        id=None, name="Laptop", category="electronics", purchased_on=None,
        purchase_price=1500.0, return_until=None, maintenance_interval_days=None,
        replacement_reserve=1200.0, evidence_id=None, evidence_span="owner", confidence=1.0,
    ))
    store, executors = _store_and_executors(db_path)
    request = store.propose(
        "update_asset",
        {"record_id": saved.id, "name": "Laptop Pro", "category": "electronics",
         "purchase_price": 1400.0, "evidence_span": "owner", "confidence": 1.0,
         "change_reason": "price corrected"},
        "Owner corrects price",
        requested_by="owner",
    )
    store.approve(request["id"], approved_by="owner")
    result = execute_approved_action(store, request["id"], executors)
    assert result["state"] == "verified"
    assert repo.get_asset(saved.id).purchase_price == 1400.0


def test_delete_asset_unlinks_evidence_but_keeps_items(tmp_path):
    from meridian.assets import Asset, AssetRepository

    db_path = str(tmp_path / "d.db")
    repo = AssetRepository(db_path)
    saved = repo.save_asset(Asset(
        id=None, name="Bike", category="sport", purchased_on=None,
        purchase_price=800.0, return_until=None, maintenance_interval_days=None,
        replacement_reserve=None, evidence_id=None, evidence_span="owner", confidence=1.0,
    ))
    evidence = EvidenceRepository(db_path)
    item = evidence.add_item(source_kind="manual", source_id="seed-1",
                             content_hash="b" * 64, mime_type="text/plain", size_bytes=3)
    evidence.add_link(evidence_id=item.id, target_kind="asset",
                      target_id=str(saved.id), relation="supports", provenance="owner")
    store, executors = _store_and_executors(db_path)
    request = store.propose("delete_asset", {"record_id": saved.id, "change_reason": "sold"},
                            "Owner removes bike", requested_by="owner")
    store.approve(request["id"], approved_by="owner")
    result = execute_approved_action(store, request["id"], executors)
    assert result["state"] == "verified"
    assert repo.get_asset(saved.id) is None
    assert evidence.list_links_for_target("asset", str(saved.id)) == []
    assert evidence.get_item(item.id) is not None


def test_illegal_transition_without_approval(tmp_path):
    db_path = str(tmp_path / "i.db")
    store, executors = _store_and_executors(db_path)
    request = store.propose("create_contract",
                            {"kind": "insurance", "name": "Car", "confidence": 1.0},
                            "test", requested_by="owner")
    from crew.actions import IllegalTransitionError
    try:
        execute_approved_action(store, request["id"], executors)
        raise AssertionError("expected IllegalTransitionError")
    except IllegalTransitionError:
        pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/meridian/test_memory_actions.py -q`
Expected: FAIL — `ModuleNotFoundError: meridian.memory_actions`.

- [ ] **Step 3: Implement `meridian/memory_actions.py`**

Create the module:

```python
"""Pipeline executors and verifiers for asset/contract management.

These are local planning-metadata writes: they never contact Crew and never
move money. They stay approval-gated through the shared action pipeline.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from meridian.assets import Asset, AssetRepository, Warranty
from meridian.contracts import Contract, ContractRepository, Obligation
from meridian.evidence import EvidenceRepository

MEMORY_ACTION_TYPES = (
    "create_asset",
    "update_asset",
    "delete_asset",
    "create_contract",
    "update_contract",
    "delete_contract",
)

_ASSET_FIELDS = (
    "name", "category", "purchased_on", "purchase_price", "return_until",
    "maintenance_interval_days", "replacement_reserve", "evidence_id",
    "evidence_span", "confidence",
)
_CONTRACT_FIELDS = (
    "kind", "name", "starts_on", "ends_on", "renews_on", "cancel_by",
    "escalation_percent", "deductible", "evidence_id", "evidence_span", "confidence",
)


def _asset_from_params(params: Dict[str, Any], asset_id: int | None = None) -> Asset:
    return Asset(
        id=asset_id,
        name=params["name"],
        category=params["category"],
        purchased_on=params.get("purchased_on"),
        purchase_price=params.get("purchase_price"),
        return_until=params.get("return_until"),
        maintenance_interval_days=params.get("maintenance_interval_days"),
        replacement_reserve=params.get("replacement_reserve"),
        evidence_id=params.get("evidence_id"),
        evidence_span=params.get("evidence_span") or "owner:managed",
        confidence=params.get("confidence", 1.0),
    )


def _contract_from_params(params: Dict[str, Any], contract_id: int | None = None) -> Contract:
    return Contract(
        id=contract_id,
        kind=params["kind"],
        name=params["name"],
        starts_on=params.get("starts_on"),
        ends_on=params.get("ends_on"),
        renews_on=params.get("renews_on"),
        cancel_by=params.get("cancel_by"),
        escalation_percent=params.get("escalation_percent"),
        deductible=params.get("deductible"),
        evidence_id=params.get("evidence_id"),
        evidence_span=params.get("evidence_span") or "owner:managed",
        confidence=params.get("confidence", 1.0),
    )


def _link_evidence(evidence: EvidenceRepository, target_kind: str, target_id: str, params: Dict[str, Any]) -> None:
    evidence_id = params.get("evidence_id")
    if evidence_id is None:
        return
    evidence.add_link(
        evidence_id=int(evidence_id),
        target_kind=target_kind,
        target_id=str(target_id),
        relation="supports",
        provenance=params.get("evidence_span") or "owner:managed",
    )


def asset_executors(db_path: str) -> Dict[str, tuple[Callable, Callable | None]]:
    repo = AssetRepository(db_path)
    evidence = EvidenceRepository(db_path)

    def create(params):
        record = repo.save_asset(_asset_from_params(params))
        _link_evidence(evidence, "asset", record.id, params)
        return {"success": True, "asset_id": record.id}

    def verify_create(params, result):
        record = repo.get_asset(result.get("asset_id"))
        return {"ok": record is not None and record.name == params["name"], "check": "asset-reread"}

    def update(params):
        record = repo.update_asset(_asset_from_params(params, asset_id=int(params["record_id"])))
        evidence.remove_links_for_target("asset", str(record.id))
        _link_evidence(evidence, "asset", record.id, params)
        return {"success": True, "asset_id": record.id}

    def verify_update(params, result):
        record = repo.get_asset(result.get("asset_id"))
        return {"ok": record is not None and record.name == params["name"], "check": "asset-reread"}

    def delete(params):
        asset_id = int(params["record_id"])
        evidence.remove_links_for_target("asset", str(asset_id))
        repo.delete_asset(asset_id)
        return {"success": True, "deleted": asset_id}

    def verify_delete(params, result):
        return {"ok": repo.get_asset(result.get("deleted")) is None, "check": "asset-gone"}

    return {
        "create_asset": (create, verify_create),
        "update_asset": (update, verify_update),
        "delete_asset": (delete, verify_delete),
    }


def contract_executors(db_path: str) -> Dict[str, tuple[Callable, Callable | None]]:
    repo = ContractRepository(db_path)
    evidence = EvidenceRepository(db_path)

    def create(params):
        record = repo.save_contract(_contract_from_params(params))
        _link_evidence(evidence, "contract", record.id, params)
        return {"success": True, "contract_id": record.id}

    def verify_create(params, result):
        record = repo.get_contract(result.get("contract_id"))
        return {"ok": record is not None and record.name == params["name"], "check": "contract-reread"}

    def update(params):
        record = repo.update_contract(_contract_from_params(params, contract_id=int(params["record_id"])))
        evidence.remove_links_for_target("contract", str(record.id))
        _link_evidence(evidence, "contract", record.id, params)
        return {"success": True, "contract_id": record.id}

    def verify_update(params, result):
        record = repo.get_contract(result.get("contract_id"))
        return {"ok": record is not None and record.name == params["name"], "check": "contract-reread"}

    def delete(params):
        contract_id = int(params["record_id"])
        evidence.remove_links_for_target("contract", str(contract_id))
        repo.delete_contract(contract_id)
        return {"success": True, "deleted": contract_id}

    def verify_delete(params, result):
        return {"ok": repo.get_contract(result.get("deleted")) is None, "check": "contract-gone"}

    return {
        "create_contract": (create, verify_create),
        "update_contract": (update, verify_update),
        "delete_contract": (delete, verify_delete),
    }
```

> Note: `get_contract` is added in Task 1 (Step 4) and used by the verifiers here.

- [ ] **Step 4: Wire into `app.py`**

Modify the `action_store` allowlist (app.py:902-910):

```python
from meridian.memory_actions import MEMORY_ACTION_TYPES, asset_executors, contract_executors

action_store = ActionStore(
    db_path=DB_FILE,
    allowed_types=(
        "move_money",
        "scheduled_move_money",
        "update_funding_rule",
        "create_commitment",
    ) + MEMORY_ACTION_TYPES,
)
```

After `action_executors = { ... }` (ends line 933) add:

```python
for _kind, (_execute, _verify) in {
    **asset_executors(DB_FILE),
    **contract_executors(DB_FILE),
}.items():
    action_executors[_kind] = ExecutorSpec(execute=_execute, verifier=_verify)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/meridian/test_memory_actions.py tests/crew -q`
Expected: PASS (plus pre-existing crew/actions tests).

- [ ] **Step 6: Commit**

```bash
git add meridian/memory_actions.py app.py tests/meridian/test_memory_actions.py
git commit -m "feat: pipeline action types for asset/contract management"
```

---

### Task 6: Management API routes (proposal creation)

**Files:**
- Modify: `meridian/api.py`
- Modify: `app.py`
- Test: `tests/meridian/test_memory_management_api.py` (new)

**Interfaces:**
- Consumes: `MERIDIAN_PROPOSAL_SINK_FACTORY` config (set in app.py) returning `Callable[[str, dict], dict]`; `_error`, `_safe_read`, `meridian_api`.
- Produces (consumed by Task 8): `POST/PATCH/DELETE /api/meridian/assets[/<id>]` and `/contracts[/<id>]` returning `202 {"proposal": {"id": ..., "state": "proposed"}}`.

- [ ] **Step 1: Write failing tests**

Create `tests/meridian/test_memory_management_api.py`:

```python
import pytest
from flask import Flask
from flask_login import LoginManager

from meridian.api import meridian_api


class _User:
    is_authenticated = True
    is_active = True
    is_anonymous = False

    def get_id(self):
        return "1"


@pytest.fixture()
def client(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test-secret"
    captured = {}

    def sink(action_type, params):
        captured["type"] = action_type
        captured["params"] = params
        return {"id": "req-1", "state": "proposed"}

    app.config["MERIDIAN_PROPOSAL_SINK_FACTORY"] = lambda: sink
    app.register_blueprint(meridian_api, url_prefix="/api/meridian")
    login = LoginManager(app)

    @login.user_loader
    def load_user(user_id):
        return _User()

    return app.test_client(), captured


def test_create_asset_proposal(client):
    test_client, captured = client
    response = test_client.post("/api/meridian/assets", json={
        "name": "Laptop", "category": "electronics", "purchase_price": 1500.0,
        "confidence": 1.0,
    })
    assert response.status_code == 202
    assert response.get_json()["proposal"]["state"] == "proposed"
    assert captured["type"] == "create_asset"


def test_update_and_delete_contract_proposals(client):
    test_client, captured = client
    assert test_client.patch("/api/meridian/contracts/3", json={
        "name": "Car policy", "kind": "insurance", "confidence": 1.0,
    }).status_code == 202
    assert captured["type"] == "update_contract"
    assert captured["params"]["record_id"] == 3
    assert test_client.delete("/api/meridian/contracts/3",
                              json={"change_reason": "cancelled"}).status_code == 202
    assert captured["type"] == "delete_contract"


def test_invalid_payload_400(client):
    test_client, _ = client
    response = test_client.post("/api/meridian/assets", json={"name": "x"})  # missing category
    assert response.status_code == 400


def test_unconfigured_sink_503(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.register_blueprint(meridian_api, url_prefix="/api/meridian")
    login = LoginManager(app)

    @login.user_loader
    def load_user(user_id):
        return _User()

    response = app.test_client().post("/api/meridian/assets",
                                      json={"name": "x", "category": "y"})
    assert response.status_code == 503
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/meridian/test_memory_management_api.py -q`
Expected: FAIL — 404 (routes missing).

- [ ] **Step 3: Implement the routes in `meridian/api.py`**

Add after `memory_workspace` (Task 3):

```python
def _proposal_sink():
    factory = current_app.config.get("MERIDIAN_PROPOSAL_SINK_FACTORY")
    if factory is None:
        return None
    return factory()


def _management_payload(action_type: str, params: dict):
    sink = _proposal_sink()
    if sink is None:
        return _error(
            "management_unavailable",
            "Action proposals are not configured.",
            "Start the application with the action pipeline enabled.",
            503,
        )
    try:
        proposal = sink(action_type, params)
    except ValueError as error:
        return _error("invalid_request", str(error), "Review the record and try again.", 400)
    return jsonify({"proposal": {"id": proposal["id"], "state": proposal["state"]}}), 202


@meridian_api.post("/assets")
@login_required
@_safe_read
def create_asset_proposal():
    payload = request.get_json(silent=True) or {}
    if not payload.get("name") or not payload.get("category"):
        return _error("invalid_request", "name and category are required.",
                      "Provide both and try again.", 400)
    return _management_payload("create_asset", payload)


@meridian_api.patch("/assets/<asset_id>")
@login_required
@_safe_read
def update_asset_proposal(asset_id: str):
    payload = request.get_json(silent=True) or {}
    if not payload.get("name") or not payload.get("category"):
        return _error("invalid_request", "name and category are required.",
                      "Provide both and try again.", 400)
    payload["record_id"] = _positive_int(asset_id)
    return _management_payload("update_asset", payload)


@meridian_api.delete("/assets/<asset_id>")
@login_required
@_safe_read
def delete_asset_proposal(asset_id: str):
    payload = request.get_json(silent=True) or {}
    payload["record_id"] = _positive_int(asset_id)
    return _management_payload("delete_asset", payload)


@meridian_api.post("/contracts")
@login_required
@_safe_read
def create_contract_proposal():
    payload = request.get_json(silent=True) or {}
    if not payload.get("name") or not payload.get("kind"):
        return _error("invalid_request", "name and kind are required.",
                      "Provide both and try again.", 400)
    return _management_payload("create_contract", payload)


@meridian_api.patch("/contracts/<contract_id>")
@login_required
@_safe_read
def update_contract_proposal(contract_id: str):
    payload = request.get_json(silent=True) or {}
    if not payload.get("name") or not payload.get("kind"):
        return _error("invalid_request", "name and kind are required.",
                      "Provide both and try again.", 400)
    payload["record_id"] = _positive_int(contract_id)
    return _management_payload("update_contract", payload)


@meridian_api.delete("/contracts/<contract_id>")
@login_required
@_safe_read
def delete_contract_proposal(contract_id: str):
    payload = request.get_json(silent=True) or {}
    payload["record_id"] = _positive_int(contract_id)
    return _management_payload("delete_contract", payload)
```

> `_positive_int` already exists in `meridian/api.py` (used by evidence routes). If not, add it (parse int, raise `ValueError`).

- [ ] **Step 4: Wire the sink in `app.py`**

After the executor registration (Task 5, Step 4) add:

```python
def _meridian_memory_proposal_sink(action_type, params):
    summary = f"Meridian {action_type}: {params.get('name') or params.get('record_id')}"
    return action_store.propose(action_type, params, summary, requested_by="meridian-owner")


app.config["MERIDIAN_PROPOSAL_SINK_FACTORY"] = lambda: _meridian_memory_proposal_sink
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/meridian/test_memory_management_api.py tests/meridian/test_api.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add meridian/api.py app.py tests/meridian/test_memory_management_api.py
git commit -m "feat: asset/contract management proposal API"
```

---

### Task 7: Seed preview data (assets, contracts, evidence)

**Files:**
- Modify: `seed_preview.py`
- Test: `tests/test_seed_preview.py` (new, light)

**Interfaces:**
- Consumes: `seed()` in `seed_preview.py`; `Asset`/`Warranty`/`Contract`/`Obligation` dataclasses; `EvidenceRepository` + `EncryptedBlobStore`/`DerivedKeyProvider`.
- Produces: preview DB populated with 2 assets, 1 warranty, 2 contracts (one insurance, one lease), 1 obligation, 2 evidence items + links so the four memory regions render.

- [ ] **Step 1: Write the failing smoke test**

Create `tests/test_seed_preview.py`:

```python
def test_seed_creates_assets_contracts_and_evidence(tmp_path, monkeypatch):
    import importlib
    import os

    db_path = str(tmp_path / "preview.db")
    monkeypatch.setenv("DB_FILE", db_path)
    seed_preview = importlib.import_module("seed_preview")
    seed_preview.DB = db_path
    seed_preview.seed()

    from meridian.assets import AssetRepository
    from meridian.contracts import ContractRepository
    from meridian.evidence import EvidenceRepository

    assert len(AssetRepository(db_path).list_assets()) == 2
    assert len(ContractRepository(db_path).list_contracts()) == 2
    assert len(EvidenceRepository(db_path)._connect().execute(
        "SELECT id FROM evidence_items").fetchall()) >= 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_seed_preview.py -q`
Expected: FAIL — counts are 0.

- [ ] **Step 3: Extend `seed()` in `seed_preview.py`**

At the end of `seed()` (after the meridian tables are created and `run_migrations` applied) append:

```python
    # ── Asset & contract memory (Task 26) ─────────────────────────────
    from meridian.assets import Asset, AssetRepository, Warranty
    from meridian.contracts import Contract, ContractRepository, Obligation
    from meridian.evidence import EvidenceRepository
    from meridian.storage import DerivedKeyProvider, EncryptedBlobStore

    evidence_root = os.path.join(os.path.dirname(os.path.abspath(DB)), "evidence")
    store = EncryptedBlobStore(evidence_root, DerivedKeyProvider(b"preview-seed-key"))
    evidence = EvidenceRepository(DB)

    receipt_blob = store.put(b"Laptop receipt (preview)", mime_type="text/plain")
    receipt = evidence.add_item(
        source_kind="manual", source_id="preview-receipt",
        content_hash=receipt_blob.content_hash, mime_type="text/plain",
        size_bytes=receipt_blob.size_bytes, title="Laptop receipt",
    )
    policy_blob = store.put(b"Home policy declarations (preview)", mime_type="text/plain")
    policy = evidence.add_item(
        source_kind="manual", source_id="preview-policy",
        content_hash=policy_blob.content_hash, mime_type="text/plain",
        size_bytes=policy_blob.size_bytes, title="Home policy declarations",
    )

    assets = AssetRepository(DB)
    laptop = assets.save_asset(Asset(
        id=None, name="Laptop", category="electronics", purchased_on="2026-08-01",
        purchase_price=1500, return_until="2026-08-31", maintenance_interval_days=180,
        replacement_reserve=1200, evidence_id=receipt.id, evidence_span="receipt",
        confidence=0.98,
    ))
    assets.save_warranty(Warranty(
        id=None, asset_id=laptop.id, provider="VendorCo", expires_on="2027-08-01",
        deductible=100, evidence_id=receipt.id, evidence_span="receipt", confidence=0.98,
    ))
    assets.save_asset(Asset(
        id=None, name="Bike", category="sport", purchased_on="2026-06-15",
        purchase_price=800, return_until=None, maintenance_interval_days=None,
        replacement_reserve=500, evidence_id=None, evidence_span="owner:managed",
        confidence=1.0,
    ))

    contracts = ContractRepository(DB)
    home = contracts.save_contract(Contract(
        id=None, kind="insurance", name="Home policy", starts_on="2026-01-01",
        ends_on="2026-12-31", renews_on="2027-01-01", cancel_by="2026-11-30",
        escalation_percent=None, deductible=1000, evidence_id=policy.id,
        evidence_span="declarations", confidence=0.96,
    ))
    contracts.save_contract(Contract(
        id=None, kind="lease", name="Apartment lease", starts_on="2026-07-01",
        ends_on="2027-06-30", renews_on=None, cancel_by="2027-05-01",
        escalation_percent=3.0, deductible=None, evidence_id=None,
        evidence_span="owner:managed", confidence=1.0,
    ))
    contracts.save_obligation(Obligation(
        id=None, contract_id=home.id, name="Premium", amount=120.0,
        due_on="2026-09-01", recurrence="monthly", commitment_id=None,
        evidence_id=policy.id, evidence_span="declarations", confidence=0.96,
    ))

    evidence.add_link(evidence_id=receipt.id, target_kind="asset",
                      target_id=str(laptop.id), relation="supports", provenance="receipt")
    evidence.add_link(evidence_id=policy.id, target_kind="contract",
                      target_id=str(home.id), relation="supports", provenance="declarations")
```

> Ensure `seed_preview.py` imports `os` at the top (it already does for `DB_FILE`).

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_seed_preview.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add seed_preview.py tests/test_seed_preview.py
git commit -m "feat: seed preview asset/contract/evidence memory"
```

---

### Task 8: Frontend — memory regions, management forms, approval rendering

**Files:**
- Modify: `static/js/meridian/memory.js`
- Create: `static/js/meridian/memory-manage.js`
- Modify: `templates/meridian/partials/accounts.html` (assets/contracts section + management forms)
- Modify: `templates/meridian/partials/today.html`, `plan.html`, `activity.html` (render hooks; regions already exist in `index.html:39-88` as `data-memory-*`)
- Modify: `static/css/meridian/workspaces.css`
- Test: `tests/browser/test_evidence_memory.py` (update), `tests/browser/test_asset_contract_management.py` (new)

**Interfaces:**
- Consumes: the four memory endpoints (Task 3) returning `{"workspace", "items"}`; management endpoints (Task 6) returning `202 {"proposal": {"id","state"}}`; existing action endpoints `GET /api/actions/pending`, `POST /api/actions/<id>/approve`, `POST /api/actions/<id>/execute` (app.py:3729/3821/3837); item field contract from Task 2.
- Produces: working memory regions, management forms, and pending memory-proposal approvals.

- [ ] **Step 1: Write the failing browser tests (RED at the DOM level)**

Update `tests/browser/test_evidence_memory.py` so it asserts the per-workspace contract (regions render items or honest empty state, evidence links present, no fifth nav item). Add `tests/browser/test_asset_contract_management.py`:

```python
import os

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("APP_URL"), reason="APP_URL required")

PLAYWRIGHT = pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser
        browser.close()


def _login(page):
    import requests

    url = os.environ["APP_URL"]
    requests.post(f"{url}/api/auth/login",
                  json={"username": "owner", "password": "meridian-owner-2026"}, timeout=10)
    # session cookie is set on the requests session, not the browser; use the
    # browser login page instead when the fixture user exists:
    page.goto(f"{url}/login")
    page.fill('input[name="username"]', "owner")
    page.fill('input[name="password"]', "meridian-owner-2026")
    page.click('button[type="submit"]')
    page.wait_for_url(f"{url}/meridian*")


def test_asset_management_flow(browser):
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    _login(page)
    page.goto(f"{os.environ['APP_URL']}/meridian?workspace=accounts")
    page.click("[data-testid=add-asset]")
    page.fill("[data-testid=asset-name]", "Test Asset")
    page.select_option("[data-testid=asset-category]", "electronics")
    page.click("[data-testid=submit-asset]")
    page.wait_for_selector("text=proposal created")
    # pending approval surface lists it
    page.goto(f"{os.environ['APP_URL']}/meridian?workspace=activity")
    page.wait_for_selector("[data-testid=pending-memory-proposals]")
    page.click("[data-testid=approve-proposal]")
    page.click("[data-testid=execute-proposal]")
    page.goto(f"{os.environ['APP_URL']}/meridian?workspace=accounts")
    page.wait_for_selector("text=Test Asset")
    page.close()
```

> The browser test requires the preview app running (`run_preview.py` on :8081 with `APP_URL` set). It is part of the final gate, not the unit loop.

- [ ] **Step 2: Run the browser tests against preview to see them fail**

Run (preview app running):
`APP_URL=http://127.0.0.1:8081 python3 -m pytest tests/browser/test_asset_contract_management.py -q`
Expected: FAIL — no `[data-testid=add-asset]` element.

- [ ] **Step 3: Rework `static/js/meridian/memory.js` render path**

Replace the `render`/`renderCategory`/`renderItem` block (memory.js:64-~215) with a per-workspace items renderer:

```javascript
        render(workspace, data) {
            const container = document.querySelector(`[data-memory-${workspace}]`);
            if (!container) return;
            if (!data || !data.items || data.items.length === 0) {
                this.renderEmpty(workspace, container);
                return;
            }
            container.innerHTML = '';
            const list = document.createElement('ul');
            list.className = 'memory-items';
            list.setAttribute('aria-label', `${workspace} memory items`);
            data.items.forEach(item => list.appendChild(this.renderItem(workspace, item)));
            container.appendChild(list);
        },

        renderItem(workspace, item) {
            const li = document.createElement('li');
            li.className = `memory-item memory-item--${item.urgency || 'scheduled'}`;
            li.setAttribute('data-memory-kind', item.kind);

            const title = document.createElement('strong');
            title.textContent = item.title || item.kind;
            li.appendChild(title);

            if (item.why_it_matters) {
                const why = document.createElement('p');
                why.className = 'memory-item__why';
                why.textContent = item.why_it_matters;
                li.appendChild(why);
            }
            if (item.amount !== null && item.amount !== undefined) {
                const amount = document.createElement('span');
                amount.className = 'memory-item__amount';
                amount.textContent = new Intl.NumberFormat('en-US', {
                    style: 'currency', currency: 'USD',
                }).format(item.amount);
                li.appendChild(amount);
            }
            if (item.confidence !== null && item.confidence !== undefined) {
                const confidence = document.createElement('span');
                confidence.className = 'memory-item__confidence';
                confidence.textContent = `${Math.round(item.confidence * 100)}% confidence`;
                li.appendChild(confidence);
            }
            if (Array.isArray(item.evidence) && item.evidence.length > 0) {
                const links = document.createElement('ul');
                links.className = 'memory-item__evidence';
                item.evidence.forEach(entry => {
                    const link = document.createElement('li');
                    const anchor = document.createElement('a');
                    anchor.href = `/api/meridian/evidence/${entry.id}/content`;
                    anchor.textContent = entry.span || 'evidence';
                    anchor.setAttribute('target', '_blank');
                    anchor.setAttribute('rel', 'noopener');
                    link.appendChild(anchor);
                    links.appendChild(link);
                });
                li.appendChild(links);
            }
            return li;
        },
```

Keep `renderEmpty`/`renderError` as-is (they already target the container). Delete `renderCategory`.

- [ ] **Step 4: Add the management + approval module `static/js/meridian/memory-manage.js`**

```javascript
// meridian/memory-manage.js - asset/contract management via pipeline proposals
(function () {
    'use strict';

    const Management = {
        init() {
            document.querySelectorAll('[data-testid=add-asset]').forEach((button) => {
                button.addEventListener('click', () => this.openForm('asset', 'create'));
            });
            document.querySelectorAll('[data-testid=add-contract]').forEach((button) => {
                button.addEventListener('click', () => this.openForm('contract', 'create'));
            });
            this.loadPending();
        },

        async submit(kind, mode, payload) {
            const path = kind === 'asset' ? '/api/meridian/assets' : '/api/meridian/contracts';
            const method = mode === 'create' ? 'POST'
                : mode === 'delete' ? 'DELETE' : 'PATCH';
            const suffix = mode === 'create' ? '' : `/${payload.record_id}`;
            const response = await fetch(`${path}${suffix}`, {
                method,
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            if (!response.ok) {
                const body = await response.json().catch(() => ({}));
                throw new Error((body.error && body.error.message) || `Request failed (${response.status})`);
            }
            return response.json();
        },

        openForm(kind, mode, record) { /* render the form; see partials in Step 5 */ },

        async loadPending() {
            const container = document.querySelector('[data-testid=pending-memory-proposals]');
            if (!container) return;
            const response = await fetch('/api/actions/pending', { credentials: 'same-origin' });
            if (!response.ok) return;
            const body = await response.json();
            const memoryTypes = new Set([
                'create_asset', 'update_asset', 'delete_asset',
                'create_contract', 'update_contract', 'delete_contract',
            ]);
            const pending = (body.actions || body.pending || []).filter(
                (action) => memoryTypes.has(action.type)
            );
            if (pending.length === 0) {
                container.hidden = true;
                return;
            }
            container.hidden = false;
            container.innerHTML = '';
            pending.forEach((action) => {
                const row = document.createElement('div');
                row.className = 'pending-memory-proposal';
                row.setAttribute('data-testid', 'pending-memory-proposal');
                const label = document.createElement('span');
                label.textContent = `${action.type}: ${action.rationale || action.id}`;
                row.appendChild(label);
                const approve = document.createElement('button');
                approve.textContent = 'Approve';
                approve.setAttribute('data-testid', 'approve-proposal');
                approve.addEventListener('click', () => this.decide(action.id, 'approve'));
                row.appendChild(approve);
                const execute = document.createElement('button');
                execute.textContent = 'Execute';
                execute.setAttribute('data-testid', 'execute-proposal');
                execute.disabled = true;
                execute.addEventListener('click', () => this.decide(action.id, 'execute'));
                row.appendChild(execute);
                container.appendChild(row);
            });
        },

        async decide(id, step) {
            await fetch(`/api/actions/${id}/${step}`, {
                method: 'POST', credentials: 'same-origin',
            });
            this.loadPending();
        },
    };

    document.addEventListener('DOMContentLoaded', () => Management.init());
})();
```

> The exact response shape of `GET /api/actions/pending` must be confirmed at implementation time (grep the route); adapt `body.actions || body.pending` to the actual key, and re-enable Execute only after approve succeeds.

- [ ] **Step 5: Add management UI to `templates/meridian/partials/accounts.html`**

Add an "Assets & Contracts" section inside the accounts partial (below the existing account lists):

```html
<section class="memory-management" aria-labelledby="memory-management-title">
  <h2 id="memory-management-title">Assets &amp; Contracts</h2>
  <div class="memory-management__actions">
    <button type="button" data-testid="add-asset">Add asset</button>
    <button type="button" data-testid="add-contract">Add contract</button>
  </div>
  <div data-memory-accounts></div>
  <div data-testid="pending-memory-proposals" hidden></div>
</section>
<script type="module" src="/static/js/meridian/memory-manage.js"></script>
```

- [ ] **Step 6: Add region styles to `static/css/meridian/workspaces.css`**

Append:

```css
/* Task 26 memory regions */
.memory-items { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--m-space-2); }
.memory-item { padding: var(--m-space-3); border: 1px solid var(--m-border); border-radius: var(--m-radius-md); }
.memory-item--overdue { border-color: var(--m-risk); }
.memory-item__why { margin: var(--m-space-1) 0; color: var(--m-ink-muted); }
.memory-item__amount { font-weight: 600; }
.memory-item__confidence { color: var(--m-ink-faint); font-size: 0.85em; }
.memory-item__evidence { margin: var(--m-space-1) 0 0; padding-left: var(--m-space-3); }
.memory-management__actions { display: flex; gap: var(--m-space-2); margin-bottom: var(--m-space-3); }
.pending-memory-proposal { display: flex; gap: var(--m-space-2); align-items: center; padding: var(--m-space-2) 0; }
```

> Use the existing token names actually defined in `tokens.css` (`--space-*`, `--radius-*`, `--border`, `--color-*`, `--text-*`) — verify names at implementation time and align.

- [ ] **Step 7: Run browser tests against preview**

Run (preview app running, seeded via Task 7):
`APP_URL=http://127.0.0.1:8081 python3 -m pytest tests/browser/test_evidence_memory.py tests/browser/test_asset_contract_management.py -q`
Expected: PASS. Also run the full browser folder.

- [ ] **Step 8: Commit**

```bash
git add static/js/meridian/memory.js static/js/meridian/memory-manage.js \
        templates/meridian/partials/accounts.html static/css/meridian/workspaces.css \
        tests/browser/test_evidence_memory.py tests/browser/test_asset_contract_management.py
git commit -m "feat: memory regions, asset/contract management UI, approval rendering"
```

---

### Task 9: Gates, docs, and final commit

**Files:**
- Modify: `docs/project/CURRENT_STATUS.md`

**Interfaces:**
- Consumes: everything from Tasks 1-8.

- [ ] **Step 1: Run the full unit gate**

Run: `python3 -m ruff check app.py crew meridian tests`
Expected: no findings.

Run: `python3 -m pytest tests -q`
Expected: all pass. Record the exact count.

- [ ] **Step 2: Run the focused and browser gates**

Run: `python3 -m pytest tests/meridian -q`
Run (preview app running): `APP_URL=http://127.0.0.1:8081 python3 -m pytest tests/browser -q`
Expected: green.

- [ ] **Step 3: Audit + docker**

Run: `python3 -m pip_audit -r requirements.txt` (expect clean or documented pre-existing advisories).
Run: `docker build -t meridian:task26 .`
Expected: build succeeds.

- [ ] **Step 4: Update `docs/project/CURRENT_STATUS.md`**

Record: Task 26 complete in `feat/meridian-implementation` (commit `<sha>`), actual test counts (from Step 1), the six new action types, the four memory endpoints, evidence store configured, and the remaining owner-only live-acceptance gate. Fix the duplicated Task 26 sentence noted in the docs review.

- [ ] **Step 5: Final commit and push**

```bash
git add docs/project/CURRENT_STATUS.md
git commit -m "docs: record Task 26 evidence-memory completion and test evidence"
git -c http.postBuffer=52428800 push origin feat/meridian-implementation
```

---

## Self-Review Notes

- The spec's §5 error table was corrected (404 for revoked/expired evidence matches the existing route).
- `ContractRepository.get_contract` did not exist; Task 1 now adds it (needed by Task 5 verifiers).
- Blob store write method is `put(content, *, mime_type)` — plan uses `put`, not `write`.
- `GET /api/actions/pending` returns `{"actions": [...]}` (verified app.py:3729-3733); Task 8 reads `body.actions`.
- `_positive_int` exists at `meridian/api.py:163` (used by Task 6 routes).
- Design tokens verified: `--m-space-*`, `--m-radius-*`, `--m-border`, `--m-ink-*`, `--m-risk` (Task 8 CSS uses these).
- `contract_events` ignoring `as_of` is a pre-existing quirk, deliberately not fixed here.
