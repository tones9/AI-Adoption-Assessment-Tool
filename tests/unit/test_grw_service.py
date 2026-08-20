from __future__ import annotations

import pytest

from ai_adoption_engine.grw.models import (
    GrwAdmissibilityEffect,
    GrwEvidenceClass,
    GrwReviewDecision,
)
from ai_adoption_engine.grw.service import GrwM1Error
from ai_adoption_engine.persistence.sqlite import SQLiteAssessmentRepository
from ai_adoption_engine.workspace.demo_extraction import demo_text
from ai_adoption_engine.workspace.models import ArtifactType, ExecutionMode, WorkflowStage
from ai_adoption_engine.workspace.service import AssessmentWorkspaceService
from ai_adoption_engine.workspace.composition import extraction_service_for


def _ready_workspace(tmp_path, name: str = "GRW service", *, repository=None, service=None):
    repository = repository or SQLiteAssessmentRepository(tmp_path / "grw-service.db")
    service = service or AssessmentWorkspaceService(
        repository, extraction_service_factory=extraction_service_for
    )
    assessment = repository.create_assessment(name, ExecutionMode.OFFLINE_DEMO)
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
    return repository, service, assessment.assessment_id


def test_context_selects_only_the_pre_registered_unknown_repetition_gap(tmp_path) -> None:
    _, service, assessment_id = _ready_workspace(tmp_path)
    context = service.open_grw_m1_context(assessment_id)
    assert context is not None
    assert context.question.priority_category == "DECISION_STRENGTHENING"
    assert context.gap.information_gap.field_name == "repetition"
    assert context.gap.information_gap.knowledge_state.value == "unknown"
    assert "A rough range is okay" in context.question.customer_question


def test_submission_lineage_exact_answer_and_idempotent_replay(tmp_path) -> None:
    repository, service, assessment_id = _ready_workspace(tmp_path)
    context = service.open_grw_m1_context(assessment_id)
    assert context is not None
    answer = "Usually around 18,000–22,000 tickets per month."
    submission = service.submit_grw_m1_response(
        assessment_id,
        baseline=context.baseline,
        gap_id=context.gap.information_gap.gap_id,
        answer_text=answer,
    )
    stored = repository.load_active_artifact(
        assessment_id, ArtifactType.GRW_EVIDENCE_SUBMISSION
    )
    assert stored is not None
    assert stored.parent_artifact_id == context.baseline.decision_package.artifact_id
    assert stored.payload == submission
    assert submission.answer_text == answer
    assert submission.evidence_class is GrwEvidenceClass.OPERATOR_PROVIDED_ESTIMATE
    assert submission.baseline == context.baseline
    assert submission.gap.information_gap.gap_id == context.gap.information_gap.gap_id
    assert service.submit_grw_m1_response(
        assessment_id,
        baseline=context.baseline,
        gap_id=context.gap.information_gap.gap_id,
        answer_text=answer,
    ) == submission
    with pytest.raises(GrwM1Error, match="already been submitted"):
        service.submit_grw_m1_response(
            assessment_id,
            baseline=context.baseline,
            gap_id=context.gap.information_gap.gap_id,
            answer_text="20–30 tickets per month",
        )


def test_unknown_and_recorded_only_review_preserve_no_assessment_effect(tmp_path) -> None:
    repository, service, assessment_id = _ready_workspace(tmp_path)
    context = service.open_grw_m1_context(assessment_id)
    assert context is not None
    submission = service.submit_grw_m1_response(
        assessment_id,
        baseline=context.baseline,
        gap_id=context.gap.information_gap.gap_id,
        answer_text="I do not know.",
        explicit_unknown=True,
    )
    status = service.load_grw_m1_status(assessment_id)
    review = service.review_grw_m1_submission(
        assessment_id,
        submission_artifact_id=status.submission_artifact_id,
        decision=GrwReviewDecision.ACCEPT_RECORDED_ONLY,
        reviewer_label="Process owner",
        rationale="No estimate is available.",
    )
    assert submission.evidence_class is GrwEvidenceClass.UNKNOWN
    assert submission.parsed_candidate is None
    assert review.admissibility_effect is GrwAdmissibilityEffect.RECORDED_ONLY
    assert review.assessment_effect == "NONE"
    assert repository.load_workspace(assessment_id).assessment.current_stage is WorkflowStage.PACKAGE_READY


def test_stale_baseline_cross_assessment_and_second_review_fail_safely(tmp_path) -> None:
    repository, service, assessment_id = _ready_workspace(tmp_path, "first")
    _, other_service, other_assessment_id = _ready_workspace(
        tmp_path, "second", repository=repository, service=service
    )
    context = service.open_grw_m1_context(assessment_id)
    other_context = other_service.open_grw_m1_context(other_assessment_id)
    assert context is not None and other_context is not None
    with pytest.raises(GrwM1Error, match="no longer attached"):
        service.submit_grw_m1_response(
            assessment_id,
            baseline=other_context.baseline,
            gap_id=context.gap.information_gap.gap_id,
            answer_text="18–22 tickets per month",
        )
    submission = service.submit_grw_m1_response(
        assessment_id,
        baseline=context.baseline,
        gap_id=context.gap.information_gap.gap_id,
        answer_text="18–22 tickets per month",
    )
    status = service.load_grw_m1_status(assessment_id)
    with pytest.raises(GrwM1Error, match="does not belong"):
        other_service.review_grw_m1_submission(
            other_assessment_id,
            submission_artifact_id=status.submission_artifact_id,
            decision=GrwReviewDecision.REJECT,
            reviewer_label="Reviewer",
            rationale="Wrong assessment.",
        )
    service.review_grw_m1_submission(
        assessment_id,
        submission_artifact_id=status.submission_artifact_id,
        decision=GrwReviewDecision.ACCEPT_PRELIMINARY,
        reviewer_label="Reviewer",
        rationale="Useful but unverified context.",
    )
    with pytest.raises(GrwM1Error, match="already been reviewed"):
        service.review_grw_m1_submission(
            assessment_id,
            submission_artifact_id=status.submission_artifact_id,
            decision=GrwReviewDecision.REJECT,
            reviewer_label="Reviewer",
            rationale="Cannot change a review.",
        )
