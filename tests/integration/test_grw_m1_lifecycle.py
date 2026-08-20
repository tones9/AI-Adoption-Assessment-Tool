from __future__ import annotations

import sqlite3

from ai_adoption_engine.application.assessment import IntegratedAssessmentService
from ai_adoption_engine.decision_support import DecisionSupportPackageService
from ai_adoption_engine.grw.models import (
    GrwAdmissibilityEffect,
    GrwEvidenceClass,
    GrwReviewDecision,
)
from ai_adoption_engine.persistence.sqlite import SQLiteAssessmentRepository
from ai_adoption_engine.workspace.composition import extraction_service_for
from ai_adoption_engine.workspace.demo_extraction import demo_text
from ai_adoption_engine.workspace.models import ArtifactType, ExecutionMode, WorkflowStage
from ai_adoption_engine.workspace.service import AssessmentWorkspaceService


class _CountingAssessmentService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def assess(self, approved):
        self.calls.append(approved.review.review_id)
        return IntegratedAssessmentService().assess(approved)


class _CountingPackageService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def generate(self, integrated):
        self.calls.append(integrated.metadata.assessment_run_id)
        return DecisionSupportPackageService().generate(integrated)


def _package_ready_workspace(tmp_path):
    repository = SQLiteAssessmentRepository(tmp_path / "grw-lifecycle.db")
    assessment_service = _CountingAssessmentService()
    package_service = _CountingPackageService()
    service = AssessmentWorkspaceService(
        repository,
        extraction_service_factory=extraction_service_for,
        assessment_service=assessment_service,
        package_service=package_service,
    )
    assessment = repository.create_assessment("GRW M1 lifecycle", ExecutionMode.OFFLINE_DEMO)
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
    return repository, service, assessment.assessment_id, assessment_service, package_service


def _artifact_snapshot(repository, assessment_id: str, artifact_type: ArtifactType):
    artifact = repository.load_active_artifact(assessment_id, artifact_type)
    assert artifact is not None
    connection = sqlite3.connect(repository.path)
    row = connection.execute(
        "SELECT payload_json FROM assessment_artifacts WHERE artifact_id = ?",
        (artifact.artifact_id,),
    ).fetchone()
    connection.close()
    return {
        "artifact_id": artifact.artifact_id,
        "revision": artifact.artifact_revision,
        "parent": artifact.parent_artifact_id,
        "sha256": artifact.payload_sha256,
        "payload_json": row[0],
    }


def test_grw_m1_persists_immutable_evidence_without_changing_the_baseline(tmp_path) -> None:
    repository, service, assessment_id, assessment_service, package_service = (
        _package_ready_workspace(tmp_path)
    )
    before_approved = _artifact_snapshot(repository, assessment_id, ArtifactType.APPROVED_REVIEW)
    before_integrated = _artifact_snapshot(
        repository, assessment_id, ArtifactType.INTEGRATED_ASSESSMENT_RESULT
    )
    before_package = _artifact_snapshot(
        repository, assessment_id, ArtifactType.DECISION_PACKAGE_RESULT
    )
    before_workspace = repository.load_workspace(assessment_id)
    integrated = before_workspace.active_artifacts[ArtifactType.INTEGRATED_ASSESSMENT_RESULT].payload
    package = before_workspace.active_artifacts[ArtifactType.DECISION_PACKAGE_RESULT].payload.package
    context = service.open_grw_m1_context(assessment_id)
    assert context is not None
    assessment_step = next(
        item
        for item in integrated.process_assessment.step_assessments
        if item.step_id == context.gap.step_id
    )
    baseline_criterion = next(
        item for item in assessment_step.criteria if item.criterion.value == "repetition"
    ).model_dump(mode="json")
    baseline_gates = [item.model_dump(mode="json") for item in assessment_step.gate_results]
    baseline_item = next(item for item in package.portfolio.items if item.step_id == context.gap.step_id)
    baseline_decision = {
        "recommendation": baseline_item.recommendation_mode,
        "priority_status": baseline_item.priority_status,
        "priority": baseline_item.priority.model_dump(mode="json") if baseline_item.priority else None,
        "roi": package.roi_statement,
    }
    calls_before_m1 = (list(assessment_service.calls), list(package_service.calls))

    answer = "Usually around 18,000–22,000 tickets per month."
    submission = service.submit_grw_m1_response(
        assessment_id,
        baseline=context.baseline,
        gap_id=context.gap.information_gap.gap_id,
        answer_text=answer,
    )
    submitted_status = service.load_grw_m1_status(assessment_id)
    assert submitted_status.submission_artifact_id is not None
    review = service.review_grw_m1_submission(
        assessment_id,
        submission_artifact_id=submitted_status.submission_artifact_id,
        decision=GrwReviewDecision.ACCEPT_PRELIMINARY,
        reviewer_label="Synthetic reviewer",
        rationale="Useful workload context, but not verified operational evidence.",
    )

    reopened = SQLiteAssessmentRepository(repository.path)
    final_workspace = reopened.load_workspace(assessment_id)
    stored_submission = final_workspace.active_artifacts[ArtifactType.GRW_EVIDENCE_SUBMISSION]
    stored_review = final_workspace.active_artifacts[ArtifactType.GRW_EVIDENCE_REVIEW]
    assert stored_submission.artifact_schema_version == "grw-m1-v0.1"
    assert stored_submission.parent_artifact_id == before_package["artifact_id"]
    assert stored_submission.payload_sha256
    assert stored_submission.payload.answer_text == answer
    assert stored_submission.payload.evidence_class is GrwEvidenceClass.OPERATOR_PROVIDED_ESTIMATE
    assert stored_submission.payload.parsed_candidate.lower_bound == 18000
    assert stored_submission.payload.parsed_candidate.upper_bound == 22000
    assert stored_review.artifact_schema_version == "grw-m1-v0.1"
    assert stored_review.parent_artifact_id == stored_submission.artifact_id
    assert stored_review.payload.submission_artifact_id == stored_submission.artifact_id
    assert stored_review.payload.submission_payload_sha256 == stored_submission.payload_sha256
    assert stored_review.payload.admissibility_effect is GrwAdmissibilityEffect.PRELIMINARY_UNDERSTANDING
    assert stored_review.payload.assessment_effect == "NONE"
    assert {
        key: stored_review.payload.non_change_proof.criterion.model_dump(mode="json")[key]
        for key in ("value", "knowledge_state", "rationale", "evidence_ids", "confidence")
    } == {
        key: baseline_criterion[key]
        for key in ("value", "knowledge_state", "rationale", "evidence_ids", "confidence")
    }
    assert stored_review.payload.non_change_proof.criterion.criterion_name == "repetition"
    assert [item.model_dump(mode="json") for item in stored_review.payload.non_change_proof.gate_results] == baseline_gates

    assert _artifact_snapshot(reopened, assessment_id, ArtifactType.APPROVED_REVIEW) == before_approved
    assert _artifact_snapshot(reopened, assessment_id, ArtifactType.INTEGRATED_ASSESSMENT_RESULT) == before_integrated
    assert _artifact_snapshot(reopened, assessment_id, ArtifactType.DECISION_PACKAGE_RESULT) == before_package
    post_integrated = final_workspace.active_artifacts[ArtifactType.INTEGRATED_ASSESSMENT_RESULT].payload
    post_package = final_workspace.active_artifacts[ArtifactType.DECISION_PACKAGE_RESULT].payload.package
    post_step = next(item for item in post_integrated.process_assessment.step_assessments if item.step_id == context.gap.step_id)
    post_criterion = next(item for item in post_step.criteria if item.criterion.value == "repetition")
    post_item = next(item for item in post_package.portfolio.items if item.step_id == context.gap.step_id)
    assert post_criterion.model_dump(mode="json") == baseline_criterion
    assert [item.model_dump(mode="json") for item in post_step.gate_results] == baseline_gates
    assert {
        "recommendation": post_item.recommendation_mode,
        "priority_status": post_item.priority_status,
        "priority": post_item.priority.model_dump(mode="json") if post_item.priority else None,
        "roi": post_package.roi_statement,
    } == baseline_decision
    assert final_workspace.assessment.current_stage is WorkflowStage.PACKAGE_READY
    assert len(reopened.list_artifact_revisions(assessment_id, ArtifactType.APPROVED_REVIEW)) == 1
    assert len(reopened.list_artifact_revisions(assessment_id, ArtifactType.INTEGRATED_ASSESSMENT_RESULT)) == 1
    assert len(reopened.list_artifact_revisions(assessment_id, ArtifactType.DECISION_PACKAGE_RESULT)) == 1
    assert len(reopened.list_artifact_revisions(assessment_id, ArtifactType.GRW_EVIDENCE_SUBMISSION)) == 1
    assert len(reopened.list_artifact_revisions(assessment_id, ArtifactType.GRW_EVIDENCE_REVIEW)) == 1
    assert (assessment_service.calls, package_service.calls) == calls_before_m1
    assert review.non_change_proof.recommendation_mode == baseline_item.recommendation_mode
    assert submission.answer_text == answer
