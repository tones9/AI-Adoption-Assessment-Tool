import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "ai_adoption_engine"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_preliminary_store_is_not_a_default_application_dependency() -> None:
    for path in (
        SOURCE / "workspace" / "service.py",
        SOURCE / "workspace" / "composition.py",
        SOURCE / "cli.py",
        ROOT / "streamlit_app.py",
    ):
        imports = _imports(path)
        assert "ai_adoption_engine.persistence.preliminary" not in imports
        assert "ai_adoption_engine.preliminary.run" not in imports
        assert "ai_adoption_engine.preliminary.formal" not in imports


def test_preliminary_migration_namespace_is_not_in_the_strict_repository() -> None:
    assert "preliminary_journey" not in (
        SOURCE / "persistence" / "migrations.py"
    ).read_text(encoding="utf-8")
    assert "preliminary_migrations" not in _imports(
        SOURCE / "persistence" / "sqlite.py"
    )


def test_slice_one_persistence_does_not_import_execution_or_presentation() -> None:
    forbidden = (
        "ai_adoption_engine.application",
        "ai_adoption_engine.decision",
        "ai_adoption_engine.decision_support",
        "ai_adoption_engine.preliminary.evaluator",
        "ai_adoption_engine.presentation",
        "streamlit",
    )
    for path in (
        SOURCE / "persistence" / "preliminary.py",
        SOURCE / "persistence" / "preliminary_migrations.py",
        SOURCE / "persistence" / "preliminary_serialization.py",
    ):
        imports = _imports(path)
        assert not any(
            imported == item or imported.startswith(f"{item}.")
            for imported in imports
            for item in forbidden
        )


def test_formal_start_boundary_imports_no_formal_engine_or_presentation() -> None:
    imports = _imports(SOURCE / "preliminary" / "formal.py")
    forbidden = (
        "ai_adoption_engine.decision",
        "ai_adoption_engine.decision_support",
        "ai_adoption_engine.integration",
        "ai_adoption_engine.presentation",
        "streamlit",
    )
    assert not any(
        imported == item or imported.startswith(f"{item}.")
        for imported in imports
        for item in forbidden
    )
