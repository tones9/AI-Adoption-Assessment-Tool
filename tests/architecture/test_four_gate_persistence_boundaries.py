import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "ai_adoption_engine"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_successor_persistence_route_is_not_a_default_dependency() -> None:
    for path in (
        SOURCE / "workspace" / "service.py",
        SOURCE / "workspace" / "composition.py",
        SOURCE / "cli.py",
        ROOT / "streamlit_app.py",
    ):
        assert "ai_adoption_engine.persistence.four_gate" not in _imports(path)


def test_successor_persistence_adapter_does_not_generate_or_reassess() -> None:
    imports = _imports(SOURCE / "persistence" / "four_gate.py")
    forbidden = (
        "ai_adoption_engine.application",
        "ai_adoption_engine.decision",
        "ai_adoption_engine.decision_support",
        "ai_adoption_engine.extraction",
        "ai_adoption_engine.presentation",
        "openai",
        "streamlit",
    )
    assert not any(
        imported == item or imported.startswith(f"{item}.")
        for imported in imports
        for item in forbidden
    )


def test_migration_four_never_updates_legacy_artifact_storage() -> None:
    source = (SOURCE / "persistence" / "migrations.py").read_text(
        encoding="utf-8"
    )
    migration_four = source.split("        4,", 1)[1]
    assert "UPDATE assessment_artifacts" not in migration_four
    assert "UPDATE active_artifacts" not in migration_four
    assert "ALTER TABLE assessment_artifacts" not in migration_four
