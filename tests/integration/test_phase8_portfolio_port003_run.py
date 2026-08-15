from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path

from ai_adoption_engine.extraction.validation import validate_candidate_against_document
from ai_adoption_engine.models.decision_support import DecisionPackageSuccess
from ai_adoption_engine.models.document import IngestionResult
from ai_adoption_engine.models.enums import KnowledgeState, RecommendationMode
from ai_adoption_engine.models.extraction import CandidateExtractionResult, ExtractionStatus
from ai_adoption_engine.models.integrated_assessment import IntegratedAssessmentSuccess
from ai_adoption_engine.models.review import ApprovalResult
from ai_adoption_engine.persistence.serialization import deserialize_artifact
from ai_adoption_engine.workspace.models import ArtifactType


ROOT = Path(__file__).resolve().parents[2]
PORTFOLIO = ROOT / "evaluation" / "portfolio"
RUN = PORTFOLIO / "runs" / "port-003" / "production-run-v0.1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_port003_output_bundle_is_hash_frozen() -> None:
    for line in (RUN / "output_hashes.sha256").read_text().splitlines():
        digest, relative_path = line.split("  ", 1)
        assert _sha256(ROOT / relative_path) == digest, relative_path

    manifest = json.loads((RUN / "output_freeze_manifest.v0.1.json").read_text())
    for item in manifest["artifacts"]:
        assert _sha256(RUN / item["path"]) == item["sha256"], item["path"]


def test_port003_candidate_is_live_schema_valid_and_evidence_resolves() -> None:
    ingestion = IngestionResult.model_validate_json(
        (RUN / "ingestion_result.json").read_text()
    )
    extraction = CandidateExtractionResult.model_validate_json(
        (RUN / "candidate_extraction.json").read_text()
    )
    assert ingestion.document is not None
    assert extraction.status is ExtractionStatus.SUCCESS
    assert extraction.candidate is not None
    assert len(extraction.candidate.steps) == 4
    assert len(extraction.provider_invocations) == 1
    assert extraction.provider_invocations[0].attempt == 1
    assert extraction.issues == []
    validate_candidate_against_document(extraction.candidate, ingestion.document)


def test_port003_extraction_identified_both_content_signals_unaided() -> None:
    """The PORT-003 headline: Phase 3 found the positive signals without human help."""

    extraction = CandidateExtractionResult.model_validate_json(
        (RUN / "candidate_extraction.json").read_text()
    )
    assert extraction.candidate is not None
    positive = {
        (step.sequence, signal.name.value): signal.assertion.value
        for step in extraction.candidate.steps
        for signal in step.characteristics.capability_signals
        if signal.assertion.knowledge_state is not KnowledgeState.UNKNOWN
    }
    assert positive == {
        (2, "creates_new_content"): True,
        (4, "creates_new_content"): True,
    }


def test_port003_review_made_no_corrections_and_retained_unknowns() -> None:
    approval = ApprovalResult.model_validate_json(
        (RUN / "approval_result.json").read_text()
    )
    assert approval.approved is not None
    review = approval.approved.review

    actions = Counter(event.action.value for event in review.events)
    assert actions == {
        "accept": 46,
        "retain-unknown": 81,
        "accept-step-order": 1,
        "approve": 1,
    }
    assert "correct" not in actions
    assert "reject" not in actions
    assert review.conflicts == []

    # Every criterion on every step stays unknown; the review invented nothing.
    for step in review.steps:
        assert all(
            item.assertion.knowledge_state is KnowledgeState.UNKNOWN
            for item in step.criteria
        )

    # The order-consistent dependency was accepted, not rejected.
    summary_step = next(item for item in review.steps if item.sequence == 4)
    assert len(summary_step.dependencies) == 1
    assert summary_step.dependencies[0].retained is True
    assert summary_step.dependencies[0].target_candidate_step_id == next(
        item.candidate_step_id for item in review.steps if item.sequence == 3
    )


def test_port003_assessment_and_package_are_complete() -> None:
    approval = ApprovalResult.model_validate_json(
        (RUN / "approval_result.json").read_text()
    )
    integrated = IntegratedAssessmentSuccess.model_validate_json(
        (RUN / "integrated_assessment.json").read_text()
    )
    package = DecisionPackageSuccess.model_validate_json(
        (RUN / "decision_package_result.json").read_text()
    )
    assert approval.approved is not None
    assert len(approval.approved.business_process.steps) == 4

    assessments = integrated.process_assessment.step_assessments
    assert len(assessments) == 4
    assert all(
        item.recommendation_mode is RecommendationMode.INVESTIGATE_FURTHER
        for item in assessments
    )
    assert all(
        next(gate for gate in item.gate_results if gate.gate.value == "technical_fit")
        .material_criteria
        == ["ai_capability_fit"]
        for item in assessments
    )
    assert [[item.value for item in step.capabilities] for step in assessments] == [
        [],
        ["GENERATIVE_AI"],
        [],
        ["GENERATIVE_AI"],
    ]
    assert len(package.package.portfolio.items) == 4
    assert package.package.future_state.status.value == "PROPOSED / NOT DEPLOYED"
    assert package.package.roi_statement == (
        "ROI / quantified benefit unavailable with current evidence."
    )


def test_port003_sqlite_lineage_is_exact_and_integrity_valid() -> None:
    final_state = json.loads((RUN / "final_run_state.json").read_text())
    connection = sqlite3.connect(f"file:{RUN / 'workspace.db'}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        assessment = connection.execute(
            "SELECT current_stage FROM assessments WHERE assessment_id = ?",
            (final_state["assessment_id"],),
        ).fetchone()
        assert assessment is not None
        assert assessment["current_stage"] == "package-ready"
        rows = connection.execute(
            "SELECT * FROM assessment_artifacts WHERE assessment_id = ?",
            (final_state["assessment_id"],),
        ).fetchall()
    finally:
        connection.close()

    assert len(rows) == 6
    by_id = {row["artifact_id"]: row for row in rows}
    active = final_state["active_artifacts"]
    for artifact_name, metadata in active.items():
        row = by_id[metadata["artifact_id"]]
        assert row["artifact_revision"] == metadata["artifact_revision"] == 1
        assert row["parent_artifact_id"] == metadata["parent_artifact_id"]
        assert row["payload_sha256"] == metadata["payload_sha256"]
        payload = deserialize_artifact(
            ArtifactType(artifact_name),
            row["payload_json"],
            row["payload_sha256"],
        )
        assert payload is not None

    assert active["CANDIDATE_EXTRACTION_RESULT"]["parent_artifact_id"] == active[
        "INGESTION_RESULT"
    ]["artifact_id"]
    assert active["REVIEW_SESSION"]["parent_artifact_id"] == active[
        "CANDIDATE_EXTRACTION_RESULT"
    ]["artifact_id"]
    assert active["APPROVED_REVIEW"]["parent_artifact_id"] == active[
        "REVIEW_SESSION"
    ]["artifact_id"]
    assert active["INTEGRATED_ASSESSMENT_RESULT"]["parent_artifact_id"] == active[
        "APPROVED_REVIEW"
    ]["artifact_id"]
    assert active["DECISION_PACKAGE_RESULT"]["parent_artifact_id"] == active[
        "INTEGRATED_ASSESSMENT_RESULT"
    ]["artifact_id"]


def test_port003_run_used_the_frozen_before_and_unchanged_production_baseline() -> None:
    manifest = json.loads((RUN / "output_freeze_manifest.v0.1.json").read_text())
    freeze = json.loads((PORTFOLIO / "freeze_manifest.v0.1.json").read_text())

    before = manifest["before_input"]
    assert _sha256(ROOT / before["path"]) == before["sha256"]
    assert before["document_id"] == f"doc-{before['sha256']}"
    assert (
        manifest["production_subtree_fingerprint"]
        == freeze["production_baseline"]["production_subtree_fingerprint"]
    )
    assert manifest["provider"]["requested_model"] == "gpt-5.6-terra"
    assert manifest["provider"]["provider_calls"] == 1
    assert manifest["provider"]["repair_invoked"] is False
    assert manifest["human_review"]["capability_signals_corrected"] == 0
    assert manifest["human_review"]["assertions_rejected"] == 0


def test_port003_operator_scripts_are_preserved_and_hash_matched() -> None:
    """PORT-003 improves on PORT-001/002, whose operator scripts were never committed."""

    manifest = json.loads((RUN / "output_freeze_manifest.v0.1.json").read_text())
    for stage in ("stage1", "stage2"):
        entry = manifest["operator_scripts"][stage]
        path = ROOT / entry["path"]
        assert path.is_file(), entry["path"]
        assert _sha256(path) == entry["sha256"], entry["path"]


def test_port003_after_packet_was_sealed_at_output_freeze() -> None:
    manifest = json.loads((RUN / "output_freeze_manifest.v0.1.json").read_text())
    boundary = manifest["after_boundary_at_output_freeze"]
    assert boundary["status"] == "SEALED_NOT_OPENED_FOR_COMPARISON"
    assert _sha256(ROOT / boundary["path"]) == boundary["sha256"]
    assert "SEALED UNTIL PRODUCT OUTPUT IS FROZEN" in (
        ROOT / boundary["path"]
    ).read_text()
