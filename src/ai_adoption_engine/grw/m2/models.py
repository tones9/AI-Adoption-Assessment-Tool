"""Immutable contracts for the deliberately narrow GRW M2 M1 path."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_adoption_engine.models.decision_support import DecisionPackageSuccess, InformationGap
from ai_adoption_engine.models.enums import CriterionName, KnowledgeState
from ai_adoption_engine.models.integrated_assessment import IntegratedAssessmentSuccess
from ai_adoption_engine.models.process import BusinessProcess
from ai_adoption_engine.models.review import ApprovedProcessReview


class M2RunStage(StrEnum):
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
    WITHDRAWN = "WITHDRAWN"
    FAILED = "FAILED"


class M2ArtifactType(StrEnum):
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


class M2EvidenceClass(StrEnum):
    """M2 evidence state; documentary support is earned through review."""

    DOCUMENT_SUPPORTED_CANDIDATE = "DOCUMENT_SUPPORTED_CANDIDATE"
    DOCUMENT_SUPPORTED = "DOCUMENT_SUPPORTED"


class M2EvidencePermission(StrEnum):
    REJECTED = "REJECTED"
    INSUFFICIENT_FOR_THIS_USE = "INSUFFICIENT_FOR_THIS_USE"
    CRITERION_RESOLUTION_AND_GATE_ADMISSIBLE = "CRITERION_RESOLUTION_AND_GATE_ADMISSIBLE"


class M2ConflictStatus(StrEnum):
    CONSISTENT = "CONSISTENT"
    PARTIALLY_OVERLAPPING = "PARTIALLY_OVERLAPPING"
    CONTRADICTORY = "CONTRADICTORY"
    DIFFERENT_SCOPE = "DIFFERENT_SCOPE"
    STALE_OR_SUPERSEDED = "STALE_OR_SUPERSEDED"
    UNRESOLVED = "UNRESOLVED"


class M2ArtifactReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: str = Field(min_length=1)
    artifact_revision: int = Field(ge=1)
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class M2BaselineReference(BaseModel):
    """Hash-pinned historical chain. M2 does not own or update it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    assessment_id: str = Field(min_length=1)
    execution_mode: str = Field(min_length=1)
    source_document_id: str = Field(pattern=r"^doc-[0-9a-f]{64}$")
    approved_review: M2ArtifactReference
    integrated_assessment: M2ArtifactReference
    decision_package: M2ArtifactReference
    package_id: str = Field(min_length=1)
    validated_process_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision_policy_id: str = Field(min_length=1)
    decision_policy_version: str = Field(min_length=1)
    decision_policy_status: str = Field(min_length=1)
    decision_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class M2StepGapReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    package_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    current_activity: str = Field(min_length=1)
    information_gap: InformationGap
    baseline_value: int | None = None
    baseline_knowledge_state: KnowledgeState

    @model_validator(mode="after")
    def validate_target(self) -> "M2StepGapReference":
        if self.information_gap.step_id != self.step_id:
            raise ValueError("The information gap must belong to the selected step")
        if self.information_gap.field_name != CriterionName.DATA_READINESS.value:
            raise ValueError("M2 M1 supports data_readiness only")
        if self.baseline_knowledge_state is not KnowledgeState.UNKNOWN or self.baseline_value is not None:
            raise ValueError("M2 M1 requires an UNKNOWN baseline data_readiness criterion")
        return self


class VersionedPolicyReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class M2ActorDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str = Field(min_length=1, max_length=200)
    declared_role: str = Field(min_length=1, max_length=200)
    acknowledged_local_role_limitation: bool
    declared_at: datetime


class M2SupportingDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str = Field(pattern=r"^doc-[0-9a-f]{64}$")
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    content_type: str = "text/plain"
    filename: str = Field(min_length=1, max_length=255)
    byte_length: int = Field(gt=0)
    received_at: datetime
    source_label: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_identity(self) -> "M2SupportingDocument":
        if self.document_id != f"doc-{self.content_sha256}":
            raise ValueError("Document ID must be derived from the original byte hash")
        if self.content_type != "text/plain":
            raise ValueError("M2 M1 accepts text/plain documents only")
        return self


class M2DocumentLocator(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    exact_excerpt: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_offsets(self) -> "M2DocumentLocator":
        if self.end_offset <= self.start_offset or self.line_end < self.line_start:
            raise ValueError("Locator end must follow its start")
        return self


class M2DocumentSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    submission_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    submitted_at: datetime
    baseline: M2BaselineReference
    gap: M2StepGapReference
    document: M2SupportingDocument
    submitter: M2ActorDeclaration
    evidence_class: Literal[M2EvidenceClass.DOCUMENT_SUPPORTED_CANDIDATE] = (
        M2EvidenceClass.DOCUMENT_SUPPORTED_CANDIDATE
    )


class M2EvidenceReview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    review_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    submission_artifact: M2ArtifactReference
    reviewed_at: datetime
    reviewer: M2ActorDeclaration
    locator: M2DocumentLocator
    scope_statement: str = Field(min_length=1)
    period_statement: str = Field(min_length=1)
    source_authority: str = Field(min_length=1)
    semantic_rationale: str = Field(min_length=1)
    limitations: str = Field(min_length=1)
    conflict_status: M2ConflictStatus
    conflict_rationale: str = Field(min_length=1)
    reconciliation_statement: str | None = None
    applicability_statement: str | None = None
    permission: M2EvidencePermission
    evidence_class: M2EvidenceClass | None = None
    admissibility_policy: VersionedPolicyReference

    @model_validator(mode="after")
    def validate_review_outcome(self) -> "M2EvidenceReview":
        if self.permission is M2EvidencePermission.CRITERION_RESOLUTION_AND_GATE_ADMISSIBLE:
            if self.evidence_class is not M2EvidenceClass.DOCUMENT_SUPPORTED:
                raise ValueError("Only accepted M2 evidence may become DOCUMENT_SUPPORTED")
        elif self.evidence_class is not None:
            raise ValueError("Rejected or insufficient evidence cannot become DOCUMENT_SUPPORTED")
        return self


class M2DataReadinessResolution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    resolution_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    evidence_review_artifact: M2ArtifactReference
    criterion: CriterionName = CriterionName.DATA_READINESS
    baseline_value: int | None = None
    baseline_knowledge_state: KnowledgeState
    proposed_value: int | None = Field(default=None, ge=0, le=4)
    proposed_knowledge_state: KnowledgeState
    mapping_rationale: str = Field(min_length=1)
    document_locators: list[M2DocumentLocator] = Field(min_length=1)
    permitted_gate: Literal["technical_fit"] = "technical_fit"
    narrowed_scope_statement: str | None = None
    data_owner_reconciliation: str | None = None
    data_owner: M2ActorDeclaration
    criterion_reviewer: M2ActorDeclaration
    instrument: VersionedPolicyReference
    admissibility_policy: VersionedPolicyReference

    @model_validator(mode="after")
    def validate_resolution(self) -> "M2DataReadinessResolution":
        if self.criterion is not CriterionName.DATA_READINESS:
            raise ValueError("M2 M1 resolves data_readiness only")
        if self.baseline_knowledge_state is not KnowledgeState.UNKNOWN or self.baseline_value is not None:
            raise ValueError("M2 M1 resolves only an UNKNOWN baseline")
        if self.proposed_knowledge_state is KnowledgeState.UNKNOWN:
            if self.proposed_value is not None:
                raise ValueError("Retained UNKNOWN must not include a value")
        elif self.proposed_knowledge_state is KnowledgeState.KNOWN:
            if self.proposed_value is None:
                raise ValueError("A known resolution needs an instrument value")
        else:
            raise ValueError("M2 M1 does not create inferred values")
        return self


class M2ReassessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    requested_at: datetime
    baseline: M2BaselineReference
    gap: M2StepGapReference
    evidence_review_artifact: M2ArtifactReference
    resolution_artifact: M2ArtifactReference
    conflict_status: M2ConflictStatus
    data_owner: M2ActorDeclaration
    criterion_reviewer: M2ActorDeclaration
    baseline_decision_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    admissibility_policy: VersionedPolicyReference
    instrument: VersionedPolicyReference


class M2ReassessmentApproval(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    approval_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    request_artifact: M2ArtifactReference
    approved_at: datetime
    approver: M2ActorDeclaration
    rationale: str = Field(min_length=1)
    exact_change: str = Field(min_length=1)
    retained_uncertainty: str = Field(min_length=1)
    conflict_status: M2ConflictStatus
    acknowledged_no_verified_role_separation: bool
    baseline_remains_active: bool = True


class M2SuccessorApprovedReview(BaseModel):
    """The M2 projection, not a replacement for the historical Phase 4 approval."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    successor_review_id: str = Field(min_length=1)
    successor_approval_event_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    baseline_approved_review: M2ArtifactReference
    request_artifact: M2ArtifactReference
    approval_artifact: M2ArtifactReference
    evidence_review_artifact: M2ArtifactReference
    resolution_artifact: M2ArtifactReference
    data_readiness_resolution: M2DataReadinessResolution
    baseline_approved: ApprovedProcessReview
    successor_process: BusinessProcess
    target_step_id: str = Field(min_length=1)
    changed_field_path: str = Field(min_length=1)
    supporting_document: M2SupportingDocument
    locator: M2DocumentLocator
    successor_process_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class M2SuccessorAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1)
    successor_review_artifact: M2ArtifactReference
    request_artifact: M2ArtifactReference
    approval_artifact: M2ArtifactReference
    evidence_review_artifact: M2ArtifactReference
    resolution_artifact: M2ArtifactReference
    integrated_assessment: IntegratedAssessmentSuccess
    baseline: M2BaselineReference
    admissibility_policy: VersionedPolicyReference
    instrument: VersionedPolicyReference


class M2SuccessorDecisionPackage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1)
    successor_assessment_artifact: M2ArtifactReference
    request_artifact: M2ArtifactReference
    approval_artifact: M2ArtifactReference
    evidence_review_artifact: M2ArtifactReference
    resolution_artifact: M2ArtifactReference
    decision_package: DecisionPackageSuccess
    baseline: M2BaselineReference


class M2BaselineSuccessorComparison(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    comparison_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    created_at: datetime
    baseline: M2BaselineReference
    successor_package_artifact: M2ArtifactReference
    target_step_id: str = Field(min_length=1)
    baseline_data_readiness: int | None
    successor_data_readiness: int | None
    baseline_recommendation: str = Field(min_length=1)
    successor_recommendation: str = Field(min_length=1)
    categories: list[str] = Field(min_length=1)
    neutral_explanation: str = Field(min_length=1)
