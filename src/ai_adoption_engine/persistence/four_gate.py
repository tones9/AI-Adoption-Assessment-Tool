"""Explicit persistence adapter for the non-default four-gate contract family."""

from __future__ import annotations

from ai_adoption_engine.models.four_gate_decision_support import (
    FourGateDecisionPackageResult,
    FourGateDecisionPackageSuccess,
)
from ai_adoption_engine.models.four_gate_integrated_assessment import (
    FourGateIntegratedAssessmentResult,
    FourGateIntegratedAssessmentSuccess,
)
from ai_adoption_engine.persistence.base import PersistenceError
from ai_adoption_engine.persistence.contract_pins import successor_contract_pin
from ai_adoption_engine.persistence.sqlite import SQLiteAssessmentRepository
from ai_adoption_engine.workspace.models import (
    ArtifactReference,
    ArtifactType,
    AssessmentRecord,
    ExecutionMode,
    OperationKind,
    OperationRecord,
    StoredArtifact,
    WorkflowStage,
)


class FourGatePersistenceAdapter:
    """Persist/hydrate only phase5-v0.2 and phase6-v0.2 artifacts explicitly."""

    def __init__(self, repository: SQLiteAssessmentRepository) -> None:
        self.repository = repository

    def create_assessment(
        self,
        title: str,
        mode: ExecutionMode,
        *,
        policy_fingerprint: str,
    ) -> AssessmentRecord:
        return self.repository.create_assessment(
            title,
            mode,
            contract_pin=successor_contract_pin(policy_fingerprint),
        )

    def pin_existing_assessment(
        self,
        assessment_id: str,
        *,
        policy_fingerprint: str,
    ) -> AssessmentRecord:
        return self.repository.pin_decision_contract(
            assessment_id,
            successor_contract_pin(policy_fingerprint),
        )

    def begin_assessment_operation(
        self,
        assessment_id: str,
        approved_artifact_id: str,
    ) -> OperationRecord:
        self._require_successor_pin(assessment_id)
        return self.repository.begin_operation(
            assessment_id,
            OperationKind.ASSESS,
            approved_artifact_id,
        )

    def begin_package_operation(
        self,
        assessment_id: str,
        integrated_artifact_id: str,
    ) -> OperationRecord:
        self._require_successor_pin(assessment_id)
        return self.repository.begin_operation(
            assessment_id,
            OperationKind.GENERATE_PACKAGE,
            integrated_artifact_id,
        )

    def persist_integrated_assessment(
        self,
        assessment_id: str,
        result: FourGateIntegratedAssessmentResult,
        *,
        approved_artifact_id: str,
        operation_id: str | None = None,
    ) -> ArtifactReference:
        self._require_successor_pin(assessment_id)
        return self.repository.save_artifact_and_advance(
            assessment_id,
            ArtifactType.INTEGRATED_ASSESSMENT_RESULT,
            result,
            artifact_schema_version="phase5-v0.2",
            stage=(
                WorkflowStage.ASSESSED
                if isinstance(result, FourGateIntegratedAssessmentSuccess)
                else WorkflowStage.APPROVED
            ),
            parent_artifact_id=approved_artifact_id,
            operation_id=operation_id,
        )

    def persist_decision_package(
        self,
        assessment_id: str,
        result: FourGateDecisionPackageResult,
        *,
        integrated_artifact_id: str,
        operation_id: str | None = None,
    ) -> ArtifactReference:
        self._require_successor_pin(assessment_id)
        return self.repository.save_artifact_and_advance(
            assessment_id,
            ArtifactType.DECISION_PACKAGE_RESULT,
            result,
            artifact_schema_version="phase6-v0.2",
            stage=(
                WorkflowStage.PACKAGE_READY
                if isinstance(result, FourGateDecisionPackageSuccess)
                else WorkflowStage.ASSESSED
            ),
            parent_artifact_id=integrated_artifact_id,
            operation_id=operation_id,
        )

    def load_integrated_assessment(self, artifact_id: str) -> StoredArtifact:
        stored = self.repository.load_artifact(artifact_id)
        if (
            stored.artifact_type is not ArtifactType.INTEGRATED_ASSESSMENT_RESULT
            or stored.artifact_schema_version != "phase5-v0.2"
        ):
            raise PersistenceError("Artifact is not a phase5-v0.2 assessment")
        return stored

    def load_decision_package(self, artifact_id: str) -> StoredArtifact:
        stored = self.repository.load_artifact(artifact_id)
        if (
            stored.artifact_type is not ArtifactType.DECISION_PACKAGE_RESULT
            or stored.artifact_schema_version != "phase6-v0.2"
        ):
            raise PersistenceError("Artifact is not a phase6-v0.2 package")
        return stored

    def _require_successor_pin(self, assessment_id: str) -> None:
        pin = self.repository.get_assessment(assessment_id).contract_pin
        if (
            pin.decision_contract_version != "phase1-v0.4"
            or pin.policy_id != "decision_policy.v0.3"
            or pin.policy_version != "0.3.0"
            or pin.virtual
        ):
            raise PersistenceError(
                "The explicit successor adapter requires a phase1-v0.4 pin"
            )
