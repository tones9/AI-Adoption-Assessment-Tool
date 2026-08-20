from __future__ import annotations

from datetime import UTC, datetime
import sqlite3

import pytest

from ai_adoption_engine.grw.m2.models import (
    M2ActorDeclaration,
    M2ArtifactType,
    M2ConflictStatus,
    M2DocumentLocator,
    M2EvidenceClass,
    M2EvidencePermission,
    M2RunStage,
)
from ai_adoption_engine.models.enums import KnowledgeState
from ai_adoption_engine.grw.m2.service import M2ReassessmentError, M2ReassessmentService
from ai_adoption_engine.persistence.reassessment import SQLiteReassessmentRepository
from ai_adoption_engine.workspace.models import ArtifactType, WorkflowStage
from tests.fakes.m2_reassessment import package_ready_m2_baseline


def _actor(label: str = "reviewer") -> M2ActorDeclaration:
    return M2ActorDeclaration(label=label, declared_role="synthetic", acknowledged_local_role_limitation=True, declared_at=datetime.now(UTC))


def _submitted_service(tmp_path, *, conflict=M2ConflictStatus.CONSISTENT, reconciliation_statement=None, applicability_statement=None):
    baseline, assessment_id = package_ready_m2_baseline(tmp_path)
    service = M2ReassessmentService(baseline, SQLiteReassessmentRepository(baseline.path))
    run_id, _, _ = service.create_run(assessment_id)
    raw = b"Target fields category and route; authorised access; coverage since January 2025."
    submission = service.submit_supporting_document(run_id, content_bytes=raw, filename="support.txt", source_label="owner", submitter=_actor("submitter"))
    text = raw.decode()
    review = service.review_document_evidence(run_id, reviewer=_actor(), locator=M2DocumentLocator(start_offset=0, end_offset=len(text), line_start=1, line_end=1, exact_excerpt=text), scope_statement="same activity", period_statement="current", source_authority="owner", semantic_rationale="manual review", limitations="limitations", conflict_status=conflict, conflict_rationale="recorded conflict", reconciliation_statement=reconciliation_statement, applicability_statement=applicability_statement, permission=M2EvidencePermission.CRITERION_RESOLUTION_AND_GATE_ADMISSIBLE)
    return baseline, assessment_id, service, run_id, submission, review


def _successor_ready_service(tmp_path):
    baseline, assessment_id, service, run_id, submission, review = _submitted_service(
        tmp_path
    )
    service.propose_data_readiness_resolution(
        run_id,
        proposed_value=3,
        proposed_knowledge_state=KnowledgeState.KNOWN,
        mapping_rationale="The reviewed document meets the versioned anchor.",
        data_owner=_actor("owner"),
        criterion_reviewer=_actor("criterion reviewer"),
    )
    service.request_reassessment(run_id)
    service.approve_reassessment(
        run_id, approver=_actor("approver"), rationale="Explicit approval."
    )
    service.build_successor_review(run_id)
    return baseline, assessment_id, service, run_id, submission, review


def test_document_intake_and_invalid_transition_fail_closed(tmp_path) -> None:
    baseline, assessment_id = package_ready_m2_baseline(tmp_path)
    service = M2ReassessmentService(baseline, SQLiteReassessmentRepository(baseline.path))
    run_id, _, _ = service.create_run(assessment_id)
    actor = M2ActorDeclaration(label="x", declared_role="x", acknowledged_local_role_limitation=True, declared_at=datetime.now(UTC))
    with pytest.raises(M2ReassessmentError, match="plain-text"):
        service.submit_supporting_document(run_id, content_bytes=b"data", filename="data.csv", source_label="x", submitter=actor)
    with pytest.raises(M2ReassessmentError, match="explicit reassessment approval"):
        service.build_successor_review(run_id)


def test_stale_baseline_is_refused_without_successor_creation(tmp_path) -> None:
    baseline, assessment_id = package_ready_m2_baseline(tmp_path)
    service = M2ReassessmentService(baseline, SQLiteReassessmentRepository(baseline.path))
    run_id, _, _ = service.create_run(assessment_id)
    workspace = baseline.load_workspace(assessment_id)
    package = workspace.active_artifacts[ArtifactType.DECISION_PACKAGE_RESULT]
    integrated = workspace.active_artifacts[ArtifactType.INTEGRATED_ASSESSMENT_RESULT]
    baseline.save_artifact_and_advance(assessment_id, ArtifactType.DECISION_PACKAGE_RESULT, package.payload, artifact_schema_version="phase6-v0.1", stage=WorkflowStage.PACKAGE_READY, parent_artifact_id=integrated.artifact_id)
    actor = M2ActorDeclaration(label="x", declared_role="x", acknowledged_local_role_limitation=True, declared_at=datetime.now(UTC))
    with pytest.raises(M2ReassessmentError, match="stale"):
        service.submit_supporting_document(run_id, content_bytes=b"data", filename="data.txt", source_label="owner", submitter=actor)
    assert service.repository.load_artifact_reference(run_id, __import__("ai_adoption_engine.grw.m2.models", fromlist=["M2ArtifactType"]).M2ArtifactType.SUCCESSOR_APPROVED_REVIEW) is None


def test_changed_decision_policy_stales_the_run_before_a_document_write(tmp_path) -> None:
    baseline, assessment_id = package_ready_m2_baseline(tmp_path)
    service = M2ReassessmentService(baseline, SQLiteReassessmentRepository(baseline.path))
    run_id, _, _ = service.create_run(assessment_id)
    baseline_policy_loader = service.assessment_service.policy_loader
    service.assessment_service.policy_loader = lambda: baseline_policy_loader().model_copy(
        update={"version": "synthetic-stale-version"}
    )
    with pytest.raises(M2ReassessmentError, match="Decision policy changed"):
        service.submit_supporting_document(
            run_id,
            content_bytes=b"document",
            filename="document.txt",
            source_label="owner",
            submitter=_actor(),
        )
    assert service.repository.load_run(run_id)["stage"] == M2RunStage.STALE.value
    assert service.repository.load_artifact_reference(
        run_id, M2ArtifactType.DOCUMENT_SUBMISSION
    ) is None


def test_uploaded_document_is_candidate_until_review(tmp_path) -> None:
    baseline, assessment_id = package_ready_m2_baseline(tmp_path)
    service = M2ReassessmentService(baseline, SQLiteReassessmentRepository(baseline.path))
    run_id, _, _ = service.create_run(assessment_id)
    submission = service.submit_supporting_document(run_id, content_bytes=b"arbitrary text", filename="support.txt", source_label="owner", submitter=_actor())
    assert submission.evidence_class is M2EvidenceClass.DOCUMENT_SUPPORTED_CANDIDATE
    assert service.repository.load_artifact_reference(run_id, M2ArtifactType.EVIDENCE_REVIEW) is None


@pytest.mark.parametrize("conflict", [M2ConflictStatus.CONTRADICTORY, M2ConflictStatus.PARTIALLY_OVERLAPPING, M2ConflictStatus.DIFFERENT_SCOPE, M2ConflictStatus.STALE_OR_SUPERSEDED, M2ConflictStatus.UNRESOLVED])
def test_material_conflicts_cannot_directly_resolve_data_readiness(tmp_path, conflict) -> None:
    _, _, service, run_id, _, _ = _submitted_service(tmp_path, conflict=conflict)
    with pytest.raises(M2ReassessmentError):
        service.propose_data_readiness_resolution(run_id, proposed_value=3, proposed_knowledge_state=KnowledgeState.KNOWN, mapping_rationale="mapping", data_owner=_actor("owner"), criterion_reviewer=_actor("criterion"))


@pytest.mark.parametrize(
    ("conflict", "review_kwargs", "resolution_kwargs"),
    [
        (
            M2ConflictStatus.CONTRADICTORY,
            {"reconciliation_statement": "The reviewer reconciled the conflicting source."},
            {"data_owner_reconciliation": "The owner confirms the reconciled target scope."},
        ),
        (
            M2ConflictStatus.PARTIALLY_OVERLAPPING,
            {},
            {"narrowed_scope_statement": "Use only the documented categorisation fields."},
        ),
        (
            M2ConflictStatus.DIFFERENT_SCOPE,
            {},
            {"narrowed_scope_statement": "Use only the selected incoming-request activity."},
        ),
        (
            M2ConflictStatus.STALE_OR_SUPERSEDED,
            {"applicability_statement": "The documented fields and access remain applicable to this target."},
            {},
        ),
    ],
)
def test_material_conflict_requires_explicit_reviewed_reconciliation_or_scope(
    tmp_path, conflict, review_kwargs, resolution_kwargs
) -> None:
    _, _, service, run_id, _, _ = _submitted_service(
        tmp_path, conflict=conflict, **review_kwargs
    )
    resolution = service.propose_data_readiness_resolution(
        run_id,
        proposed_value=3,
        proposed_knowledge_state=KnowledgeState.KNOWN,
        mapping_rationale="The reviewed, limited document maps to the instrument.",
        data_owner=_actor("owner"),
        criterion_reviewer=_actor("criterion"),
        **resolution_kwargs,
    )
    assert resolution.proposed_value == 3


def test_document_tamper_blocks_successor_and_preserves_baseline(tmp_path) -> None:
    baseline, assessment_id, service, run_id, submission, _ = _submitted_service(tmp_path)
    before = baseline.load_workspace(assessment_id).model_dump(mode="json")
    service.propose_data_readiness_resolution(run_id, proposed_value=3, proposed_knowledge_state=KnowledgeState.KNOWN, mapping_rationale="mapping", data_owner=_actor("owner"), criterion_reviewer=_actor("criterion"))
    service.request_reassessment(run_id)
    service.approve_reassessment(run_id, approver=_actor("approver"), rationale="approve")
    connection = sqlite3.connect(baseline.path)
    connection.execute("UPDATE reassessment_documents SET content_bytes=? WHERE document_id=?", (b"tampered", submission.document.document_id))
    connection.commit(); connection.close()
    with pytest.raises(M2ReassessmentError, match="hash"):
        service.build_successor_review(run_id)
    assert service.repository.load_artifact_reference(run_id, M2ArtifactType.SUCCESSOR_APPROVED_REVIEW) is None
    assert baseline.load_workspace(assessment_id).model_dump(mode="json") == before


def test_document_tamper_after_projection_blocks_phase5_as_stale(tmp_path) -> None:
    baseline, assessment_id, service, run_id, submission, _ = _successor_ready_service(
        tmp_path
    )
    before = baseline.load_workspace(assessment_id).model_dump(mode="json")
    connection = sqlite3.connect(baseline.path)
    connection.execute(
        "UPDATE reassessment_documents SET content_bytes=? WHERE document_id=?",
        (b"tampered after projection", submission.document.document_id),
    )
    connection.commit()
    connection.close()
    with pytest.raises(M2ReassessmentError, match="hash"):
        service.assess_successor(run_id)
    assert service.repository.load_run(run_id)["stage"] == M2RunStage.STALE.value
    assert service.repository.load_artifact_reference(
        run_id, M2ArtifactType.SUCCESSOR_INTEGRATED_ASSESSMENT
    ) is None
    assert service.repository.load_artifact_reference(
        run_id, M2ArtifactType.SUCCESSOR_DECISION_PACKAGE
    ) is None
    assert service.repository.load_artifact_reference(
        run_id, M2ArtifactType.BASELINE_SUCCESSOR_COMPARISON
    ) is None
    assert baseline.load_workspace(assessment_id).model_dump(mode="json") == before


def test_phase5_failure_is_terminal_and_cannot_activate_partial_successor(tmp_path) -> None:
    baseline, assessment_id, service, run_id, _, _ = _successor_ready_service(tmp_path)
    before = baseline.load_workspace(assessment_id).model_dump(mode="json")

    class FailingPhase5:
        def __init__(self, policy_loader) -> None:
            self.policy_loader = policy_loader

        def assess_successor(self, *_args, **_kwargs):
            raise RuntimeError("injected phase 5 failure")

    service.assessment_service = FailingPhase5(service.assessment_service.policy_loader)
    with pytest.raises(RuntimeError, match="injected phase 5 failure"):
        service.assess_successor(run_id)
    assert service.repository.load_run(run_id)["stage"] == M2RunStage.FAILED.value
    assert service.repository.load_artifact_reference(
        run_id, M2ArtifactType.SUCCESSOR_INTEGRATED_ASSESSMENT
    ) is None
    assert baseline.load_workspace(assessment_id).model_dump(mode="json") == before


def test_phase6_failure_is_terminal_and_cannot_activate_partial_package(tmp_path) -> None:
    baseline, assessment_id, service, run_id, _, _ = _successor_ready_service(tmp_path)
    before = baseline.load_workspace(assessment_id).model_dump(mode="json")
    service.assess_successor(run_id)

    class FailingPhase6:
        def generate(self, *_args, **_kwargs):
            raise RuntimeError("injected phase 6 failure")

    service.package_service = FailingPhase6()
    with pytest.raises(RuntimeError, match="injected phase 6 failure"):
        service.generate_successor_package(run_id)
    assert service.repository.load_run(run_id)["stage"] == M2RunStage.FAILED.value
    assert service.repository.load_artifact_reference(
        run_id, M2ArtifactType.SUCCESSOR_DECISION_PACKAGE
    ) is None
    assert service.repository.load_artifact_reference(
        run_id, M2ArtifactType.BASELINE_SUCCESSOR_COMPARISON
    ) is None
    assert baseline.load_workspace(assessment_id).model_dump(mode="json") == before
