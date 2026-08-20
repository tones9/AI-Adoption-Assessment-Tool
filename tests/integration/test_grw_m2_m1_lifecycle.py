from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai_adoption_engine.grw.m2.models import M2ActorDeclaration, M2ConflictStatus, M2DocumentLocator, M2EvidencePermission
from ai_adoption_engine.grw.m2.service import M2ReassessmentError, M2ReassessmentService
from ai_adoption_engine.models.enums import KnowledgeState, RecommendationMode
from ai_adoption_engine.persistence.reassessment import SQLiteReassessmentRepository
from ai_adoption_engine.workspace.models import ArtifactType, WorkflowStage
from tests.fakes.m2_reassessment import package_ready_m2_baseline


def _actor(label: str = "M2 reviewer") -> M2ActorDeclaration:
    return M2ActorDeclaration(label=label, declared_role="synthetic role", acknowledged_local_role_limitation=True, declared_at=datetime.now(UTC))


def _snapshot(repository, assessment_id):
    workspace = repository.load_workspace(assessment_id)
    data = {}
    for kind in (ArtifactType.APPROVED_REVIEW, ArtifactType.INTEGRATED_ASSESSMENT_RESULT, ArtifactType.DECISION_PACKAGE_RESULT):
        artifact = workspace.active_artifacts[kind]
        data[kind] = (artifact.artifact_id, artifact.artifact_revision, artifact.parent_artifact_id, artifact.payload_sha256, artifact.payload.model_dump(mode="json"))
    return workspace.assessment.model_dump(mode="json"), {kind: artifact.artifact_id for kind, artifact in workspace.active_artifacts.items()}, data


def _full_lifecycle(tmp_path):
    baseline, assessment_id = package_ready_m2_baseline(tmp_path)
    service = M2ReassessmentService(baseline, SQLiteReassessmentRepository(baseline.path))
    before = _snapshot(baseline, assessment_id)
    run_id, baseline_ref, gap = service.create_run(assessment_id)
    supporting_document = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "m2_data_readiness_supporting_document.txt"
    )
    payload = supporting_document.read_bytes()
    submitted = service.submit_supporting_document(run_id, content_bytes=payload, filename=supporting_document.name, source_label="Service operations manager", submitter=_actor("submitter"))
    decoded = payload.decode()
    locator = M2DocumentLocator(
        start_offset=0,
        end_offset=len(decoded),
        line_start=1,
        line_end=decoded.count("\n", 0, len(decoded)) + 1,
        exact_excerpt=decoded,
    )
    service.review_document_evidence(run_id, reviewer=_actor(), locator=locator, scope_statement="The document covers the selected categorisation activity.", period_statement="January 2025 onward.", source_authority="Service operations manager", semantic_rationale="The fields, access and limits support the M2 M1 instrument anchor.", limitations="Text quality limitations remain.", conflict_status=M2ConflictStatus.CONSISTENT, conflict_rationale="No material conflict identified.", permission=M2EvidencePermission.CRITERION_RESOLUTION_AND_GATE_ADMISSIBLE)
    service.propose_data_readiness_resolution(run_id, proposed_value=3, proposed_knowledge_state=KnowledgeState.KNOWN, mapping_rationale="The document meets anchor 3; limitations remain explicit.", data_owner=_actor("owner"), criterion_reviewer=_actor("criterion reviewer"))
    service.request_reassessment(run_id)
    service.approve_reassessment(run_id, approver=_actor("approver"), rationale="The exact M2 M1 resolution is approved for a separate successor.")
    successor = service.build_successor_review(run_id)
    assessment = service.assess_successor(run_id)
    package = service.generate_successor_package(run_id)
    comparison = service.compare(run_id)
    return baseline, assessment_id, service, before, run_id, baseline_ref, gap, submitted, successor, assessment, package, comparison


def test_m2_m1_lifecycle_creates_a_separate_successor_and_preserves_baseline(tmp_path) -> None:
    baseline, assessment_id, service, before, run_id, baseline_ref, gap, submitted, successor, assessment, package, comparison = _full_lifecycle(tmp_path)
    after = _snapshot(baseline, assessment_id)
    assert after == before
    assert baseline.load_workspace(assessment_id).assessment.current_stage is WorkflowStage.PACKAGE_READY
    assert successor.target_step_id == gap.step_id
    assert successor.successor_process.steps[0].characteristics.data_readiness.value == 3
    assert submitted.document.document_id == f"doc-{hashlib.sha256(service.repository.load_document_bytes(submitted.document.document_id)).hexdigest()}"
    assert "not original Phase 3 extraction evidence" in successor.successor_process.evidence[-1].provenance
    assert assessment.integrated_assessment.status == "success"
    assert package.decision_package.status == "success"
    assert comparison.categories == ["CRITERION_CHANGE", "GATE_CHANGE", "RECOMMENDATION_CHANGE"]
    successor_item = next(item for item in package.decision_package.package.portfolio.items if item.step_id == gap.step_id)
    assert successor_item.recommendation_mode is RecommendationMode.AUGMENT
    assert service.repository.load_run(run_id)["stage"] == "COMPARED"
    assert service.compare(run_id) == comparison


def test_m2_requires_reviewed_resolution_and_explicit_approval(tmp_path) -> None:
    baseline, assessment_id = package_ready_m2_baseline(tmp_path)
    service = M2ReassessmentService(baseline, SQLiteReassessmentRepository(baseline.path))
    run_id, _, _ = service.create_run(assessment_id)
    with pytest.raises(M2ReassessmentError, match="explicit reassessment approval"):
        service.build_successor_review(run_id)
    with pytest.raises(M2ReassessmentError, match="criterion resolution"):
        service.request_reassessment(run_id)
    actor = _actor()
    payload = b"Data fields and access are documented."
    submission = service.submit_supporting_document(run_id, content_bytes=payload, filename="support.txt", source_label="owner", submitter=actor)
    text = payload.decode()
    service.review_document_evidence(run_id, reviewer=actor, locator=M2DocumentLocator(start_offset=0, end_offset=len(text), line_start=1, line_end=1, exact_excerpt=text), scope_statement="same activity", period_statement="current", source_authority="owner", semantic_rationale="support", limitations="limitations", conflict_status=M2ConflictStatus.CONSISTENT, conflict_rationale="none", permission=M2EvidencePermission.CRITERION_RESOLUTION_AND_GATE_ADMISSIBLE)
    with pytest.raises(M2ReassessmentError, match="0–4"):
        service.propose_data_readiness_resolution(run_id, proposed_value=5, proposed_knowledge_state=KnowledgeState.KNOWN, mapping_rationale="bad", data_owner=_actor(), criterion_reviewer=_actor())


def test_m2_frozen_portfolio_path_refuses_before_database_mutation(tmp_path) -> None:
    protected = tmp_path / "evaluation" / "portfolio" / "PORT-004" / "workspace.db"
    protected.parent.mkdir(parents=True)
    protected.write_bytes(b"frozen bytes")
    before = hashlib.sha256(protected.read_bytes()).hexdigest()
    with pytest.raises(PermissionError, match="frozen evaluation"):
        SQLiteReassessmentRepository(protected)
    assert hashlib.sha256(protected.read_bytes()).hexdigest() == before
