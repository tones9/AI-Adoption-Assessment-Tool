from __future__ import annotations

import hashlib

from ai_adoption_engine.application.decision_continuation import (
    DecisionContinuationService,
)
from ai_adoption_engine.grw.m2.models import M2ArtifactType
from ai_adoption_engine.grw.m2.service import M2ReassessmentService
from ai_adoption_engine.persistence.reassessment import SQLiteReassessmentRepository
from ai_adoption_engine.workspace.models import ArtifactType
from ai_adoption_engine.workspace.service import AssessmentWorkspaceService
from tests.integration.test_grw_m2_m1_lifecycle import _full_lifecycle


def _dcw_service(repository) -> DecisionContinuationService:
    reassessment = SQLiteReassessmentRepository(repository.path)
    workspace = AssessmentWorkspaceService(
        repository, extraction_service_factory=lambda *_args: None
    )
    return DecisionContinuationService(
        workspace, M2ReassessmentService(repository, reassessment)
    )


def _baseline_refs(repository, assessment_id: str) -> dict[str, tuple[str, int, str]]:
    workspace = repository.load_workspace(assessment_id)
    return {
        kind.value: (
            workspace.active_artifacts[kind].artifact_id,
            workspace.active_artifacts[kind].artifact_revision,
            workspace.active_artifacts[kind].payload_sha256,
        )
        for kind in (
            ArtifactType.APPROVED_REVIEW,
            ArtifactType.INTEGRATED_ASSESSMENT_RESULT,
            ArtifactType.DECISION_PACKAGE_RESULT,
        )
    }


def test_dcw_renders_existing_successor_and_comparison_without_replacing_baseline(
    tmp_path,
) -> None:
    (
        baseline,
        assessment_id,
        _,
        before,
        run_id,
        baseline_ref,
        gap,
        submitted,
        _,
        _,
        successor_package,
        comparison,
    ) = _full_lifecycle(tmp_path)
    before_refs = _baseline_refs(baseline, assessment_id)
    before_hash = hashlib.sha256(baseline.path.read_bytes()).hexdigest()

    view = _dcw_service(baseline).open(assessment_id)

    assert len(view.m2_runs) == 1
    run = view.m2_runs[0]
    assert run.run_id == run_id
    assert run.is_terminal is True
    assert _dcw_service(baseline).resumable_run(assessment_id, run_id) is None
    assert run.successor is not None
    assert run.successor.package_id == successor_package.decision_package.package.package_id
    assert run.comparison is not None
    assert run.comparison.categories == tuple(comparison.categories)
    assert run.comparison.neutral_explanation == comparison.neutral_explanation
    assert run.controlled_report is not None
    report = run.controlled_report
    assert report.baseline_package_id == baseline_ref.package_id
    assert report.baseline_value is None
    assert report.baseline_knowledge_state == "unknown"
    assert report.baseline_recommendation == comparison.baseline_recommendation
    assert report.approved_change.approval_reason == (
        "The exact M2 M1 resolution is approved for a separate successor."
    )
    assert report.approved_change.baseline_remains_active is True
    assert report.approved_change.mapping_rationale == (
        "The document meets anchor 3; limitations remain explicit."
    )
    assert report.evidence.document_id == submitted.document.document_id
    assert report.evidence.content_sha256 == submitted.document.content_sha256
    assert report.evidence.source_authority == "Service operations manager"
    assert report.evidence.exact_excerpt
    assert report.successor_package_id == (
        successor_package.decision_package.package.package_id
    )
    assert report.successor_value == 3
    assert report.successor_knowledge_state == "known"
    assert report.successor_recommendation == comparison.successor_recommendation
    assert any(item.gate == "technical_fit" for item in report.gate_differences)
    assert report.comparison_categories == tuple(comparison.categories)
    assert _baseline_refs(baseline, assessment_id) == before_refs
    assert baseline.load_workspace(assessment_id).assessment.model_dump(mode="json") == before[0]
    assert hashlib.sha256(baseline.path.read_bytes()).hexdigest() == before_hash


def test_dcw_rejects_an_unrelated_artifact_from_the_controlled_report_lineage(
    tmp_path, monkeypatch
) -> None:
    baseline, assessment_id, _, _, run_id, *_ = _full_lifecycle(tmp_path)
    service = _dcw_service(baseline)
    repository = service.m2_service.repository
    evidence_ref = repository.load_artifact_reference(
        run_id, M2ArtifactType.EVIDENCE_REVIEW
    )
    comparison_ref = repository.load_artifact_reference(
        run_id, M2ArtifactType.BASELINE_SUCCESSOR_COMPARISON
    )
    assert evidence_ref is not None and comparison_ref is not None
    evidence = repository.load_artifact(evidence_ref.artifact_id)
    forged = evidence.model_copy(
        update={"submission_artifact": comparison_ref}
    )
    original_load = repository.load_artifact

    def load_with_unrelated_reference(artifact_id: str):
        if artifact_id == evidence_ref.artifact_id:
            return forged
        return original_load(artifact_id)

    monkeypatch.setattr(repository, "load_artifact", load_with_unrelated_reference)

    view = service.open(assessment_id)

    assert view.m2_discovery_error is not None
    assert view.m2_runs == ()
