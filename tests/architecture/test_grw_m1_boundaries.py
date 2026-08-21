from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from ai_adoption_engine.grw.models import GrwReviewDecision
from ai_adoption_engine.grw.service import GrwM1Error
from ai_adoption_engine.persistence.sqlite import SQLiteAssessmentRepository
from ai_adoption_engine.workspace.composition import extraction_service_for
from ai_adoption_engine.workspace.demo_extraction import demo_text
from ai_adoption_engine.workspace.models import ExecutionMode
from ai_adoption_engine.workspace.service import AssessmentWorkspaceService


ROOT = Path(__file__).resolve().parents[2]
PORTFOLIO = ROOT / "evaluation" / "portfolio"
PORT004_PACKAGE_DB = (
    PORTFOLIO / "runs" / "port-004" / "production-run-v0.5-packaged" / "workspace.db"
)


def _portfolio_hashes() -> dict[str, str]:
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(PORTFOLIO.rglob("*"))
        if path.is_file()
    }


def _run_fresh_m1(tmp_path) -> None:
    repository = SQLiteAssessmentRepository(tmp_path / "fresh-m1.db")
    service = AssessmentWorkspaceService(repository, extraction_service_factory=extraction_service_for)
    assessment = repository.create_assessment("Fresh M1", ExecutionMode.OFFLINE_DEMO)
    service.ingest_upload(assessment.assessment_id, raw_text=demo_text())
    service.extract(assessment.assessment_id)
    review = service.start_review(assessment.assessment_id)
    service.review_service.accept_assertion(review, review.process_name, "process.name")
    for step in review.steps:
        service.review_service.accept_assertion(
            review, step.activity, f"steps.{step.candidate_step_id}.activity"
        )
    service.review_service.accept_step_order(review)
    service.save_review(assessment.assessment_id, review)
    assert service.approve(assessment.assessment_id).approved is not None
    assert service.assess(assessment.assessment_id).status == "success"
    assert service.generate_package(assessment.assessment_id).status == "success"
    context = service.open_grw_m1_context(assessment.assessment_id)
    assert context is not None
    service.submit_grw_m1_response(
        assessment.assessment_id,
        baseline=context.baseline,
        gap_id=context.gap.information_gap.gap_id,
        answer_text="Usually around 18,000–22,000 tickets per month.",
    )


def _protected_port004_copy(tmp_path):
    """Copy a known frozen package-ready workspace into a protected path for refusal tests."""

    ordinary = tmp_path / "ordinary" / "workspace.db"
    ordinary.parent.mkdir(parents=True)
    shutil.copy2(PORT004_PACKAGE_DB, ordinary)
    SQLiteAssessmentRepository(ordinary)
    destination = (
        tmp_path
        / "evaluation"
        / "portfolio"
        / "runs"
        / "port-004"
        / "production-run-v0.5-packaged"
        / "workspace.db"
    )
    destination.parent.mkdir(parents=True)
    shutil.copy2(ordinary, destination)
    repository = SQLiteAssessmentRepository(destination)
    service = AssessmentWorkspaceService(repository, extraction_service_factory=extraction_service_for)
    assessment = repository.list_assessments()
    assert len(assessment) == 1
    return destination, service, assessment[0].assessment_id
    status = service.load_grw_m1_status(assessment.assessment_id)
    service.review_grw_m1_submission(
        assessment.assessment_id,
        submission_artifact_id=status.submission_artifact_id,
        decision=GrwReviewDecision.ACCEPT_PRELIMINARY,
        reviewer_label="Synthetic reviewer",
        rationale="Useful context only.",
    )


def test_grw_m1_service_cannot_run_or_mutate_the_formal_decision_path() -> None:
    source = (ROOT / "src" / "ai_adoption_engine" / "grw" / "service.py").read_text()
    for forbidden in (
        "AssessmentEngine",
        "IntegratedAssessmentService",
        "DecisionSupportPackageService",
        "ProcessReviewService",
        "approve_review",
        ".assess(",
        ".generate_package(",
        ".reset_to_review(",
        "decision_policy",
    ):
        assert forbidden not in source
    page = (ROOT / "src" / "ai_adoption_engine" / "presentation" / "pages" / "gap_resolution.py").read_text()
    for forbidden in ("file_uploader", "data_editor", "unsafe_allow_html", "upload"):
        assert forbidden not in page


def test_grw_m1_uses_a_fresh_workspace_and_leaves_all_frozen_ports_unchanged(tmp_path) -> None:
    before = _portfolio_hashes()
    _run_fresh_m1(tmp_path)
    assert _portfolio_hashes() == before
    source = (ROOT / "src" / "ai_adoption_engine" / "grw" / "service.py").read_text()
    assert "port-003" not in source.lower()
    assert "evaluation/portfolio" not in source


def test_grw_submission_is_refused_before_mutating_a_protected_portfolio_workspace(tmp_path) -> None:
    protected_db, service, assessment_id = _protected_port004_copy(tmp_path)
    context = service.open_grw_m1_context(assessment_id)
    assert context is not None
    before = hashlib.sha256(protected_db.read_bytes()).hexdigest()

    try:
        service.submit_grw_m1_response(
            assessment_id,
            baseline=context.baseline,
            gap_id=context.gap.information_gap.gap_id,
            answer_text="Usually around 18,000–22,000 tickets per month.",
        )
    except GrwM1Error as exc:
        assert "refused for frozen evaluation portfolio" in str(exc)
    else:
        raise AssertionError("GRW submission unexpectedly wrote to a protected workspace")

    assert hashlib.sha256(protected_db.read_bytes()).hexdigest() == before


def test_grw_review_is_refused_before_mutating_a_protected_portfolio_workspace(tmp_path) -> None:
    protected_db, service, assessment_id = _protected_port004_copy(tmp_path)
    before = hashlib.sha256(protected_db.read_bytes()).hexdigest()

    try:
        service.review_grw_m1_submission(
            assessment_id,
            submission_artifact_id="unused-submission-id",
            decision=GrwReviewDecision.ACCEPT_PRELIMINARY,
            reviewer_label="Synthetic reviewer",
            rationale="This must be refused before the submission is loaded.",
        )
    except GrwM1Error as exc:
        assert "refused for frozen evaluation portfolio" in str(exc)
    else:
        raise AssertionError("GRW review unexpectedly wrote to a protected workspace")

    assert hashlib.sha256(protected_db.read_bytes()).hexdigest() == before
