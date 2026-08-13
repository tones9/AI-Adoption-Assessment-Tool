import ast
from pathlib import Path

from ai_adoption_engine.decision.engine import AssessmentEngine
from ai_adoption_engine.extraction.service import ProcessExtractionService
from ai_adoption_engine.ingestion.text import ingest_raw_text
from ai_adoption_engine.models.candidate_process import CandidateBusinessProcess
from ai_adoption_engine.models.process import BusinessProcess
from tests.fakes.extraction_provider import (
    ScriptedExtractionProvider,
    raw_chunk,
    raw_step,
)


def test_extraction_source_has_no_phase1_engine_or_policy_imports() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "ai_adoption_engine" / "extraction"
    forbidden = {
        "ai_adoption_engine.decision",
        "ai_adoption_engine.models.assessment",
        "ai_adoption_engine.models.process",
    }
    imported: set[str] = set()
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
    assert not any(
        imported_name == item or imported_name.startswith(f"{item}.")
        for imported_name in imported
        for item in forbidden
    )


def test_candidate_model_is_not_validated_business_process() -> None:
    assert not issubclass(CandidateBusinessProcess, BusinessProcess)
    candidate_fields = set(CandidateBusinessProcess.model_fields)
    assert "candidate_status" in candidate_fields
    assert "recommendation" not in candidate_fields
    assert "priority" not in candidate_fields


def test_phase2_document_remains_extraction_free() -> None:
    result = ingest_raw_text("Document only")
    assert result.document is not None
    assert not hasattr(result.document, "candidate_status")
    assert not hasattr(result.document, "steps")


def test_extraction_runtime_never_invokes_assessment_engine(monkeypatch) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Phase 1 decision engine was invoked by Phase 3")

    monkeypatch.setattr(AssessmentEngine, "assess", fail_if_called)
    ingestion = ingest_raw_text("Agent records the complaint.")
    assert ingestion.document is not None
    provider = ScriptedExtractionProvider(
        [
            raw_chunk(
                raw_step(
                    local_step_id="one",
                    activity="Record complaint",
                    block_id="t-b0001",
                    snippet="Agent records the complaint.",
                )
            )
        ]
    )
    result = ProcessExtractionService(provider).extract(ingestion.document)
    assert result.candidate is not None
