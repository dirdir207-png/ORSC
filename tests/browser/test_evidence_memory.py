from pathlib import Path


def test_memory_uses_existing_four_workspaces_without_fifth_navigation_item():
    root = Path(__file__).parents[2]
    navigation = (root / "templates/meridian/partials/navigation.html").read_text()
    shell = (root / "templates/meridian/index.html").read_text()
    memory = (root / "static/js/meridian/memory.js").read_text()

    assert navigation.count("data-workspace=") == 4
    assert 'src="/static/js/meridian/memory.js"' in shell
    assert "today" in memory
    assert "plan" in memory
    assert "activity" in memory
    assert "accounts" in memory
    assert "why_it_matters" in memory
    assert "evidence_url" in memory


def test_memory_has_mobile_safe_attention_and_structure_regions():
    root = Path(__file__).parents[2]
    shell = (root / "templates/meridian/index.html").read_text()

    assert "data-memory-today" in shell
    assert "data-memory-plan" in shell
    assert "data-memory-activity" in shell
    assert "data-memory-accounts" in shell
