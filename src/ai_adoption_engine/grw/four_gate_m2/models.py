"""Immutable contracts for ``grw-m2-four-gate-v0.1``."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_adoption_engine.models.enums import CriterionName, KnowledgeState
from ai_adoption_engine.models.four_gate_assessment import (
    AutonomyCeiling,
    ChangeDisposition,
    DecisionStatus,
    FourGateName,
    FourGatePriorityStatus,
    FourGateResult,
    OutcomeCode,
    ReadinessDisposition,
    SelectedInterventionFamily,
)
from ai_adoption_engine.models.four_gate_decision_support import (
    FourGateDecisionPackageSuccess,
    FourGateInformationGap,
    FourGateInformationGapKind,
)
from ai_adoption_engine.models.four_gate_integrated_assessment import (
    FourGateIntegratedAssessmentSuccess,
)
from ai_adoption_engine.models.review import ApprovedProcessReview


SCHEMA_VERSION = "grw-m2-four-gate-v0.1"


class FourGateM2RunStage(StrEnum):
    OPEN = "OPEN"
    DOCUMENT_SUBMITTED = "DOCUMENT_SUBMITTED"
    EVIDENCE_REVIEWED = "EVIDENCE_REVIEWED"
    RESOLUTION_PROPOSED = "RESOLUTION_PROPOSED"
    REQUESTED = "REQUESTED"
    APPROVED = "APPROVED"
    SUCCESSOR_REVIEW_READY = "SUCCESSOR_REVIEW_READY"
    ASSESSED = "ASSESSED"
    PACKAGE_READY = "PACKAGE_READY"
    COMPARED = "COMPARED"
    EVIDENCE_REJECTED = "EVIDENCE_REJECTED"
    INSUFFICIENT = "INSUFFICIENT"
    BLOCKED_CONFLICT = "BLOCKED_CONFLICT"
    STALE = "STALE"
    FAILED = "FAILED"


class FourGateM2ArtifactType(StrEnum):
    RUN_MANIFEST = "RUN_MANIFEST"
    DOCUMENT_SUBMISSION = "DOCUMENT_SUBMISSION"
    EVIDENCE_REVIEW = "EVIDENCE_REVIEW"
    DATA_READINESS_RESOLUTION = "DATA_READINESS_RESOLUTION"
    REASSESSMENT_REQUEST = "REASSESSMENT_REQUEST"
    REASSESSMENT_APPROVAL = "REASSESSMENT_APPROVAL"
    SUCCESSOR_APPROVED_REVIEW = "SUCCESSOR_APPROVED_REVIEW"
    SUCCESSOR_INTEGRATED_ASSESSMENT = "SUCCESSOR_INTEGRATED_ASSESSMENT"
    SUCCESSOR_DECISION_PACKAGE = "SUCCESSOR_DECISION_PACKAGE"
    BASELINE_SUCCESSOR_COMPARISON = "BASELINE_SUCCESSOR_COMPARISON"


class FourGateM2EvidencePermission(StrEnum):
    REJECTED = "REJECTED"
    INSUFFICIENT_FOR_THIS_USE = "INSUFFICIENT_FOR_THIS_USE"
    CRITERION_RESOLUTION_AND_GATE_ADMISSIBLE = (
        "CRITERION_RESOLUTION_AND_GATE_ADMISSIBLE"
    )


class FourGateM2ConflictStatus(StrEnum):
    CONSISTENT = "CONSISTENT"
    PARTIALLY_OVERLAPPING = "PARTIALLY_OVERLAPPING"
    CONTRADICTORY = "CONTRADICTORY"
    DIFFERENT_SCOPE = "DIFFERENT_SCOPE"
    STALE_OR_SUPERSEDED = "STALE_OR_SUPERSEDED"
    UNRESOLVED = "UNRESOLVED"


class FourGateM2ArtifactReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: str = Field(min_length=1)
    artifact_revision: int = Field(ge=1)
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class FourGateM2BaselineReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    assessment_id: str = Field(min_length=1)
    execution_mode: str = Field(min_length=1)
    source_document_id: str = Field(pattern=r"^doc-[0-9a-f]{64}$")
    approved_review: FourGateM2ArtifactReference
    integrated_assessment: FourGateM2ArtifactReference
    decision_package: FourGateM2ArtifactReference
    package_id: str = Field(min_length=1)
    validated_process_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    framework_id: Literal["four-gate-framework.v0.1"]
    framework_version: Literal["0.1"]
    phase1_contract_version: Literal["phase1-v0.4"]
    phase5_schema_version: Literal["phase5-v0.2"]
    phase6_schema_version: Literal["phase6-v0.2"]
    decision_policy_id: Literal["decision_policy.v0.3"]
    decision_policy_version: Literal["0.3.0"]
    decision_policy_status: str = Field(min_length=1)
    decision_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class FourGateM2GapReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    package_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    activity: str = Field(min_length=1)
    information_gap: FourGateInformationGap
    gate_result: FourGateResult
    baseline_value: None = None
    baseline_knowledge_state: Literal[KnowledgeState.UNKNOWN] = KnowledgeState.UNKNOWN

    @model_validator(mode="after")
    def validate_eligible_gap(self) -> Self:
        gap = self.information_gap
        if (
            gap.step_id != self.step_id
            or gap.kind is not FourGateInformationGapKind.ACTIVE_DECISION_BLOCKER
            or gap.gate is not FourGateName.IS_IT_READY
            or gap.field_name != CriterionName.DATA_READINESS.value
            or self.gate_result.gate is not FourGateName.IS_IT_READY
            or self.gate_result.status.value != "BLOCKED_BY_EVIDENCE"
        ):
            raise ValueError("Successor M2 supports only active Gate 2 data_readiness")
        return self


class FourGateM2RunManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    run_id: str = Field(min_length=1)
    created_at: datetime
    baseline: FourGateM2BaselineReference
    target: FourGateM2GapReference
    creation_idempotency_key: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_target_contract(self) -> Self:
        if self.target.package_id != self.baseline.package_id:
            raise ValueError("Run target must belong to the pinned package")
        return self


class FourGateM2ActorDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str = Field(min_length=1, max_length=200)
    declared_role: str = Field(min_length=1, max_length=200)
    acknowledged_local_role_limitation: bool
    declared_at: datetime

    @model_validator(mode="after")
    def require_local_authority_disclosure(self) -> Self:
        if not self.acknowledged_local_role_limitation:
            raise ValueError("Local role declarations must not claim verified authority")
        return self


class FourGateM2SupportingDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str = Field(pattern=r"^doc-[0-9a-f]{64}$")
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    content_type: Literal["text/plain"] = "text/plain"
    filename: str = Field(min_length=1, max_length=255)
    byte_length: int = Field(gt=0)
    received_at: datetime
    source_label: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        if self.document_id != f"doc-{self.content_sha256}":
            raise ValueError("Document ID must derive from the content hash")
        return self


class FourGateM2DocumentLocator(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    exact_excerpt: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_offsets(self) -> Self:
        if self.end_offset <= self.start_offset or self.line_end < self.line_start:
            raise ValueError("Locator end must follow its start")
        return self


class FourGateM2DocumentSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    submission_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    submitted_at: datetime
    baseline: FourGateM2BaselineReference
    target: FourGateM2GapReference
    document: FourGateM2SupportingDocument
    submitter: FourGateM2ActorDeclaration
    evidence_status: Literal["CANDIDATE_PENDING_HUMAN_REVIEW"] = (
        "CANDIDATE_PENDING_HUMAN_REVIEW"
    )

    @model_validator(mode="after")
    def validate_target_contract(self) -> Self:
        if self.target.package_id != self.baseline.package_id:
            raise ValueError("Document target must belong to the pinned package")
        return self


class FourGateM2EvidenceReview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    review_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    baseline: FourGateM2BaselineReference
    target: FourGateM2GapReference
    submission_artifact: FourGateM2ArtifactReference
    reviewed_at: datetime
    reviewer: FourGateM2ActorDeclaration
    locator: FourGateM2DocumentLocator
    scope_statement: str = Field(min_length=1)
    period_statement: str = Field(min_length=1)
    source_authority: str = Field(min_length=1)
    applicability_statement: str = Field(min_length=1)
    semantic_rationale: str = Field(min_length=1)
    limitations: str = Field(min_length=1)
    conflict_status: FourGateM2ConflictStatus
    conflict_rationale: str = Field(min_length=1)
    permission: FourGateM2EvidencePermission

    @model_validator(mode="after")
    def validate_permission(self) -> Self:
        if self.target.package_id != self.baseline.package_id:
            raise ValueError("Evidence target must belong to the pinned package")
        if (
            self.permission
            is FourGateM2EvidencePermission.CRITERION_RESOLUTION_AND_GATE_ADMISSIBLE
            and self.conflict_status is not FourGateM2ConflictStatus.CONSISTENT
        ):
            raise ValueError("Only consistent reviewed evidence may resolve the criterion")
        return self


class FourGateM2DataReadinessResolution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    resolution_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    baseline: FourGateM2BaselineReference
    target: FourGateM2GapReference
    evidence_review_artifact: FourGateM2ArtifactReference
    criterion: Literal[CriterionName.DATA_READINESS] = CriterionName.DATA_READINESS
    permitted_gate: Literal[FourGateName.IS_IT_READY] = FourGateName.IS_IT_READY
    baseline_value: None = None
    baseline_knowledge_state: Literal[KnowledgeState.UNKNOWN] = KnowledgeState.UNKNOWN
    proposed_value: int | None = Field(default=None, ge=0, le=5)
    proposed_knowledge_state: KnowledgeState
    mapping_rationale: str = Field(min_length=1)
    data_owner: FourGateM2ActorDeclaration
    criterion_reviewer: FourGateM2ActorDeclaration

    @model_validator(mode="after")
    def validate_resolution(self) -> Self:
        if self.target.package_id != self.baseline.package_id:
            raise ValueError("Resolution target must belong to the pinned package")
        if self.proposed_knowledge_state is KnowledgeState.UNKNOWN:
            if self.proposed_value is not None:
                raise ValueError("Retained unknown must not carry a value")
        elif self.proposed_knowledge_state is KnowledgeState.KNOWN:
            if self.proposed_value is None:
                raise ValueError("A known resolution requires a value")
        else:
            raise ValueError("This controlled path does not create inferred values")
        return self


class FourGateM2ReassessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    request_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    requested_at: datetime
    baseline: FourGateM2BaselineReference
    target: FourGateM2GapReference
    evidence_review_artifact: FourGateM2ArtifactReference
    resolution_artifact: FourGateM2ArtifactReference
    changed_field_path: str = Field(min_length=1)
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_exact_change(self) -> Self:
        expected = f"steps.{self.target.step_id}.characteristics.data_readiness"
        if (
            self.target.package_id != self.baseline.package_id
            or self.changed_field_path != expected
        ):
            raise ValueError("Request must identify only the pinned data-readiness field")
        return self


class FourGateM2ReassessmentApproval(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    approval_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    baseline: FourGateM2BaselineReference
    target: FourGateM2GapReference
    request_artifact: FourGateM2ArtifactReference
    approved_at: datetime
    approver: FourGateM2ActorDeclaration
    rationale: str = Field(min_length=1)
    exact_change: str = Field(min_length=1)
    retained_uncertainty: str = Field(min_length=1)
    baseline_remains_active: Literal[True] = True

    @model_validator(mode="after")
    def validate_target_contract(self) -> Self:
        if self.target.package_id != self.baseline.package_id:
            raise ValueError("Approval target must belong to the pinned package")
        return self


class FourGateM2SuccessorApprovedReview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    run_id: str = Field(min_length=1)
    baseline: FourGateM2BaselineReference
    baseline_approved_review: FourGateM2ArtifactReference
    request_artifact: FourGateM2ArtifactReference
    approval_artifact: FourGateM2ArtifactReference
    evidence_review_artifact: FourGateM2ArtifactReference
    resolution_artifact: FourGateM2ArtifactReference
    target_step_id: str = Field(min_length=1)
    changed_field_path: str = Field(min_length=1)
    evidence_id: str = Field(pattern=r"^cev-[0-9a-f]{64}$")
    successor_process_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    approved_review: ApprovedProcessReview

    @model_validator(mode="after")
    def validate_projection_identity(self) -> Self:
        if (
            self.baseline_approved_review != self.baseline.approved_review
            or self.changed_field_path
            != f"steps.{self.target_step_id}.characteristics.data_readiness"
        ):
            raise ValueError("Successor projection does not match the pinned baseline")
        return self


class FourGateM2SuccessorAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    run_id: str = Field(min_length=1)
    baseline: FourGateM2BaselineReference
    successor_review_artifact: FourGateM2ArtifactReference
    integrated_assessment: FourGateIntegratedAssessmentSuccess


class FourGateM2SuccessorDecisionPackage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    run_id: str = Field(min_length=1)
    baseline: FourGateM2BaselineReference
    successor_assessment_artifact: FourGateM2ArtifactReference
    decision_package: FourGateDecisionPackageSuccess


class FourGateM2DecisionSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_status: DecisionStatus
    change_disposition: ChangeDisposition
    readiness_disposition: ReadinessDisposition
    selected_intervention_family: SelectedInterventionFamily
    autonomy_ceiling: AutonomyCeiling
    outcome_code: OutcomeCode
    gate_results: list[FourGateResult] = Field(min_length=4, max_length=4)
    priority_status: FourGatePriorityStatus
    priority_score: float | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def validate_gate_order(self) -> Self:
        if [item.gate for item in self.gate_results] != list(FourGateName):
            raise ValueError("Comparison snapshots require four ordered gates")
        return self


class FourGateM2BaselineSuccessorComparison(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    comparison_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    created_at: datetime
    baseline: FourGateM2BaselineReference
    successor_package_artifact: FourGateM2ArtifactReference
    target_step_id: str = Field(min_length=1)
    changed_field_path: Literal["characteristics.data_readiness"] = (
        "characteristics.data_readiness"
    )
    baseline_data_readiness: None = None
    baseline_data_readiness_knowledge_state: Literal[KnowledgeState.UNKNOWN] = (
        KnowledgeState.UNKNOWN
    )
    successor_data_readiness: int = Field(ge=0, le=5)
    successor_data_readiness_knowledge_state: Literal[KnowledgeState.KNOWN] = (
        KnowledgeState.KNOWN
    )
    baseline_evidence_ids: list[str]
    successor_evidence_ids: list[str] = Field(min_length=1)
    baseline_decision: FourGateM2DecisionSnapshot
    successor_decision: FourGateM2DecisionSnapshot
    categories: list[str] = Field(min_length=1)
    neutral_explanation: str = Field(min_length=1)
