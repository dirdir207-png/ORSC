from pathlib import Path


def test_memory_uses_existing_four_workspaces_without_fifth_navigation_item():
    root = Path(__file__).parents[2]
    navigation = (root / "templates/meridian/partials/navigation.html").read_text()
    memory = (root / "static/js/meridian/memory.js").read_text()

    assert navigation.count("data-workspace=") == 4
    assert "today" in memory
    assert "plan" in memory
    assert "activity" in memory
    assert "accounts" in memory
    # Per-workspace item contract (Task 2 fields)
    assert "why_it_matters" in memory
    assert "urgency" in memory
    assert "kind" in memory
    assert "amount" in memory
    assert "confidence" in memory


def test_memory_renders_per_workspace_items_with_evidence_links():
    root = Path(__file__).parents[2]
    memory = (root / "static/js/meridian/memory.js").read_text()

    # Render targets each workspace's `[data-memory-<workspace>]` hook.
    assert "data-memory-${workspace}" in memory
    # Renders an honest empty state when there are no items.
    assert "data.items.length === 0" in memory
    assert "renderEmpty" in memory
    # Evidence entries render as links into the evidence content endpoint.
    assert "/api/meridian/evidence/" in memory
    assert "memory-item__evidence" in memory


def test_each_partial_has_a_memory_render_hook():
    root = Path(__file__).parents[2]
    partials = root / "templates/meridian/partials"

    assert "data-memory-today" in (partials / "today.html").read_text()
    assert "data-memory-plan" in (partials / "plan.html").read_text()
    assert "data-memory-activity" in (partials / "activity.html").read_text()
    assert "data-memory-accounts" in (partials / "accounts.html").read_text()


def test_management_module_loads_on_accounts_and_targets_action_pipeline():
    root = Path(__file__).parents[2]
    manage = (root / "static/js/meridian/memory-manage.js").read_text()
    accounts = (root / "templates/meridian/partials/accounts.html").read_text()

    assert 'src="/static/js/meridian/memory-manage.js"' in accounts
    assert 'data-testid="add-asset"' in accounts
    assert 'data-testid="add-contract"' in accounts
    assert "pending-memory-proposals" in manage
    assert "/api/actions/pending" in manage
    assert "/api/meridian/assets" in manage
    assert "/api/meridian/contracts" in manage
