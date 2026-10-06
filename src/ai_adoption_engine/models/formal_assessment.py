"""Frozen, persistence-free contracts for explicit formal assessment runs.

The module deliberately contains data and validation only.  It does not project
inputs, derive guidance, persist records, invoke an assessment engine, or grant
approval or implementation authority.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

from ai_adoption_engine.models.enums import CriterionName, KnowledgeState
from ai_adoption_engine.models.evidence import EvidenceReference
from ai_adoption_engine.models.formal_evidence import (
    FORMAL_EVIDENCE_FAMILY,
    FORMAL_EVIDENCE_READINESS_SCHEMA,
    FORMAL_INPUT_CANDIDATE_SET_SCHEMA,
    FORMAL_INPUT_MAPPING_SCHEMA,
    FormalEvidenceLineage,
    FormalTarget,
    FormalTargetKind,
    RequestIdentity,
    ReviewerDeclaration,
)
from ai_adoption_engine.models.four_gate_assessment import (
    BlockingEvidenceGap,
    CapabilitySignalName,
    EvidenceProblemCode,
    FourGateName,
    FourGateProcessAssessment,
)
from ai_adoption_engine.models.process import BusinessProcess, ProcessStep


FORMAL_ASSESSMENT_RUN_STORE_ID = "formal-assessment-run-store.v0.1"
FORMAL_ASSESSMENT_RUN_STORE_VERSION = "0.1.0"
FORMAL_ASSESSMENT_INPUT_CHOICE_SCHEMA = "formal-assessment-input-choice.v0.1"
FORMAL_ASSESSMENT_AUTHORIZATION_SCHEMA = "formal-assessment-authorization.v0.1"
FORMAL_INPUT_CONFLICT_RESOLUTION_SCHEMA = "formal-input-conflict-resolution.v0.1"
FORMAL_ASSESSMENT_INPUT_PROJECTION_SCHEMA = "formal-assessment-input-projection.v0.1"
FORMAL_ASSESSMENT_RUN_MANIFEST_SCHEMA = "formal-assessment-run-manifest.v0.1"
FORMAL_ASSESSMENT_RUN_EVENT_SCHEMA = "formal-assessment-run-event.v0.1"
FORMAL_ASSESSMENT_RUN_STATE_SCHEMA = "formal-assessment-run-state.v0.1"
FORMAL_ASSESSMENT_RESULT_SCHEMA = "formal-assessment-result.v0.1"
FORMAL_ASSESSMENT_RESULT_SUPERSESSION_SCHEMA = (
    "formal-assessment-result-supersession.v0.1"
)
FORMAL_ASSESSMENT_RUN_REQUEST_SCHEMA = "formal-assessment-run-request.v0.1"
FORMAL_EVIDENCE_GUIDANCE_SCHEMA = "formal-evidence-guidance.v0.1"

FORMAL_INPUT_ADAPTER_ID = "formal-four-gate-input-adapter.v0.1"
FORMAL_INPUT_ADAPTER_VERSION = "0.1.0"
FORMAL_INPUT_ADAPTER_RULES_ID = "formal-four-gate-input-adapter-rules.v0.1"
FORMAL_INPUT_ADAPTER_RULES_FINGERPRINT = (
    "0472d8517f0a6176ac56ed5599b11c7b22d94092a8a85083551837fd54ec8b5d"
)
FORMAL_GUIDANCE_CATALOGUE_ID = "formal-evidence-guidance-catalogue.v0.1"
FORMAL_GUIDANCE_CATALOGUE_FINGERPRINT = (
    "99f10b4f527e3d920a3db0c9c9794086c84b0fa472b923437ea0e24264aab95c"
)
FOUR_GATE_POLICY_FINGERPRINT = (
    "0a2f0040f78e8a4a48b9cc1d9d72f79b4b980f75b85cbd4fcbd8d9ad556e08f2"
)

_SHA256_PATTERN = r"^[0-9a-f]{64}$"

FORMAL_EVIDENCE_GUIDANCE_CATALOGUE = {
    EvidenceProblemCode.UNKNOWN: (
        "Provide reviewed evidence that establishes the requested value or "
        "preserves it as unknown."
    ),
    EvidenceProblemCode.VALUE_MISSING: (
        "Provide a reviewed, typed value for the identified formal input."
    ),
    EvidenceProblemCode.INFERRED_CONFIDENCE_TOO_LOW: (
        "Provide stronger documented evidence or a sufficiently supported "
        "reviewed inference."
    ),
    EvidenceProblemCode.EVIDENCE_REFERENCE_MISSING: (
        "Provide exact reviewed evidence references for the identified value."
    ),
    EvidenceProblemCode.ACTIVITY_EVIDENCE_MISSING: (
        "Provide exact reviewed evidence for the identified activity."
    ),
}


def _canonical_json_bytes(value: Any) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def require_direct_utc_timestamps(self) -> Self:
        for field_name in type(self).model_fields:
            value = getattr(self, field_name)
            if isinstance(value, datetime) and (
                value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value)
            ):
                raise ValueError(f"{field_name} must be an explicit UTC timestamp")
        return self

    def canonical_json_bytes(self) -> bytes:
        return _canonical_json_bytes(self)


class FormalAssessmentInputMode(StrEnum):
    APPROVED_PROCESS_ONLY = "APPROVED_PROCESS_ONLY"
    APPROVED_PROCESS_WITH_SUPPORTING_EVIDENCE = (
        "APPROVED_PROCESS_WITH_SUPPORTING_EVIDENCE"
    )


class SupportingEvidenceDisposition(StrEnum):
    NO_SUPPORTING_HISTORY = "NO_SUPPORTING_HISTORY"
    CURRENT_SUPPORTING_EVIDENCE_INCLUDED = "CURRENT_SUPPORTING_EVIDENCE_INCLUDED"
    CURRENT_SUPPORTING_EVIDENCE_EXPLICITLY_EXCLUDED = (
        "CURRENT_SUPPORTING_EVIDENCE_EXPLICITLY_EXCLUDED"
    )


class SupportingDocumentRevisionPin(_FrozenContract):
    document_id: str = Field(min_length=1)
    document_content_sha256: str = Field(pattern=_SHA256_PATTERN)
    metadata_revision_id: str = Field(min_length=1)


class SupportingHistoryExclusion(_FrozenContract):
    lineage: FormalEvidenceLineage
    supporting_history_head_id: str = Field(min_length=1)
    supporting_history_head_sha256: str = Field(pattern=_SHA256_PATTERN)
    current_documents: tuple[SupportingDocumentRevisionPin, ...] = Field(min_length=1)
    confirmation: Literal["EXCLUDE CURRENT SUPPORTING EVIDENCE FROM THIS RUN"]
    history_effect: Literal["REFERENCE_ONLY_NO_DELETE_SUPERSESSION_OR_REWRITE"] = (
        "REFERENCE_ONLY_NO_DELETE_SUPERSESSION_OR_REWRITE"
    )
    declarant: ReviewerDeclaration
    rationale: str = Field(min_length=1)
    excluded_at: datetime
    request: RequestIdentity

    @model_validator(mode="after")
    def validate_exclusion_snapshot(self) -> Self:
        document_ids = [item.document_id for item in self.current_documents]
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("excluded current document identities must be unique")
        return self


class SupportingEvidenceCandidatePin(_FrozenContract):
    lineage: FormalEvidenceLineage
    supporting_history_head_id: str = Field(min_length=1)
    supporting_history_head_sha256: str = Field(pattern=_SHA256_PATTERN)
    candidate_contract: Literal["formal-input-candidate-set.v0.1"] = (
        FORMAL_INPUT_CANDIDATE_SET_SCHEMA
    )
    candidate_set_id: str = Field(min_length=1)
    candidate_set_payload_sha256: str = Field(pattern=_SHA256_PATTERN)
    readiness_contract: Literal["formal-evidence-readiness.v0.1"] = (
        FORMAL_EVIDENCE_READINESS_SCHEMA
    )
    readiness_id: str = Field(min_length=1)
    readiness_payload_sha256: str = Field(pattern=_SHA256_PATTERN)
    readiness_candidate_set_id: str = Field(min_length=1)
    readiness_candidate_set_payload_sha256: str = Field(pattern=_SHA256_PATTERN)
    readiness_status: Literal["READY_TO_ATTEMPT"]

    @model_validator(mode="after")
    def require_readiness_for_exact_candidate(self) -> Self:
        if (
            self.readiness_candidate_set_id != self.candidate_set_id
            or self.readiness_candidate_set_payload_sha256
            != self.candidate_set_payload_sha256
        ):
            raise ValueError("readiness must pin the exact candidate set and payload")
        return self


class FormalAssessmentInputChoice(_FrozenContract):
    schema_version: Literal["formal-assessment-input-choice.v0.1"]
    store_contract: Literal["formal-assessment-run-store.v0.1"]
    lineage: FormalEvidenceLineage
    mode: FormalAssessmentInputMode
    supporting_evidence_disposition: SupportingEvidenceDisposition
    supporting_candidate: SupportingEvidenceCandidatePin | None = None
    exclusion: SupportingHistoryExclusion | None = None
    explicit_user_confirmation: Literal[True]
    selected_at: datetime
    request: RequestIdentity

    @model_validator(mode="after")
    def validate_closed_choice(self) -> Self:
        if self.mode is FormalAssessmentInputMode.APPROVED_PROCESS_ONLY:
            if self.supporting_candidate is not None:
                raise ValueError("process-only mode cannot pin a candidate or readiness")
            if self.supporting_evidence_disposition is SupportingEvidenceDisposition.NO_SUPPORTING_HISTORY:
                if self.exclusion is not None:
                    raise ValueError("absent supporting history cannot have an exclusion")
            elif self.supporting_evidence_disposition is SupportingEvidenceDisposition.CURRENT_SUPPORTING_EVIDENCE_EXPLICITLY_EXCLUDED:
                if self.exclusion is None:
                    raise ValueError("existing supporting history requires an exclusion snapshot")
                if self.exclusion.lineage != self.lineage:
                    raise ValueError("supporting exclusion must share exact lineage")
            else:
                raise ValueError("process-only mode cannot include supporting evidence")
        else:
            if self.supporting_evidence_disposition is not SupportingEvidenceDisposition.CURRENT_SUPPORTING_EVIDENCE_INCLUDED:
                raise ValueError("supporting mode must include current supporting evidence")
            if self.supporting_candidate is None or self.exclusion is not None:
                raise ValueError("supporting mode requires one candidate pin and no exclusion")
            if self.supporting_candidate.lineage != self.lineage:
                raise ValueError("supporting candidate must share exact lineage")
        return self


class FormalRunLineage(_FrozenContract):
    formal_lifecycle_id: str = Field(min_length=1)
    authorization_id: str = Field(min_length=1)
    projection_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)


class FormalValueOrigin(StrEnum):
    APPROVED_PROCESS = "APPROVED_PROCESS"
    SUPPORTING_MAPPING = "SUPPORTING_MAPPING"
    CORROBORATED = "CORROBORATED"


FormalScalar = StrictInt | StrictBool | None


class FormalEvidenceReferencePin(_FrozenContract):
    evidence_id: str = Field(min_length=1)
    evidence_payload_sha256: str = Field(pattern=_SHA256_PATTERN)


class FormalMappingReferencePin(_FrozenContract):
    contract: Literal["formal-input-mapping.v0.1"] = FORMAL_INPUT_MAPPING_SCHEMA
    mapping_id: str = Field(min_length=1)
    mapping_payload_sha256: str = Field(pattern=_SHA256_PATTERN)


class CompetingFormalValue(_FrozenContract):
    lineage: FormalEvidenceLineage
    activity_id: str = Field(min_length=1)
    target: FormalTarget
    origin: FormalValueOrigin
    value: FormalScalar
    knowledge_state: KnowledgeState
    confidence: float | None = Field(default=None, ge=0, le=1)
    approved_process_field_path: str | None = Field(default=None, min_length=1)
    evidence: tuple[FormalEvidenceReferencePin, ...]
    supporting_mappings: tuple[FormalMappingReferencePin, ...] = ()

    @model_validator(mode="after")
    def validate_competing_value(self) -> Self:
        if self.knowledge_state is KnowledgeState.UNKNOWN:
            if self.value is not None or self.confidence is not None:
                raise ValueError("unknown alternatives require null value and confidence")
        elif self.value is None:
            raise ValueError("known or inferred alternatives require a value")
        if self.knowledge_state is KnowledgeState.INFERRED and self.confidence is None:
            raise ValueError("inferred alternatives require confidence")
        if self.target.kind is FormalTargetKind.CRITERION:
            if self.value is not None and (type(self.value) is not int or not 0 <= self.value <= 5):
                raise ValueError("criterion alternatives must be strict integers from 0 to 5")
        elif self.target.kind in {
            FormalTargetKind.HUMAN_ACCOUNTABILITY_REQUIRED,
            FormalTargetKind.CAPABILITY_SIGNAL,
        }:
            if self.value is not None and type(self.value) is not bool:
                raise ValueError("boolean alternatives must be strict booleans")
        elif self.value is not None:
            raise ValueError("activity evidence cannot carry a scalar alternative")
        if self.origin is FormalValueOrigin.APPROVED_PROCESS:
            if self.approved_process_field_path is None or self.supporting_mappings:
                raise ValueError("approved-process alternatives require only a process path")
        elif self.origin is FormalValueOrigin.SUPPORTING_MAPPING:
            if self.approved_process_field_path is not None or not self.supporting_mappings:
                raise ValueError("supporting alternatives require only supporting mapping pins")
        elif self.approved_process_field_path is None or not self.supporting_mappings:
            raise ValueError(
                "corroborated alternatives require a process path and supporting mappings"
            )
        if not self.evidence:
            raise ValueError("every competing alternative requires exact evidence")
        if len(self.evidence) != len({item.evidence_id for item in self.evidence}):
            raise ValueError("competing evidence identities must be unique")
        if len(self.supporting_mappings) != len(
            {item.mapping_id for item in self.supporting_mappings}
        ):
            raise ValueError("competing mapping identities must be unique")
        return self


class FormalInputConflictResolution(_FrozenContract):
    schema_version: Literal["formal-input-conflict-resolution.v0.1"]
    store_contract: Literal["formal-assessment-run-store.v0.1"]
    resolution_id: str = Field(min_length=1)
    lineage: FormalEvidenceLineage
    run_lineage: FormalRunLineage
    activity_id: str = Field(min_length=1)
    target: FormalTarget
    alternatives: tuple[CompetingFormalValue, ...] = Field(min_length=2)
    selected_value: FormalScalar
    selected_knowledge_state: KnowledgeState
    selected_confidence: float | None = Field(default=None, ge=0, le=1)
    reviewer: ReviewerDeclaration
    explicit_human_selection: Literal[True]
    rationale: str = Field(min_length=1)
    resolved_at: datetime
    request: RequestIdentity

    @model_validator(mode="after")
    def validate_resolution(self) -> Self:
        if self.run_lineage.formal_lifecycle_id != self.lineage.formal_lifecycle_id:
            raise ValueError("resolution run lineage must use the formal lifecycle")
        for alternative in self.alternatives:
            if (
                alternative.lineage != self.lineage
                or alternative.activity_id != self.activity_id
                or alternative.target != self.target
            ):
                raise ValueError("all alternatives require exact target and lineage")
        keys = [
            (item.value, item.knowledge_state, item.confidence)
            for item in self.alternatives
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("identical values combine provenance without a resolution")
        selected = (
            self.selected_value,
            self.selected_knowledge_state,
            self.selected_confidence,
        )
        if selected not in keys:
            raise ValueError("selected value must be one of the competing alternatives")
        return self


class ApprovedProcessAuthorizationPin(_FrozenContract):
    lineage: FormalEvidenceLineage
    source_extraction_run_id: str = Field(min_length=1)
    approval_event_id: str = Field(min_length=1)
    approved_at: datetime


class FormalAssessmentCompatibilityIdentity(_FrozenContract):
    adapter_id: Literal["formal-four-gate-input-adapter.v0.1"]
    adapter_version: Literal["0.1.0"]
    adapter_rules_id: Literal["formal-four-gate-input-adapter-rules.v0.1"]
    adapter_rules_fingerprint: Literal[
        "0472d8517f0a6176ac56ed5599b11c7b22d94092a8a85083551837fd54ec8b5d"
    ]
    engine_input_contract: Literal["phase1-v0.4"]
    framework_id: Literal["four-gate-framework.v0.1"]
    framework_version: Literal["0.1"]
    policy_id: Literal["decision_policy.v0.3"]
    policy_version: Literal["0.3.0"]
    policy_fingerprint: Literal[
        "0a2f0040f78e8a4a48b9cc1d9d72f79b4b980f75b85cbd4fcbd8d9ad556e08f2"
    ]
    engine_id: Literal["four-gate-assessment-engine.v0.1"]
    engine_version: Literal["0.1.0"]
    formal_evidence_contract: Literal["preliminary-formal-evidence.v0.1"]
    candidate_contract: Literal["formal-input-candidate-set.v0.1"]
    readiness_contract: Literal["formal-evidence-readiness.v0.1"]
    output_contract: Literal["phase1-v0.4"]
    guidance_catalogue_id: Literal["formal-evidence-guidance-catalogue.v0.1"]
    guidance_catalogue_fingerprint: Literal[
        "99f10b4f527e3d920a3db0c9c9794086c84b0fa472b923437ea0e24264aab95c"
    ]


class FormalAssessmentAuthorization(_FrozenContract):
    schema_version: Literal["formal-assessment-authorization.v0.1"]
    store_contract: Literal["formal-assessment-run-store.v0.1"]
    authorization_id: str = Field(min_length=1)
    run_lineage: FormalRunLineage
    approved_process: ApprovedProcessAuthorizationPin
    input_choice: FormalAssessmentInputChoice
    conflict_resolutions: tuple[FormalInputConflictResolution, ...] = ()
    compatibility: FormalAssessmentCompatibilityIdentity
    explicit_run_confirmation: Literal["ATTEMPT ORGANISATIONAL ASSESSMENT"]
    authorization_scope: Literal[
        "ASSESSMENT_RUN_ATTEMPT_ONLY_NOT_APPROVAL_OR_IMPLEMENTATION_AUTHORITY"
    ]
    request: RequestIdentity
    authorized_at: datetime

    @model_validator(mode="after")
    def validate_authorization(self) -> Self:
        lineage = self.approved_process.lineage
        if self.authorization_id != self.run_lineage.authorization_id:
            raise ValueError("authorization identity must match run lineage")
        if self.run_lineage.formal_lifecycle_id != lineage.formal_lifecycle_id:
            raise ValueError("authorization must use the active formal lifecycle")
        if self.input_choice.lineage != lineage:
            raise ValueError("input choice and approved process must share exact lineage")
        ids = [item.resolution_id for item in self.conflict_resolutions]
        if len(ids) != len(set(ids)):
            raise ValueError("conflict resolution identities must be unique")
        for resolution in self.conflict_resolutions:
            if resolution.lineage != lineage or resolution.run_lineage != self.run_lineage:
                raise ValueError("conflict resolutions require exact authorization lineage")
        if self.input_choice.mode is FormalAssessmentInputMode.APPROVED_PROCESS_ONLY and self.conflict_resolutions:
            raise ValueError("process-only authorization cannot require supporting conflicts")
        return self


class ProjectedValueOrigin(StrEnum):
    SOURCE_ONLY = "SOURCE_ONLY"
    CORROBORATED = "CORROBORATED"
    FILLED_UNKNOWN = "FILLED_UNKNOWN"
    EXPLICITLY_RESOLVED = "EXPLICITLY_RESOLVED"


class FormalFieldResolutionTrace(_FrozenContract):
    activity_id: str = Field(min_length=1)
    target: FormalTarget
    approved_process_field_path: str = Field(min_length=1)
    projected_field_path: str = Field(min_length=1)
    approved_value: FormalScalar
    approved_knowledge_state: KnowledgeState
    projected_value: FormalScalar
    projected_knowledge_state: KnowledgeState
    projected_confidence: float | None = Field(default=None, ge=0, le=1)
    origin: ProjectedValueOrigin
    evidence_ids: tuple[str, ...]
    supporting_mappings: tuple[FormalMappingReferencePin, ...] = ()
    conflict_resolution_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_origin(self) -> Self:
        if self.projected_knowledge_state is KnowledgeState.UNKNOWN:
            if self.projected_value is not None or self.projected_confidence is not None:
                raise ValueError("unknown projected values must remain null")
        elif self.projected_value is None:
            raise ValueError("known or inferred projected values require a value")
        if self.projected_knowledge_state is KnowledgeState.INFERRED and self.projected_confidence is None:
            raise ValueError("inferred projected values require confidence")
        if (
            self.projected_knowledge_state is not KnowledgeState.UNKNOWN
            and not self.evidence_ids
        ):
            raise ValueError("known or inferred projected values require evidence")
        if self.origin is ProjectedValueOrigin.SOURCE_ONLY:
            if self.supporting_mappings or self.conflict_resolution_id is not None:
                raise ValueError("source-only traces cannot claim supporting provenance")
            if (
                self.projected_value != self.approved_value
                or self.projected_knowledge_state is not self.approved_knowledge_state
            ):
                raise ValueError("source-only traces cannot change approved values")
        elif self.origin is ProjectedValueOrigin.EXPLICITLY_RESOLVED:
            if not self.supporting_mappings or self.conflict_resolution_id is None:
                raise ValueError("resolved traces require mappings and an exact resolution")
        elif self.conflict_resolution_id is not None or not self.supporting_mappings:
            raise ValueError("supporting traces require mappings without a resolution")
        if self.origin is ProjectedValueOrigin.FILLED_UNKNOWN:
            if self.approved_knowledge_state is not KnowledgeState.UNKNOWN:
                raise ValueError("filled-unknown traces require an approved unknown")
        if self.origin is ProjectedValueOrigin.CORROBORATED and (
            self.approved_value != self.projected_value
            or self.approved_knowledge_state is not self.projected_knowledge_state
        ):
            raise ValueError("corroboration cannot change an approved value")
        return self


def _target_key(target: FormalTarget) -> tuple[str, str]:
    if target.kind is FormalTargetKind.CRITERION:
        return target.kind.value, target.criterion.value
    if target.kind is FormalTargetKind.CAPABILITY_SIGNAL:
        return target.kind.value, target.capability_signal.value
    return target.kind.value, ""


def _input_for_target(step: ProcessStep, target: FormalTarget):
    if target.kind is FormalTargetKind.CRITERION:
        return step.characteristics.criterion(target.criterion)
    if target.kind is FormalTargetKind.HUMAN_ACCOUNTABILITY_REQUIRED:
        return step.characteristics.human_accountability_required
    if target.kind is FormalTargetKind.CAPABILITY_SIGNAL:
        return getattr(step.characteristics.capability_signals, target.capability_signal.value)
    raise ValueError("activity evidence has no scalar engine input")


def _expected_scalar_target_keys() -> list[tuple[str, str]]:
    return [
        *((FormalTargetKind.CRITERION.value, item.value) for item in CriterionName),
        (FormalTargetKind.HUMAN_ACCOUNTABILITY_REQUIRED.value, ""),
        *((FormalTargetKind.CAPABILITY_SIGNAL.value, item.value) for item in CapabilitySignalName),
    ]


def _expected_field_path(prefix: str, activity_id: str, target: FormalTarget) -> str:
    base = f"{prefix}.steps[step_id={activity_id}].characteristics"
    if target.kind is FormalTargetKind.CRITERION:
        return f"{base}.{target.criterion.value}"
    if target.kind is FormalTargetKind.HUMAN_ACCOUNTABILITY_REQUIRED:
        return f"{base}.human_accountability_required"
    return f"{base}.capability_signals.{target.capability_signal.value}"


class FormalAssessmentActivityProjection(_FrozenContract):
    activity_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    engine_input: ProcessStep
    field_resolutions: tuple[FormalFieldResolutionTrace, ...] = Field(min_length=21, max_length=21)
    activity_evidence: tuple[EvidenceReference, ...]

    @model_validator(mode="after")
    def validate_activity_projection(self) -> Self:
        if self.engine_input.step_id != self.activity_id or self.engine_input.sequence != self.sequence:
            raise ValueError("activity projection identity must match the engine input")
        keys = [_target_key(item.target) for item in self.field_resolutions]
        if keys != _expected_scalar_target_keys():
            raise ValueError("field traces must contain every scalar input in canonical order")
        for trace in self.field_resolutions:
            if trace.activity_id != self.activity_id:
                raise ValueError("field traces must use the projected activity")
            projected = _input_for_target(self.engine_input, trace.target)
            if (
                trace.projected_value != projected.value
                or trace.projected_knowledge_state is not projected.knowledge_state
                or trace.projected_confidence != projected.confidence
                or tuple(projected.evidence_ids) != trace.evidence_ids
            ):
                raise ValueError("field trace must exactly describe the engine input")
        if [item.evidence_id for item in self.activity_evidence] != self.engine_input.evidence_ids:
            raise ValueError(
                "activity evidence must exactly match engine-input activity evidence"
            )
        return self


_STRUCTURAL_STEP_FIELDS = (
    "step_id", "sequence", "activity", "description", "actor",
    "responsible_role", "systems", "inputs", "outputs", "dependencies", "exceptions",
)


class FormalAssessmentInputProjection(_FrozenContract):
    schema_version: Literal["formal-assessment-input-projection.v0.1"]
    store_contract: Literal["formal-assessment-run-store.v0.1"]
    projection_id: str = Field(min_length=1)
    run_lineage: FormalRunLineage
    authorization: FormalAssessmentAuthorization
    approved_process: BusinessProcess
    engine_input: BusinessProcess
    activities: tuple[FormalAssessmentActivityProjection, ...] = Field(min_length=1)
    complete_evidence: tuple[EvidenceReference, ...]
    projection_fingerprint: str | None = Field(default=None, pattern=_SHA256_PATTERN, frozen=True)

    @model_validator(mode="after")
    def validate_projection(self) -> Self:
        if self.projection_id != self.run_lineage.projection_id:
            raise ValueError("projection identity must match run lineage")
        if self.authorization.run_lineage != self.run_lineage:
            raise ValueError("projection and authorization require exact run lineage")
        lineage = self.authorization.approved_process.lineage
        if (
            self.approved_process.process_id != lineage.validated_process_id
            or self.engine_input.process_id != lineage.validated_process_id
        ):
            raise ValueError("projection process must match approved lineage")
        for field_name in ("process_id", "name", "description", "business_objective", "organisation"):
            if getattr(self.engine_input, field_name) != getattr(self.approved_process, field_name):
                raise ValueError("supporting inputs cannot change process structure")
        if len(self.engine_input.steps) != len(self.approved_process.steps):
            raise ValueError("supporting inputs cannot add or remove activities")
        for approved, projected in zip(self.approved_process.steps, self.engine_input.steps, strict=True):
            for field_name in _STRUCTURAL_STEP_FIELDS:
                if getattr(approved, field_name) != getattr(projected, field_name):
                    raise ValueError("supporting inputs cannot modify activity structure or order")
        activity_ids = [item.activity_id for item in self.activities]
        if activity_ids != [item.step_id for item in self.engine_input.steps]:
            raise ValueError("activities must match the engine input in exact order")
        if [item.engine_input for item in self.activities] != self.engine_input.steps:
            raise ValueError("activity engine inputs must equal the complete engine input")
        for approved_step, activity in zip(
            self.approved_process.steps,
            self.activities,
            strict=True,
        ):
            for trace in activity.field_resolutions:
                approved_value = _input_for_target(approved_step, trace.target)
                if (
                    trace.approved_value != approved_value.value
                    or trace.approved_knowledge_state
                    is not approved_value.knowledge_state
                ):
                    raise ValueError(
                        "field trace must exactly preserve the approved-process input"
                    )
                if (
                    trace.approved_process_field_path
                    != _expected_field_path(
                        "approved_process",
                        activity.activity_id,
                        trace.target,
                    )
                    or trace.projected_field_path
                    != _expected_field_path(
                        "engine_input",
                        activity.activity_id,
                        trace.target,
                    )
                ):
                    raise ValueError("field trace paths must be canonical")
        evidence_ids = [item.evidence_id for item in self.complete_evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("complete projection evidence identities must be unique")
        if self.engine_input.evidence != list(self.complete_evidence):
            raise ValueError("complete evidence must equal engine-input evidence")
        known_evidence = set(evidence_ids)
        traces = [trace for item in self.activities for trace in item.field_resolutions]
        if any(set(trace.evidence_ids) - known_evidence for trace in traces):
            raise ValueError("every projected value requires complete evidence provenance")
        mode = self.authorization.input_choice.mode
        if mode is FormalAssessmentInputMode.APPROVED_PROCESS_ONLY:
            if any(trace.origin is not ProjectedValueOrigin.SOURCE_ONLY for trace in traces):
                raise ValueError("process-only projections cannot contain supporting provenance")
        resolution_by_id = {
            item.resolution_id: item for item in self.authorization.conflict_resolutions
        }
        used_resolutions = {
            trace.conflict_resolution_id for trace in traces if trace.conflict_resolution_id
        }
        if used_resolutions != set(resolution_by_id):
            raise ValueError("every authorization conflict resolution must be used exactly by projection")
        for trace in traces:
            if trace.conflict_resolution_id:
                resolution = resolution_by_id[trace.conflict_resolution_id]
                if (
                    resolution.activity_id != trace.activity_id
                    or resolution.target != trace.target
                    or resolution.selected_value != trace.projected_value
                    or resolution.selected_knowledge_state is not trace.projected_knowledge_state
                    or resolution.selected_confidence != trace.projected_confidence
                ):
                    raise ValueError("resolved projection must equal the selected run-scoped value")
                source_alternatives = [
                    item
                    for item in resolution.alternatives
                    if item.origin
                    in {
                        FormalValueOrigin.APPROVED_PROCESS,
                        FormalValueOrigin.CORROBORATED,
                    }
                ]
                supporting_alternatives = [
                    item
                    for item in resolution.alternatives
                    if item.origin
                    in {
                        FormalValueOrigin.SUPPORTING_MAPPING,
                        FormalValueOrigin.CORROBORATED,
                    }
                ]
                if trace.approved_knowledge_state is KnowledgeState.UNKNOWN:
                    if source_alternatives or len(supporting_alternatives) < 2:
                        raise ValueError(
                            "a supporting conflict over an approved unknown cannot "
                            "invent an approved-process alternative"
                        )
                elif (
                    len(source_alternatives) != 1
                    or not supporting_alternatives
                    or source_alternatives[0].value != trace.approved_value
                    or source_alternatives[0].knowledge_state
                    is not trace.approved_knowledge_state
                    or source_alternatives[0].approved_process_field_path
                    != trace.approved_process_field_path
                ):
                    raise ValueError(
                        "resolved projection requires the exact approved-process alternative"
                    )
                resolved_mapping_ids = {
                    mapping.mapping_id
                    for alternative in supporting_alternatives
                    for mapping in alternative.supporting_mappings
                }
                if resolved_mapping_ids != {
                    mapping.mapping_id for mapping in trace.supporting_mappings
                }:
                    raise ValueError(
                        "resolved projection requires every exact supporting alternative"
                    )
        payload = self.model_dump(mode="json", exclude={"projection_fingerprint"})
        expected = _fingerprint(payload)
        if self.projection_fingerprint is not None and self.projection_fingerprint != expected:
            raise ValueError("projection_fingerprint must match canonical projection content")
        object.__setattr__(self, "projection_fingerprint", expected)
        return self


class FormalRunStatus(StrEnum):
    AUTHORIZED = "AUTHORIZED"
    RUNNING = "RUNNING"
    COMPLETED_PENDING_REVIEW = "COMPLETED_PENDING_REVIEW"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"
    ABANDONED = "ABANDONED"
    RETRY_AVAILABLE = "RETRY_AVAILABLE"
    STALE = "STALE"
    SUPERSEDED = "SUPERSEDED"


class FormalRunOperation(StrEnum):
    AUTHORIZE = "AUTHORIZE"
    START = "START"
    COMPLETE = "COMPLETE"
    FAIL = "FAIL"
    INTERRUPT = "INTERRUPT"
    ABANDON = "ABANDON"
    MARK_RETRY_AVAILABLE = "MARK_RETRY_AVAILABLE"
    MARK_STALE = "MARK_STALE"
    SUPERSEDE = "SUPERSEDE"


class FormalRunStaleReason(StrEnum):
    APPROVED_PROCESS_LINEAGE_NO_LONGER_ACTIVE = (
        "APPROVED_PROCESS_LINEAGE_NO_LONGER_ACTIVE"
    )
    SUPPORTING_CANDIDATE_OR_READINESS_NO_LONGER_CURRENT = (
        "SUPPORTING_CANDIDATE_OR_READINESS_NO_LONGER_CURRENT"
    )


class FormalAssessmentRunRequest(_FrozenContract):
    schema_version: Literal["formal-assessment-run-request.v0.1"]
    store_contract: Literal["formal-assessment-run-store.v0.1"]
    request: RequestIdentity
    operation: FormalRunOperation
    run_lineage: FormalRunLineage
    canonical_operation_payload_sha256: str = Field(pattern=_SHA256_PATTERN)
    requested_at: datetime


class FormalRunRecoveryLineage(_FrozenContract):
    run_id: str = Field(min_length=1)
    predecessor_attempt_number: int = Field(ge=1)
    root_attempt_number: Literal[1] = 1
    authorization_id: str = Field(min_length=1)
    projection_id: str = Field(min_length=1)
    projection_fingerprint: str = Field(pattern=_SHA256_PATTERN)
    input_mode: FormalAssessmentInputMode


class FormalAssessmentRunManifest(_FrozenContract):
    schema_version: Literal["formal-assessment-run-manifest.v0.1"]
    store_contract: Literal["formal-assessment-run-store.v0.1"]
    run_lineage: FormalRunLineage
    attempt_number: int = Field(ge=1)
    authorization: FormalAssessmentAuthorization
    projection: FormalAssessmentInputProjection
    recovery: FormalRunRecoveryLineage | None = None
    initial_status: Literal[FormalRunStatus.AUTHORIZED] = FormalRunStatus.AUTHORIZED
    request: FormalAssessmentRunRequest
    created_at: datetime

    @model_validator(mode="after")
    def validate_manifest(self) -> Self:
        if self.authorization.run_lineage != self.run_lineage or self.projection.run_lineage != self.run_lineage:
            raise ValueError("manifest pins one exact authorization and projection")
        if self.request.run_lineage != self.run_lineage or self.request.operation is not FormalRunOperation.AUTHORIZE:
            raise ValueError("manifest requires its exact authorization request")
        if (self.attempt_number == 1) != (self.recovery is None):
            raise ValueError("retry attempts require recovery lineage")
        if self.recovery is not None:
            if (
                self.recovery.run_id != self.run_lineage.run_id
                or self.recovery.predecessor_attempt_number
                != self.attempt_number - 1
                or self.recovery.authorization_id
                != self.authorization.authorization_id
                or self.recovery.projection_id != self.projection.projection_id
                or self.recovery.projection_fingerprint != self.projection.projection_fingerprint
                or self.recovery.input_mode is not self.authorization.input_choice.mode
            ):
                raise ValueError("recovery must reuse the original immutable projection and mode")
        return self


class FormalRunFailureDetails(_FrozenContract):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    retryable: StrictBool
    field_path: str | None = Field(default=None, min_length=1)
    activity_id: str | None = Field(default=None, min_length=1)


_ALLOWED_TRANSITIONS = {
    FormalRunOperation.START: {(FormalRunStatus.AUTHORIZED, FormalRunStatus.RUNNING)},
    FormalRunOperation.COMPLETE: {(FormalRunStatus.RUNNING, FormalRunStatus.COMPLETED_PENDING_REVIEW)},
    FormalRunOperation.FAIL: {(FormalRunStatus.RUNNING, FormalRunStatus.FAILED)},
    FormalRunOperation.INTERRUPT: {(FormalRunStatus.RUNNING, FormalRunStatus.INTERRUPTED)},
    FormalRunOperation.ABANDON: {
        (FormalRunStatus.AUTHORIZED, FormalRunStatus.ABANDONED),
        (FormalRunStatus.INTERRUPTED, FormalRunStatus.ABANDONED),
        (FormalRunStatus.RETRY_AVAILABLE, FormalRunStatus.ABANDONED),
    },
    FormalRunOperation.MARK_RETRY_AVAILABLE: {
        (FormalRunStatus.FAILED, FormalRunStatus.RETRY_AVAILABLE),
        (FormalRunStatus.INTERRUPTED, FormalRunStatus.RETRY_AVAILABLE),
    },
    FormalRunOperation.MARK_STALE: {
        (FormalRunStatus.AUTHORIZED, FormalRunStatus.STALE),
        (FormalRunStatus.COMPLETED_PENDING_REVIEW, FormalRunStatus.STALE),
    },
    FormalRunOperation.SUPERSEDE: {
        (FormalRunStatus.COMPLETED_PENDING_REVIEW, FormalRunStatus.SUPERSEDED),
    },
}


class FormalAssessmentRunEvent(_FrozenContract):
    schema_version: Literal["formal-assessment-run-event.v0.1"]
    store_contract: Literal["formal-assessment-run-store.v0.1"]
    event_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    run_lineage: FormalRunLineage
    operation: FormalRunOperation
    from_status: FormalRunStatus
    to_status: FormalRunStatus
    authorization_id: str = Field(min_length=1)
    projection_id: str = Field(min_length=1)
    projection_fingerprint: str = Field(pattern=_SHA256_PATTERN)
    failure: FormalRunFailureDetails | None = None
    stale_reason: FormalRunStaleReason | None = None
    request: FormalAssessmentRunRequest
    occurred_at: datetime

    @model_validator(mode="after")
    def validate_event(self) -> Self:
        if self.operation is FormalRunOperation.AUTHORIZE:
            raise ValueError("authorization is represented by the immutable manifest")
        if (self.from_status, self.to_status) not in _ALLOWED_TRANSITIONS[self.operation]:
            raise ValueError("invalid formal run state transition")
        if (
            self.authorization_id != self.run_lineage.authorization_id
            or self.projection_id != self.run_lineage.projection_id
            or self.request.run_lineage != self.run_lineage
            or self.request.operation is not self.operation
        ):
            raise ValueError("run event pins and request must match exact run lineage")
        if (self.operation is FormalRunOperation.FAIL) != (self.failure is not None):
            raise ValueError("failure details exist exactly for a failed transition")
        if (self.operation is FormalRunOperation.MARK_STALE) != (
            self.stale_reason is not None
        ):
            raise ValueError("stale reason exists exactly for a stale transition")
        return self


class FormalAssessmentRunState(_FrozenContract):
    schema_version: Literal["formal-assessment-run-state.v0.1"]
    store_contract: Literal["formal-assessment-run-store.v0.1"]
    manifest: FormalAssessmentRunManifest
    events: tuple[FormalAssessmentRunEvent, ...] = ()
    current_status: FormalRunStatus
    projected_at: datetime

    @model_validator(mode="after")
    def validate_projection(self) -> Self:
        status = FormalRunStatus.AUTHORIZED
        for expected_sequence, event in enumerate(self.events, start=1):
            if event.sequence != expected_sequence or event.run_lineage != self.manifest.run_lineage:
                raise ValueError("run events require contiguous sequence and exact lineage")
            if event.from_status is not status:
                raise ValueError("run event chain must be contiguous")
            if event.authorization_id != self.manifest.authorization.authorization_id or event.projection_fingerprint != self.manifest.projection.projection_fingerprint:
                raise ValueError("run events cannot change authorization or projection")
            if (
                event.stale_reason
                is FormalRunStaleReason.SUPPORTING_CANDIDATE_OR_READINESS_NO_LONGER_CURRENT
                and self.manifest.authorization.input_choice.mode
                is FormalAssessmentInputMode.APPROVED_PROCESS_ONLY
            ):
                raise ValueError(
                    "supporting-history changes cannot stale a process-only run"
                )
            status = event.to_status
        if self.current_status is not status:
            raise ValueError("current status must be derived from the event chain")
        return self


class FormalResultActivityTrace(_FrozenContract):
    activity_id: str = Field(min_length=1)
    projected_activity_path: str = Field(min_length=1)
    assessment_activity_path: str = Field(min_length=1)
    projection_fingerprint: str = Field(pattern=_SHA256_PATTERN)
    evidence_ids: tuple[str, ...]


class FormalAssessmentResult(_FrozenContract):
    schema_version: Literal["formal-assessment-result.v0.1"]
    store_contract: Literal["formal-assessment-run-store.v0.1"]
    result_id: str = Field(min_length=1)
    manifest: FormalAssessmentRunManifest
    status: Literal[FormalRunStatus.COMPLETED_PENDING_REVIEW] = FormalRunStatus.COMPLETED_PENDING_REVIEW
    customer_status: Literal[
        "Organisational assessment completed — review required"
    ] = "Organisational assessment completed — review required"
    assessment: FourGateProcessAssessment
    activity_traces: tuple[FormalResultActivityTrace, ...]
    completed_at: datetime
    implementation_approval_granted: Literal[False] = False
    decision_package_generated: Literal[False] = False

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        projection = self.manifest.projection
        compatibility = self.manifest.authorization.compatibility
        if (
            self.assessment.process_id != projection.engine_input.process_id
            or self.assessment.process_name != projection.engine_input.name
            or self.assessment.decision_contract_version != compatibility.output_contract
            or self.assessment.framework_id != compatibility.framework_id
            or self.assessment.framework_version != compatibility.framework_version
            or self.assessment.policy_id != compatibility.policy_id
            or self.assessment.policy_version != compatibility.policy_version
        ):
            raise ValueError("formal result must preserve every pinned strict identity")
        projected_ids = [item.activity_id for item in projection.activities]
        assessed_ids = [item.step_id for item in self.assessment.step_assessments]
        traced_ids = [item.activity_id for item in self.activity_traces]
        if assessed_ids != projected_ids or traced_ids != projected_ids:
            raise ValueError("result requires exactly one ordered assessment and trace per activity")
        evidence_by_activity = {
            item.activity_id: tuple(item.engine_input.evidence_ids)
            for item in projection.activities
        }
        for index, trace in enumerate(self.activity_traces):
            activity_id = projected_ids[index]
            if (
                trace.projected_activity_path != f"activities[{index}]"
                or trace.assessment_activity_path != f"assessment.step_assessments[{index}]"
                or trace.projection_fingerprint != projection.projection_fingerprint
                or trace.evidence_ids != evidence_by_activity[activity_id]
            ):
                raise ValueError("result activity trace must point to exact projected inputs")
        for projected_activity, assessed_activity in zip(
            projection.activities,
            self.assessment.step_assessments,
            strict=True,
        ):
            projected_step = projected_activity.engine_input
            if assessed_activity.activity != projected_step.activity:
                raise ValueError("assessment activity must equal the projected activity")
            for criterion_result, criterion_name in zip(
                assessed_activity.criteria,
                CriterionName,
                strict=True,
            ):
                projected_value = projected_step.characteristics.criterion(
                    criterion_name
                )
                if (
                    criterion_result.criterion is not criterion_name
                    or criterion_result.value != projected_value.value
                    or criterion_result.knowledge_state
                    is not projected_value.knowledge_state
                    or criterion_result.rationale != projected_value.rationale
                    or criterion_result.evidence_ids != projected_value.evidence_ids
                    or criterion_result.confidence != projected_value.confidence
                ):
                    raise ValueError(
                        "assessment criteria must exactly trace projected inputs"
                    )
            accountability = projected_step.characteristics.human_accountability_required
            accountability_result = assessed_activity.human_accountability
            if (
                accountability_result.value != accountability.value
                or accountability_result.knowledge_state
                is not accountability.knowledge_state
                or accountability_result.rationale != accountability.rationale
                or accountability_result.evidence_ids != accountability.evidence_ids
                or accountability_result.confidence != accountability.confidence
            ):
                raise ValueError(
                    "assessment accountability must exactly trace projected input"
                )
            for signal_result, signal_name in zip(
                assessed_activity.capability_signals,
                CapabilitySignalName,
                strict=True,
            ):
                projected_signal = getattr(
                    projected_step.characteristics.capability_signals,
                    signal_name.value,
                )
                if (
                    signal_result.signal is not signal_name
                    or signal_result.value != projected_signal.value
                    or signal_result.knowledge_state
                    is not projected_signal.knowledge_state
                    or signal_result.rationale != projected_signal.rationale
                    or signal_result.evidence_ids != projected_signal.evidence_ids
                    or signal_result.confidence != projected_signal.confidence
                ):
                    raise ValueError(
                        "assessment capability signals must exactly trace projected inputs"
                    )
        return self


class FormalAssessmentTerminalFailure(_FrozenContract):
    schema_version: Literal["formal-assessment-result.v0.1"]
    store_contract: Literal["formal-assessment-run-store.v0.1"]
    terminal_record_id: str = Field(min_length=1)
    manifest: FormalAssessmentRunManifest
    status: Literal[
        FormalRunStatus.FAILED,
        FormalRunStatus.INTERRUPTED,
        FormalRunStatus.ABANDONED,
    ]
    failure: FormalRunFailureDetails
    occurred_at: datetime
    assessment: Literal[None] = None


class FormalAssessmentResultSupersession(_FrozenContract):
    schema_version: Literal["formal-assessment-result-supersession.v0.1"]
    store_contract: Literal["formal-assessment-run-store.v0.1"]
    supersession_id: str = Field(min_length=1)
    formal_lifecycle_id: str = Field(min_length=1)
    superseded_result_id: str = Field(min_length=1)
    successor_result_id: str = Field(min_length=1)
    superseded_run_id: str = Field(min_length=1)
    successor_run_id: str = Field(min_length=1)
    predecessor_status: Literal[FormalRunStatus.COMPLETED_PENDING_REVIEW]
    successor_status: Literal[FormalRunStatus.COMPLETED_PENDING_REVIEW]
    rationale: str = Field(min_length=1)
    request: RequestIdentity
    superseded_at: datetime

    @model_validator(mode="after")
    def validate_supersession(self) -> Self:
        if self.superseded_result_id == self.successor_result_id or self.superseded_run_id == self.successor_run_id:
            raise ValueError("supersession requires a distinct later successful result")
        return self


class FormalEvidenceGuidanceItem(_FrozenContract):
    activity_id: str = Field(min_length=1)
    gate: FourGateName
    field_name: str = Field(min_length=1)
    problem_code: str = Field(min_length=1)
    blocking_question: str = Field(min_length=1)
    evidence_ids: tuple[str, ...]
    requested_information: str = Field(min_length=1)
    boundary_notice: Literal[
        "Requested information is not evidence; uploading a document does not guarantee a successful outcome."
    ]


class FormalEvidenceGuidance(_FrozenContract):
    schema_version: Literal["formal-evidence-guidance.v0.1"]
    store_contract: Literal["formal-assessment-run-store.v0.1"]
    guidance_id: str = Field(min_length=1)
    source_result: FormalAssessmentResult
    catalogue_id: Literal["formal-evidence-guidance-catalogue.v0.1"]
    catalogue_fingerprint: Literal[
        "99f10b4f527e3d920a3db0c9c9794086c84b0fa472b923437ea0e24264aab95c"
    ]
    source_gaps: tuple[BlockingEvidenceGap, ...]
    items: tuple[FormalEvidenceGuidanceItem, ...]
    generated_at: datetime
    derivation: Literal["DETERMINISTIC_CATALOGUE_ONLY_NO_LLM"]
    modifies_engine_result: Literal[False] = False

    @model_validator(mode="after")
    def validate_guidance_boundary(self) -> Self:
        exact_source_pairs = tuple(
            (activity.step_id, gap)
            for activity in self.source_result.assessment.step_assessments
            for gap in activity.blocking_gaps
        )
        if self.source_gaps != tuple(gap for _, gap in exact_source_pairs):
            raise ValueError(
                "guidance source gaps must equal the exact result blocking gaps"
            )
        if len(self.items) != len(exact_source_pairs):
            raise ValueError("guidance requires exactly one item per blocking gap")
        for item, (activity_id, gap) in zip(
            self.items,
            exact_source_pairs,
            strict=True,
        ):
            if (
                item.activity_id != activity_id
                or item.gate is not gap.gate
                or item.field_name != gap.field_name
                or item.problem_code != gap.problem_code.value
                or item.blocking_question != gap.blocking_question
                or item.evidence_ids != tuple(gap.evidence_ids)
                or item.requested_information
                != FORMAL_EVIDENCE_GUIDANCE_CATALOGUE[gap.problem_code]
            ):
                raise ValueError("guidance must preserve every strict blocking-gap field")
        return self
