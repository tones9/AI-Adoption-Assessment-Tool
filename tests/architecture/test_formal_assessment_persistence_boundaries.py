import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src/ai_adoption_engine"
PERSISTENCE_FILES = (
    SOURCE / "persistence/formal_assessment.py",
    SOURCE / "persistence/formal_assessment_serialization.py",
    SOURCE / "persistence/formal_assessment_migration.py",
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


def test_repository_imports_no_adapter_engine_provider_ui_or_approval_layer() -> None:
    forbidden = (
        "ai_adoption_engine.formal",
        "ai_adoption_engine.decision",
        "ai_adoption_engine.decision_support",
        "ai_adoption_engine.presentation",
        "ai_adoption_engine.providers",
        "ai_adoption_engine.review.approval",
        "streamlit",
    )
    for path in PERSISTENCE_FILES:
        imports = _imports(path)
        assert not any(
            imported == item or imported.startswith(f"{item}.")
            for imported in imports
            for item in forbidden
        )


def test_repository_contains_no_execution_or_product_authority_logic() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in PERSISTENCE_FILES)
    forbidden = (
        "FormalFourGateInputAdapter",
        "FourGateAssessmentEngine",
        "load_four_gate_policy",
        "DecisionPackage",
        "FormalApproval",
        "APPROVE IMPLEMENTATION",
    )
    assert not {item for item in forbidden if item in source}


def test_formal_assessment_repository_is_not_runtime_activated() -> None:
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
            assert "persistence.formal_assessment" not in source


def test_migration_eight_is_outside_ordinary_preliminary_migrations() -> None:
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
    assert "FORMAL_ASSESSMENT_MIGRATION" not in source


def test_strict_persistence_has_no_formal_assessment_dependency() -> None:
    for relative in (
        "persistence/migrations.py",
        "persistence/sqlite.py",
        "persistence/serialization.py",
    ):
        source = (SOURCE / relative).read_text(encoding="utf-8")
        assert "formal_assessment" not in source
