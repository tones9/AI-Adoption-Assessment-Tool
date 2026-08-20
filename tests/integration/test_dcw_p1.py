from __future__ import annotations

from ai_adoption_engine.application.decision_continuation import (
    DecisionContinuationService,
)
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
        _,
        gap,
        _,
        _,
        _,
        successor_package,
        comparison,
    ) = _full_lifecycle(tmp_path)
    before_refs = _baseline_refs(baseline, assessment_id)

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
    assert _baseline_refs(baseline, assessment_id) == before_refs
    assert baseline.load_workspace(assessment_id).assessment.model_dump(mode="json") == before[0]
