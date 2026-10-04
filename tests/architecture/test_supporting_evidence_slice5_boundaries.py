import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "ai_adoption_engine"
CONVERSION = SOURCE / "supporting_evidence" / "conversion.py"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_slice5_has_explicit_mapping_candidate_and_readiness_apis() -> None:
    tree = ast.parse(CONVERSION.read_text(encoding="utf-8"))
    methods = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert {
        "get_mapping_queue",
        "map_reviewed_evidence",
        "mark_reviewed_evidence_context_only",
        "get_mapping_history",
        "prepare_candidate_set",
        "evaluate_and_persist_readiness",
        "get_current_preparation_state",
    } <= methods
    assert not any("bulk" in name for name in methods)


def test_slice5_imports_no_ui_provider_parser_preliminary_or_strict_engine() -> None:
    imports = _imports(CONVERSION)
    forbidden = (
        "streamlit",
        "ai_adoption_engine.presentation",
        "ai_adoption_engine.ingestion",
        "ai_adoption_engine.extraction",
        "ai_adoption_engine.supporting_evidence.provider",
        "ai_adoption_engine.preliminary",
        "ai_adoption_engine.decision",
        "ai_adoption_engine.phase5",
        "ai_adoption_engine.phase6",
    )
    assert not any(
        imported == item or imported.startswith(f"{item}.")
        for imported in imports
        for item in forbidden
    )


def test_slice5_is_not_activated_by_runtime_defaults() -> None:
    runtime_paths = (
        ROOT / "streamlit_app.py",
        SOURCE / "cli.py",
        SOURCE / "workspace" / "composition.py",
        SOURCE / "workspace" / "service.py",
        SOURCE / "preliminary" / "composition.py",
        SOURCE / "preliminary" / "formal.py",
    )
    for path in runtime_paths:
        if path.exists():
            source = path.read_text(encoding="utf-8")
            assert "SupportingEvidenceFormalInputService" not in source
            assert "supporting_evidence.conversion" not in source


def test_slice5_reuses_migration_seven_and_frozen_contract_identities() -> None:
    migrations = (SOURCE / "persistence" / "preliminary_migrations.py").read_text(
        encoding="utf-8"
    )
    models = (SOURCE / "models" / "formal_evidence.py").read_text(
        encoding="utf-8"
    )
    conversion = CONVERSION.read_text(encoding="utf-8")
    assert "SUPPORTING_EVIDENCE_MIGRATION_8" not in migrations
    assert "migration 8" not in conversion.lower()
    for identity in (
        "formal-input-mapping.v0.1",
        "formal-input-candidate-set.v0.1",
        "formal-evidence-readiness.v0.1",
    ):
        assert identity in models
