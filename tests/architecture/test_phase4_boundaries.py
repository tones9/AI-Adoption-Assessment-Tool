import ast
from pathlib import Path

from ai_adoption_engine.decision.engine import AssessmentEngine
from ai_adoption_engine.models.process import BusinessProcess
from ai_adoption_engine.review.approval import approve_review
from tests.fakes.review import FIXED_TIME, candidate_result, review_service
from ai_adoption_engine.models.review import ExplicitApproval, ProcessReviewSession


def test_phase3_does_not_import_or_invoke_phase4_review() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "ai_adoption_engine" / "extraction"
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        assert not any(item.startswith("ai_adoption_engine.review") for item in imports)


def test_phase4_has_no_provider_ui_persistence_or_decision_runtime_imports() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "ai_adoption_engine" / "review"
    forbidden = (
        "ai_adoption_engine.decision",
        "ai_adoption_engine.extraction.providers",
        "openai",
        "sqlite3",
        "streamlit",
    )
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        assert not any(
            imported == item or imported.startswith(f"{item}.")
            for imported in imports
            for item in forbidden
        )


def test_review_session_is_not_a_business_process() -> None:
    assert not issubclass(ProcessReviewSession, BusinessProcess)


def test_review_and_approval_never_invoke_decision_engine(monkeypatch) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Phase 1 decision engine was invoked during review")

    monkeypatch.setattr(AssessmentEngine, "assess", fail_if_called)
    service = review_service()
    session = service.start_review(candidate_result())
    service.accept_assertion(session, session.process_name, "process.name")
    for step in session.steps:
        service.accept_assertion(session, step.activity, f"steps.{step.candidate_step_id}.activity")
    service.accept_step_order(session)
    result = approve_review(
        session,
        ExplicitApproval(
            approval_statement="APPROVE CURRENT-STATE PROCESS",
            approved_at=FIXED_TIME,
        ),
    )
    assert result.approved is not None
