import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src/ai_adoption_engine"
PERSISTENCE_FILES = (
    SOURCE / "persistence/formal_evidence.py",
    SOURCE / "persistence/formal_evidence_serialization.py",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_supporting_evidence_persistence_imports_no_runtime_or_execution_layer() -> None:
    forbidden = (
        "ai_adoption_engine.application",
        "ai_adoption_engine.decision",
        "ai_adoption_engine.decision_support",
        "ai_adoption_engine.preliminary.evaluator",
        "ai_adoption_engine.presentation",
        "ai_adoption_engine.providers",
        "streamlit",
    )
    for path in PERSISTENCE_FILES:
        imports = _imports(path)
        assert not any(
            imported == item or imported.startswith(f"{item}.")
            for imported in imports
            for item in forbidden
        )


def test_supporting_evidence_repository_is_not_runtime_activated() -> None:
    runtime_paths = (
        ROOT / "streamlit_app.py",
        SOURCE / "cli.py",
        SOURCE / "workspace/composition.py",
        SOURCE / "workspace/service.py",
        SOURCE / "preliminary/composition.py",
        SOURCE / "preliminary/formal.py",
        SOURCE / "preliminary/journey.py",
        SOURCE / "preliminary/run.py",
    )
    for path in runtime_paths:
        if path.exists():
            source = path.read_text(encoding="utf-8")
            assert "persistence.formal_evidence" not in source


def test_migration_seven_is_not_in_ordinary_preliminary_migration_list() -> None:
    source = (SOURCE / "persistence/preliminary_migrations.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "PRELIMINARY_JOURNEY_STORE_MIGRATIONS"
    )
    versions = [item.elts[0].value for item in assignment.value.elts]
    assert versions == [1, 2, 3, 4, 5, 6]
    assert "SUPPORTING_EVIDENCE_MIGRATION" in source


def test_strict_migration_module_has_no_supporting_evidence_dependency() -> None:
    strict_migrations = SOURCE / "persistence/migrations.py"
    assert "formal_evidence" not in strict_migrations.read_text(encoding="utf-8")
