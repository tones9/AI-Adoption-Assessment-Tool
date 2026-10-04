import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "ai_adoption_engine"
REVIEW = SOURCE / "supporting_evidence" / "review.py"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_review_service_has_no_bulk_review_api() -> None:
    tree = ast.parse(REVIEW.read_text(encoding="utf-8"))
    method_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "review_proposal" in method_names
    assert not any("bulk" in name or "review_all" in name for name in method_names)


def test_review_service_imports_no_parser_provider_mapping_readiness_or_engine() -> None:
    imports = _imports(REVIEW)
    forbidden = (
        "ai_adoption_engine.ingestion",
        "ai_adoption_engine.extraction",
        "ai_adoption_engine.supporting_evidence.provider",
        "ai_adoption_engine.supporting_evidence.openai",
        "ai_adoption_engine.decision",
        "ai_adoption_engine.presentation",
        "streamlit",
    )
    assert not any(
        imported == item or imported.startswith(f"{item}.")
        for imported in imports
        for item in forbidden
    )
    source = REVIEW.read_text(encoding="utf-8")
    assert "FormalInputMapping" not in source
    assert "FormalInputCandidateSet" not in source
    assert "FormalEvidenceReadiness" not in source


def test_review_service_is_not_activated_by_runtime_defaults() -> None:
    runtime_paths = (
        ROOT / "streamlit_app.py",
        SOURCE / "cli.py",
        SOURCE / "workspace" / "composition.py",
        SOURCE / "workspace" / "service.py",
        SOURCE / "preliminary" / "composition.py",
        SOURCE / "preliminary" / "formal.py",
        SOURCE / "preliminary" / "journey.py",
        SOURCE / "preliminary" / "run.py",
    )
    for path in runtime_paths:
        if path.exists():
            source = path.read_text(encoding="utf-8")
            assert "SupportingEvidenceReviewService" not in source
            assert "supporting_evidence.review" not in source


def test_slice4_adds_no_migration_eight() -> None:
    migrations = (
        SOURCE / "persistence" / "preliminary_migrations.py"
    ).read_text(encoding="utf-8")
    assert "SUPPORTING_EVIDENCE_MIGRATION_8" not in migrations
    assert "migration 8" not in REVIEW.read_text(encoding="utf-8").lower()
