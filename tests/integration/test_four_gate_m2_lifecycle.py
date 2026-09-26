from __future__ import annotations

import hashlib
import sqlite3

from ai_adoption_engine.application.four_gate_assessment import (
    FourGateIntegratedAssessmentService,
)
from ai_adoption_engine.decision_support.four_gate_service import (
    FourGateDecisionSupportPackageService,
)
from ai_adoption_engine.grw.four_gate_m2.models import (
    SCHEMA_VERSION,
    FourGateM2ArtifactType,
    FourGateM2RunStage,
)
from ai_adoption_engine.models.enums import CriterionName
from ai_adoption_engine.workspace.models import ArtifactType
from tests.fakes.four_gate_m2 import complete_lifecycle, successor_m2_service
from tests.fakes.review import FIXED_TIME


def _baseline_snapshot(path):
    connection = sqlite3.connect(path)
    try:
        return {
            "artifacts": connection.execute(
                "SELECT artifact_id, artifact_schema_version, payload_json, "
                "payload_sha256, parent_artifact_id FROM assessment_artifacts "
                "ORDER BY artifact_id"
            ).fetchall(),
            "active": connection.execute(
                "SELECT artifact_type, artifact_id FROM active_artifacts "
                "ORDER BY artifact_type"
            ).fetchall(),
            "assessment": connection.execute(
                "SELECT decision_contract_version, decision_policy_id, "
                "decision_policy_version, decision_policy_fingerprint "
                "FROM assessments"
            ).fetchall(),
        }
    finally:
        connection.close()


class _Phase5Spy:
    def __init__(self, loader, calls):
        self.delegate = FourGateIntegratedAssessmentService(
            policy_loader=loader,
            clock=lambda: FIXED_TIME,
            run_id_factory=lambda: "successor-m2-phase5",
        )
        self.calls = calls

    def assess(self, approved):
        self.calls.append(type(approved).__name__)
        return self.delegate.assess(approved)


class _Phase6Spy:
    def __init__(self, calls):
        self.delegate = FourGateDecisionSupportPackageService()
        self.calls = calls

    def generate(self, integrated):
        self.calls.append(type(integrated).__name__)
        return self.delegate.generate(integrated)


def test_full_same_contract_lifecycle_is_append_only_and_typed(tmp_path) -> None:
    phase5_calls: list[str] = []
    phase6_calls: list[str] = []
    state = successor_m2_service(
        tmp_path,
        phase5_factory=lambda loader: _Phase5Spy(loader, phase5_calls),
        phase6=_Phase6Spy(phase6_calls),
    )
    before = _baseline_snapshot(state["baseline_repository"].path)
    before_package_hash = hashlib.sha256(
        state["package"].model_dump_json().encode()
    ).hexdigest()

    lifecycle = complete_lifecycle(state, value=4)
    manifest, _, _, resolution, request, approval, projection, assessed, packaged, compared = (
        lifecycle
    )

    assert state["repository"].load_run(manifest.run_id)["stage"] == (
        FourGateM2RunStage.COMPARED
    )
    assert phase5_calls == ["ApprovedProcessReview"]
    assert phase6_calls == ["FourGateIntegratedAssessmentSuccess"]
    assert request.changed_field_path.endswith(".characteristics.data_readiness")
    assert approval.baseline_remains_active is True
    assert resolution.criterion is CriterionName.DATA_READINESS
    assert projection.baseline == manifest.baseline
    assert assessed.integrated_assessment.metadata.phase1_contract_version == "phase1-v0.4"
    assert assessed.integrated_assessment.metadata.integration_schema_version == "phase5-v0.2"
    assert packaged.decision_package.package_schema_version == "phase6-v0.2"
    assert compared.baseline_decision.outcome_code.value == "DISCOVERY_REQUIRED"
    assert len(compared.baseline_decision.gate_results) == 4
    assert len(compared.successor_decision.gate_results) == 4
    assert "TYPED_DECISION_CHANGE" in compared.categories
    assert "improvement" in compared.neutral_explanation
    assert "does not establish" in compared.neutral_explanation
    assert state["service"].request_reassessment(manifest.run_id) == request
    assert state["service"].build_successor_review(manifest.run_id) == projection
    assert state["service"].assess_successor(manifest.run_id) == assessed
    assert state["service"].generate_successor_package(manifest.run_id) == packaged
    assert state["service"].compare(manifest.run_id) == compared

    connection = sqlite3.connect(state["baseline_repository"].path)
    try:
        rows = connection.execute(
            "SELECT artifact_type, artifact_schema_version, parent_artifact_id "
            "FROM four_gate_reassessment_artifacts WHERE run_id=? "
            "ORDER BY rowid",
            (manifest.run_id,),
        ).fetchall()
    finally:
        connection.close()
    assert [row[0] for row in rows] == [item.value for item in FourGateM2ArtifactType]
    assert {row[1] for row in rows} == {SCHEMA_VERSION}
    assert rows[0][2] is None
    assert all(row[2] is not None for row in rows[1:])
    assert _baseline_snapshot(state["baseline_repository"].path) == before
    assert hashlib.sha256(state["package"].model_dump_json().encode()).hexdigest() == (
        before_package_hash
    )


def test_successor_artifacts_round_trip_with_same_policy_and_framework(tmp_path) -> None:
    state = successor_m2_service(tmp_path)
    lifecycle = complete_lifecycle(state)
    manifest, projection, assessed, packaged, compared = (
        lifecycle[0],
        lifecycle[6],
        lifecycle[7],
        lifecycle[8],
        lifecycle[9],
    )

    for artifact_type, expected in (
        (FourGateM2ArtifactType.RUN_MANIFEST, manifest),
        (FourGateM2ArtifactType.SUCCESSOR_APPROVED_REVIEW, projection),
        (FourGateM2ArtifactType.SUCCESSOR_INTEGRATED_ASSESSMENT, assessed),
        (FourGateM2ArtifactType.SUCCESSOR_DECISION_PACKAGE, packaged),
        (FourGateM2ArtifactType.BASELINE_SUCCESSOR_COMPARISON, compared),
    ):
        reference = state["repository"].load_artifact_reference(
            manifest.run_id, artifact_type
        )
        assert reference is not None
        assert state["repository"].load_artifact(reference.artifact_id) == expected

    source = packaged.decision_package.package.source
    assert source.phase1_contract_version == "phase1-v0.4"
    assert source.policy.policy_id == manifest.baseline.decision_policy_id
    assert source.policy.policy_version == manifest.baseline.decision_policy_version
    assert source.policy.decision_policy_fingerprint == (
        manifest.baseline.decision_policy_fingerprint
    )
    assert packaged.decision_package.package.current_state.framework_id == (
        manifest.baseline.framework_id
    )
    assert state["baseline_repository"].load_workspace(
        state["assessment_id"]
    ).active_artifacts[ArtifactType.DECISION_PACKAGE_RESULT].payload == state["package"]
