import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = PROJECT_ROOT / "src" / "ai_adoption_engine"


def _imports(path: Path) -> set[str]:
    imports: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_successor_phase5_uses_only_successor_policy_and_engine_entrypoints() -> None:
    path = SOURCE_ROOT / "application" / "four_gate_assessment.py"
    imports = _imports(path)

    assert "ai_adoption_engine.decision.four_gate_engine" in imports
    assert "ai_adoption_engine.decision.four_gate_policy" in imports
    assert "ai_adoption_engine.decision.engine" not in imports
    assert "ai_adoption_engine.decision.policy" not in imports
    assert not any(
        item.startswith(forbidden)
        for item in imports
        for forbidden in (
            "ai_adoption_engine.decision.capabilities",
            "ai_adoption_engine.decision.gates",
            "ai_adoption_engine.decision.scoring",
        )
    )


def test_successor_phase5_has_no_persistence_provider_report_or_ui_imports() -> None:
    paths = (
        SOURCE_ROOT / "application" / "four_gate_assessment.py",
        SOURCE_ROOT / "models" / "four_gate_integrated_assessment.py",
    )
    forbidden = (
        "ai_adoption_engine.persistence",
        "ai_adoption_engine.extraction.providers",
        "ai_adoption_engine.decision_support",
        "ai_adoption_engine.presentation",
        "sqlite3",
        "streamlit",
        "openai",
    )
    for path in paths:
        imports = _imports(path)
        assert not any(
            item == blocked or item.startswith(f"{blocked}.")
            for item in imports
            for blocked in forbidden
        )


def test_legacy_phase5_and_default_entrypoints_do_not_import_successor_route() -> None:
    paths = (
        SOURCE_ROOT / "application" / "assessment.py",
        SOURCE_ROOT / "decision" / "engine.py",
        SOURCE_ROOT / "decision" / "policy.py",
        SOURCE_ROOT / "cli.py",
    )
    for path in paths:
        imports = _imports(path)
        assert not any("four_gate" in item for item in imports)
