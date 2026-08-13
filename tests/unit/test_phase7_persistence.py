from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ai_adoption_engine.workspace.composition import extraction_service_for
from ai_adoption_engine.workspace.demo_extraction import demo_text
from ai_adoption_engine.workspace.service import AssessmentWorkspaceService
from ai_adoption_engine.workspace.models import (
    ArtifactType,
    ExecutionMode,
    WorkflowStage,
)
from ai_adoption_engine.persistence import ArtifactCorruptionError
from ai_adoption_engine.persistence.sqlite import SQLiteAssessmentRepository


def _service(tmp_path: Path) -> tuple[SQLiteAssessmentRepository, AssessmentWorkspaceService, str]:
    repository = SQLiteAssessmentRepository(tmp_path / "phase7.db")
    service = AssessmentWorkspaceService(
        repository, extraction_service_factory=extraction_service_for
    )
    assessment = repository.create_assessment("Offline fixture", ExecutionMode.OFFLINE_DEMO)
    return repository, service, assessment.assessment_id


def _approve(service: AssessmentWorkspaceService, assessment_id: str):
    service.ingest_upload(assessment_id, raw_text=demo_text())
    service.extract(assessment_id)
    session = service.start_review(assessment_id)
    service.review_service.accept_assertion(session, session.process_name, "process.name")
    for step in session.steps:
        service.review_service.accept_assertion(
            session, step.activity, f"steps.{step.candidate_step_id}.activity"
        )
    service.review_service.accept_step_order(session)
    service.save_review(assessment_id, session)
    result = service.approve(assessment_id)
    assert result.approved is not None
    return result.approved


def _full_chain(service: AssessmentWorkspaceService, assessment_id: str):
    approved = _approve(service, assessment_id)
    integrated = service.assess(assessment_id)
    package = service.generate_package(assessment_id)
    assert integrated.status == "success"
    assert package.status == "success"
    return approved, integrated, package


def test_milestone_revisions_are_immutable_and_lineage_is_exact(tmp_path: Path) -> None:
    repository, service, assessment_id = _service(tmp_path)
    _full_chain(service, assessment_id)
    first = repository.load_workspace(assessment_id)
    first_approval = first.active_artifacts[ArtifactType.APPROVED_REVIEW]
    first_assessment = first.active_artifacts[ArtifactType.INTEGRATED_ASSESSMENT_RESULT]
    first_package = first.active_artifacts[ArtifactType.DECISION_PACKAGE_RESULT]
    first_approval_json = first_approval.payload.model_dump_json()

    service.reset_to_review(assessment_id)
    review = repository.load_active_artifact(assessment_id, ArtifactType.REVIEW_SESSION)
    assert review is not None
    session = review.payload
    service.review_service.correct_assertion(
        session,
        session.process_name,
        "process.name",
        "Revised Customer Complaint Handling",
        rationale="Reviewer refined the process identity.",
    )
    service.save_review(assessment_id, session)
    assert service.approve(assessment_id).approved is not None
    assert service.assess(assessment_id).status == "success"
    assert service.generate_package(assessment_id).status == "success"

    approvals = repository.list_artifact_revisions(
        assessment_id, ArtifactType.APPROVED_REVIEW
    )
    assessments = repository.list_artifact_revisions(
        assessment_id, ArtifactType.INTEGRATED_ASSESSMENT_RESULT
    )
    packages = repository.list_artifact_revisions(
        assessment_id, ArtifactType.DECISION_PACKAGE_RESULT
    )
    assert [item.artifact_revision for item in approvals] == [1, 2]
    assert [item.artifact_revision for item in assessments] == [1, 2]
    assert [item.artifact_revision for item in packages] == [1, 2]
    assert approvals[0].payload.model_dump_json() == first_approval_json
    assert assessments[0].parent_artifact_id == first_approval.artifact_id
    assert packages[0].parent_artifact_id == first_assessment.artifact_id
    assert repository.load_artifact(first_package.artifact_id).parent_artifact_id == first_assessment.artifact_id
    current = repository.load_workspace(assessment_id)
    current_approval = current.active_artifacts[ArtifactType.APPROVED_REVIEW]
    current_assessment = current.active_artifacts[ArtifactType.INTEGRATED_ASSESSMENT_RESULT]
    current_package = current.active_artifacts[ArtifactType.DECISION_PACKAGE_RESULT]
    assert current_assessment.parent_artifact_id == current_approval.artifact_id
    assert current_package.parent_artifact_id == current_assessment.artifact_id


def test_reset_marks_downstream_non_current_without_deleting_history(tmp_path: Path) -> None:
    repository, service, assessment_id = _service(tmp_path)
    _full_chain(service, assessment_id)
    service.reset_to_review(assessment_id)
    workspace = repository.load_workspace(assessment_id)
    assert workspace.assessment.current_stage is WorkflowStage.IN_REVIEW
    assert ArtifactType.APPROVED_REVIEW not in workspace.active_artifacts
    assert ArtifactType.INTEGRATED_ASSESSMENT_RESULT not in workspace.active_artifacts
    assert ArtifactType.DECISION_PACKAGE_RESULT not in workspace.active_artifacts
    assert len(repository.list_artifact_revisions(assessment_id, ArtifactType.APPROVED_REVIEW)) == 1
    assert len(repository.list_artifact_revisions(assessment_id, ArtifactType.INTEGRATED_ASSESSMENT_RESULT)) == 1
    assert len(repository.list_artifact_revisions(assessment_id, ArtifactType.DECISION_PACKAGE_RESULT)) == 1


def test_artifact_and_stage_change_roll_back_together(tmp_path: Path) -> None:
    repository, _, assessment_id = _service(tmp_path)
    connection = sqlite3.connect(repository.path)
    connection.execute(
        """CREATE TRIGGER reject_artifact BEFORE INSERT ON assessment_artifacts
           BEGIN SELECT RAISE(ABORT, 'forced failure'); END"""
    )
    connection.commit()
    connection.close()
    from ai_adoption_engine.ingestion.text import ingest_raw_text

    with pytest.raises(sqlite3.IntegrityError):
        repository.save_artifact_and_advance(
            assessment_id,
            ArtifactType.INGESTION_RESULT,
            ingest_raw_text("Safe rollback fixture"),
            artifact_schema_version="phase2-v0.1",
            stage=WorkflowStage.INGESTED,
        )
    assert repository.get_assessment(assessment_id).current_stage is WorkflowStage.NEW
    assert repository.list_artifact_revisions(assessment_id, ArtifactType.INGESTION_RESULT) == []


def test_hash_mismatch_fails_without_partial_hydration(tmp_path: Path) -> None:
    repository, service, assessment_id = _service(tmp_path)
    service.ingest_upload(assessment_id, raw_text=demo_text())
    connection = sqlite3.connect(repository.path)
    connection.execute(
        "UPDATE assessment_artifacts SET payload_json = '{}' WHERE assessment_id = ?",
        (assessment_id,),
    )
    connection.commit()
    connection.close()
    with pytest.raises(ArtifactCorruptionError):
        repository.load_workspace(assessment_id)


def test_unsupported_schema_version_fails_safely(tmp_path: Path) -> None:
    repository, service, assessment_id = _service(tmp_path)
    service.ingest_upload(assessment_id, raw_text=demo_text())
    connection = sqlite3.connect(repository.path)
    connection.execute(
        "UPDATE assessment_artifacts SET artifact_schema_version = 'future-v99' WHERE assessment_id = ?",
        (assessment_id,),
    )
    connection.commit()
    connection.close()
    with pytest.raises(ArtifactCorruptionError):
        repository.load_workspace(assessment_id)


def test_delete_requires_confirmation_and_removes_all_revisions(tmp_path: Path) -> None:
    repository, service, assessment_id = _service(tmp_path)
    _full_chain(service, assessment_id)
    with pytest.raises(ValueError):
        repository.delete_assessment(assessment_id, confirmed=False)
    repository.delete_assessment(assessment_id, confirmed=True)
    connection = sqlite3.connect(repository.path)
    counts = [
        connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("assessments", "assessment_artifacts", "active_artifacts", "assessment_operations")
    ]
    connection.close()
    assert counts == [0, 0, 0, 0]


def test_source_replacement_deactivates_chain_but_preserves_history(tmp_path: Path) -> None:
    repository, service, assessment_id = _service(tmp_path)
    _full_chain(service, assessment_id)
    original = repository.load_workspace(assessment_id)
    original_ingestion = original.active_artifacts[ArtifactType.INGESTION_RESULT]
    original_candidate = original.active_artifacts[ArtifactType.CANDIDATE_EXTRACTION_RESULT]
    with pytest.raises(ValueError, match="explicit confirmation"):
        service.ingest_upload(assessment_id, raw_text="A replacement process source.")
    service.ingest_upload(
        assessment_id,
        raw_text="A replacement process source.",
        replace_existing=True,
    )
    workspace = repository.load_workspace(assessment_id)
    assert workspace.assessment.current_stage is WorkflowStage.INGESTED
    assert set(workspace.active_artifacts) == {ArtifactType.INGESTION_RESULT}
    assert len(repository.list_artifact_revisions(assessment_id, ArtifactType.APPROVED_REVIEW)) == 1
    assert len(repository.list_artifact_revisions(assessment_id, ArtifactType.INTEGRATED_ASSESSMENT_RESULT)) == 1
    assert len(repository.list_artifact_revisions(assessment_id, ArtifactType.DECISION_PACKAGE_RESULT)) == 1

    service.ingest_upload(
        assessment_id,
        raw_text=demo_text(),
        replace_existing=True,
    )
    reactivated = repository.load_workspace(assessment_id)
    assert reactivated.active_artifacts[ArtifactType.INGESTION_RESULT].artifact_id == original_ingestion.artifact_id
    assert len(repository.list_artifact_revisions(assessment_id, ArtifactType.INGESTION_RESULT)) == 2
    service.extract(assessment_id)
    reactivated = repository.load_workspace(assessment_id)
    assert reactivated.active_artifacts[ArtifactType.CANDIDATE_EXTRACTION_RESULT].artifact_id == original_candidate.artifact_id
    assert reactivated.active_artifacts[ArtifactType.CANDIDATE_EXTRACTION_RESULT].parent_artifact_id == original_ingestion.artifact_id


def test_downstream_artifacts_reject_wrong_parent_types(tmp_path: Path) -> None:
    repository, service, assessment_id = _service(tmp_path)
    service.ingest_upload(assessment_id, raw_text=demo_text())
    ingestion = repository.load_active_artifact(assessment_id, ArtifactType.INGESTION_RESULT)
    assert ingestion is not None
    from tests.fakes.decision_support import sample_integrated_assessment

    with pytest.raises(Exception, match="requires parent APPROVED_REVIEW"):
        repository.save_artifact_and_advance(
            assessment_id,
            ArtifactType.INTEGRATED_ASSESSMENT_RESULT,
            sample_integrated_assessment(),
            artifact_schema_version="phase5-v0.1",
            stage=WorkflowStage.ASSESSED,
            parent_artifact_id=ingestion.artifact_id,
        )
