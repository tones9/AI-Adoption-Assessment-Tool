import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "ai_adoption_engine"
SERVICE_DIRECTORY = SOURCE / "supporting_evidence"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_slice3_services_are_not_activated_by_ui_cli_or_application_defaults() -> None:
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
            assert "supporting_evidence" not in source
            assert "SupportingDocumentIntakeService" not in source
            assert "SupportingEvidenceExtractionService" not in source


def test_dedicated_extraction_does_not_call_process_extraction_service_or_provider() -> None:
    imports = set()
    for path in SERVICE_DIRECTORY.glob("*.py"):
        imports.update(_imports(path))
    forbidden = {
        "ai_adoption_engine.extraction.service",
        "ai_adoption_engine.extraction.provider",
        "ai_adoption_engine.providers.openai",
    }
    assert not imports & forbidden


def test_slice3_modules_do_not_activate_review_mapping_readiness_or_strict_engine() -> None:
    slice3_files = (
        SERVICE_DIRECTORY / "intake.py",
        SERVICE_DIRECTORY / "ingestion.py",
        SERVICE_DIRECTORY / "extraction.py",
        SERVICE_DIRECTORY / "provider.py",
        SERVICE_DIRECTORY / "openai.py",
    )
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in slice3_files
    )
    forbidden_names = (
        "SupportingEvidenceReviewRevision",
        "FormalInputMapping",
        "FormalInputCandidateSet",
        "FormalEvidenceReadiness",
        "StrictFourGate",
        "DecisionPackage",
    )
    assert not any(name in source for name in forbidden_names)


def test_no_migration_eight_and_process_extraction_files_are_unmodified_by_slice3() -> None:
    migration_source = (
        SOURCE / "persistence" / "preliminary_migrations.py"
    ).read_text(encoding="utf-8")
    assert "SUPPORTING_EVIDENCE_MIGRATION_8" not in migration_source
    assert not (ROOT / "config" / "supporting_evidence_extraction.v0.2.json").exists()
    dedicated = (SERVICE_DIRECTORY / "openai.py").read_text(encoding="utf-8")
    assert "OpenAIExtractionProvider" not in dedicated
