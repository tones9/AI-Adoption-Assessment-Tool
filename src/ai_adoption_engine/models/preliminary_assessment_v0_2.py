"""Frozen domain contracts for the persistence-free Preliminary Assessment v0.2."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


OUTPUT_SCHEMA_ID = "preliminary-assessment.v0.2"
EVALUATOR_ID = "preliminary-evaluator.v0.2"
EVALUATOR_VERSION = "0.2.0"
RULE_SET_ID = "preliminary-evaluator-rules.v0.2"
RULE_SET_VERSION = "0.2.0"
CONTRACT_STATUS = "PROVISIONAL EXPLORATION — NOT VALIDATED"
DISCLAIMER = (
    "Provisional exploration only. This Preliminary Assessment is not an "
    "organisational decision, formal outcome, gate result, Decision Package, or "
    "approval to implement. It does not satisfy formal evidence requirements."
)


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def canonical_json_bytes(value: Any) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def content_id(prefix: str, payload: dict[str, Any]) -> str:
    return prefix + hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


class KnowledgeClassification(StrEnum):
    DOCUMENTED_FACT = "DOCUMENTED_FACT"
    REVIEWED_INFERENCE = "REVIEWED_INFERENCE"
    RULE_DERIVED_INFERENCE = "RULE_DERIVED_INFERENCE"
    UNKNOWN = "UNKNOWN"
    CONFLICT = "CONFLICT"
    CONTEXT_ONLY_HUMAN_DECLARATION = "CONTEXT_ONLY_HUMAN_DECLARATION"


class ComponentAction(StrEnum):
    READ = "READ"
    INTERPRET = "INTERPRET"
    INVESTIGATE = "INVESTIGATE"
    ASSESS = "ASSESS"
    CATEGORISE = "CATEGORISE"
    RETRIEVE = "RETRIEVE"
    COMPARE = "COMPARE"
    RECOMMEND = "RECOMMEND"
    DECIDE = "DECIDE"
    APPROVE = "APPROVE"
    DRAFT = "DRAFT"
    SUMMARISE = "SUMMARISE"
    RECORD = "RECORD"
    UPDATE = "UPDATE"
    TRANSFORM = "TRANSFORM"
    NOTIFY = "NOTIFY"
    ROUTE = "ROUTE"
    ASSIGN = "ASSIGN"
    SCHEDULE = "SCHEDULE"
    MONITOR = "MONITOR"
    CONTACT = "CONTACT"
    NEGOTIATE = "NEGOTIATE"
    FOLLOW_UP = "FOLLOW_UP"
    OTHER_SUPPORTED_ACTION = "OTHER_SUPPORTED_ACTION"


class WorkNeedType(StrEnum):
    INTERPRET_INFORMATION = "INTERPRET_INFORMATION"
    INVESTIGATE_MATTER = "INVESTIGATE_MATTER"
    CATEGORISE_ITEM = "CATEGORISE_ITEM"
    RETRIEVE_KNOWLEDGE = "RETRIEVE_KNOWLEDGE"
    COMPARE_OR_RECOMMEND = "COMPARE_OR_RECOMMEND"
    CREATE_CONTENT = "CREATE_CONTENT"
    PREDICT_OR_DETECT_PATTERN = "PREDICT_OR_DETECT_PATTERN"
    MAKE_ACCOUNTABLE_DECISION = "MAKE_ACCOUNTABLE_DECISION"
    INTERACT_WITH_PERSON = "INTERACT_WITH_PERSON"
    RECORD_INFORMATION = "RECORD_INFORMATION"
    TRANSFORM_INFORMATION = "TRANSFORM_INFORMATION"
    ROUTE_OR_NOTIFY = "ROUTE_OR_NOTIFY"
    SCHEDULE_OR_MONITOR = "SCHEDULE_OR_MONITOR"
    IMPROVE_PROCESS_FLOW = "IMPROVE_PROCESS_FLOW"
    OTHER_SUPPORTED_NEED = "OTHER_SUPPORTED_NEED"


class ProvisionalDirectionV2(StrEnum):
    LIKELY_NO_CHANGE = "LIKELY_NO_CHANGE"
    LIKELY_PROCESS_IMPROVEMENT_FIRST = "LIKELY_PROCESS_IMPROVEMENT_FIRST"
    LIKELY_CONVENTIONAL_AUTOMATION = "LIKELY_CONVENTIONAL_AUTOMATION"
    LIKELY_HUMAN_LED = "LIKELY_HUMAN_LED"
    POTENTIAL_AI_ASSISTED_WORK = "POTENTIAL_AI_ASSISTED_WORK"
    POTENTIAL_AI_AUTOMATION = "POTENTIAL_AI_AUTOMATION"
    INSUFFICIENT_BASIS_TO_SUGGEST_A_DIRECTION = (
        "INSUFFICIENT_BASIS_TO_SUGGEST_A_DIRECTION"
    )


class EvidenceCoverage(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ActivityResultType(StrEnum):
    ACTIONABLE = "ACTIONABLE"
    DISCOVERY_REQUIRED = "DISCOVERY_REQUIRED"
    NO_CHANGE = "NO_CHANGE"


class SourceSpan(_Frozen):
    source_document_id: str = Field(min_length=1)
    approved_review_artifact_id: str = Field(min_length=1)
    approved_evidence_item_id: str = Field(min_length=1)
    source_block_id: str = Field(min_length=1)
    document_start: int = Field(ge=0)
    document_end: int = Field(gt=0)
    block_start: int = Field(ge=0)
    block_end: int = Field(gt=0)
    exact_text: str = Field(min_length=1)
    source_locator: str = Field(min_length=1)
    fact_or_reviewed_inference_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_offsets(self) -> "SourceSpan":
        if self.document_end <= self.document_start or self.block_end <= self.block_start:
            raise ValueError("Source spans must be non-empty half-open ranges")
        if self.document_end - self.document_start != len(self.exact_text):
            raise ValueError("Document offsets must match exact_text length")
        if self.block_end - self.block_start != len(self.exact_text):
            raise ValueError("Block offsets must match exact_text length")
        return self

    def signature(self) -> tuple[str, int, int, str, str]:
        return (
            self.source_document_id,
            self.document_start,
            self.document_end,
            self.approved_evidence_item_id,
            self.fact_or_reviewed_inference_id,
        )


class MatchedSubSpan(_Frozen):
    parent_source_span_signature: tuple[str, int, int, str, str]
    match_start_in_span: int = Field(ge=0)
    match_end_in_span: int = Field(gt=0)
    exact_matched_text: str = Field(min_length=1)
    normalized_matched_key: str = Field(min_length=1)
    matched_literal_code: str = Field(pattern=r"^PD2-\d{3}-L\d{3}$")

    @model_validator(mode="after")
    def validate_match(self) -> "MatchedSubSpan":
        if self.match_end_in_span <= self.match_start_in_span:
            raise ValueError("Matched sub-spans must be non-empty")
        if self.match_end_in_span - self.match_start_in_span != len(
            self.exact_matched_text
        ):
            raise ValueError("Matched sub-span offsets must match exact text")
        return self


class EvidenceRecord(_Frozen):
    item_id: str = Field(min_length=1)
    classification: KnowledgeClassification
    statement: str = Field(min_length=1)
    source_spans: tuple[SourceSpan, ...] = ()


class RuleDerivedInference(_Frozen):
    inference_id: str = Field(pattern=r"^pri2-[0-9a-f]{64}$")
    pd2_rule_code: str = Field(pattern=r"^PD2-\d{3}$")
    matched_literal_code: str = Field(pattern=r"^PD2-\d{3}-L\d{3}$")
    normalized_derived_characteristic: dict[str, str | None]
    source_fact_ids: tuple[str, ...] = ()
    source_reviewed_inference_ids: tuple[str, ...] = ()
    source_spans: tuple[SourceSpan, ...] = Field(min_length=1)


class PreliminaryComponent(_Frozen):
    component_id: str = Field(pattern=r"^pac2-[0-9a-f]{64}$")
    activity_identity: str = Field(min_length=1)
    parent_step_sequence: int = Field(ge=1)
    source_field: str = Field(min_length=1)
    source_item_index: int = Field(ge=0)
    clause_index: int = Field(ge=0)
    matched_token_start: int = Field(ge=0)
    matched_token_end: int = Field(gt=0)
    pd2_rule_code: str = Field(pattern=r"^PD2-\d{3}$")
    matched_literal_code: str = Field(pattern=r"^PD2-\d{3}-L\d{3}$")
    component_action: ComponentAction
    normalized_actor: str | None = None
    normalized_object: str | None = None
    normalized_input_artifact: str | None = None
    normalized_output_artifact: str | None = None
    normalized_recipient: str | None = None
    normalized_destination: str | None = None
    source_fact_ids: tuple[str, ...] = ()
    source_reviewed_inference_ids: tuple[str, ...] = ()
    rule_derived_inference_id: str = Field(pattern=r"^pri2-[0-9a-f]{64}$")
    source_spans: tuple[SourceSpan, ...] = Field(min_length=1)
    matched_sub_spans: tuple[MatchedSubSpan, ...] = Field(min_length=1)
    dependency_component_ids: tuple[str, ...] = ()
    source_document_id: str = Field(min_length=1)
    owner_signature: tuple[str, ...] = Field(min_length=1)
    control_signature: tuple[str, ...] = Field(min_length=1)
    safety_signature: tuple[str, ...] = Field(min_length=1)
    accountability_signature: tuple[str, ...] = Field(min_length=1)
    conflict_signature: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_component(self) -> "PreliminaryComponent":
        if self.matched_token_end <= self.matched_token_start:
            raise ValueError("Matched token range must be non-empty")
        if any(item == self.component_id for item in self.dependency_component_ids):
            raise ValueError("A component cannot depend on itself")
        if any(span.source_document_id != self.source_document_id for span in self.source_spans):
            raise ValueError("Every source span must use the component source document")
        spans = {span.signature(): span for span in self.source_spans}
        for matched in self.matched_sub_spans:
            parent = spans.get(matched.parent_source_span_signature)
            if parent is None:
                raise ValueError("Matched sub-span must reference a component source span")
            if matched.match_end_in_span > len(parent.exact_text):
                raise ValueError("Matched sub-span must remain inside its parent span")
            if parent.exact_text[
                matched.match_start_in_span : matched.match_end_in_span
            ] != matched.exact_matched_text:
                raise ValueError("Matched sub-span text must equal the parent substring")
        return self


class WorkNeed(_Frozen):
    work_need_id: str = Field(pattern=r"^pwn2-[0-9a-f]{64}$")
    activity_identity: str = Field(min_length=1)
    work_need_type: WorkNeedType
    component_ids: tuple[str, ...] = Field(min_length=1)
    normalized_object_keys: tuple[str, ...] = Field(min_length=1)
    pd2_rule_codes: tuple[str, ...] = Field(min_length=1)


class DecisionTraceEntry(_Frozen):
    input_name: str = Field(min_length=1)
    normalized_value: str | int | bool | None = None
    knowledge_classification: KnowledgeClassification
    evidence_item_ids: tuple[str, ...] = ()
    material: bool
    evaluation_stage: str = Field(min_length=1)
    comparison_operator: str = Field(min_length=1)
    comparison_value: str | int | bool | None = None
    comparison_result: bool | None = None
    producing_pd2_code: str | None = None
    candidate_pa2_code: str | None = None
    selection_status: Literal["SELECTED", "REJECTED", "CONTEXT"]
    precedence_or_rejection_code: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unknown_value(self) -> "DecisionTraceEntry":
        if self.knowledge_classification in {
            KnowledgeClassification.UNKNOWN,
            KnowledgeClassification.CONFLICT,
        } and self.normalized_value is not None:
            raise ValueError("Unknown and conflict trace inputs have null values")
        return self


class Opportunity(_Frozen):
    opportunity_id: str = Field(pattern=r"^pop2-[0-9a-f]{64}$")
    activity_identity: str = Field(min_length=1)
    direction: ProvisionalDirectionV2
    deciding_rule_code: str = Field(pattern=r"^PA2-\d{3}$")
    construction_code: Literal["POG2-001", "POG2-002", "POG2-003", "POG2-004"]
    component_ids: tuple[str, ...] = Field(min_length=1)
    work_need_ids: tuple[str, ...] = Field(min_length=1)
    owner_signature: tuple[str, ...] = Field(min_length=1)
    control_signature: tuple[str, ...] = Field(min_length=1)
    safety_signature: tuple[str, ...] = Field(min_length=1)
    accountability_signature: tuple[str, ...] = Field(min_length=1)
    conflict_ids: tuple[str, ...] = ()
    material_evidence_item_ids: tuple[str, ...] = ()
    material_inference_ids: tuple[str, ...] = ()
    material_unknown_ids: tuple[str, ...] = ()
    source_spans: tuple[SourceSpan, ...] = Field(min_length=1)
    decision_input_trace: tuple[DecisionTraceEntry, ...] = Field(min_length=1)
    evidence_coverage: EvidenceCoverage
    rationale: str = Field(min_length=1)


class ScopedDiscoveryNeed(_Frozen):
    scoped_discovery_id: str = Field(pattern=r"^psd2-[0-9a-f]{64}$")
    activity_identity: str = Field(min_length=1)
    discovery_reason_code: Literal[
        "NO_DIRECTION_BEARING_EVIDENCE",
        "MATERIAL_EVIDENCE_CONFLICT",
        "INSEPARABLE_SCOPE",
        "UNSUPPORTED_CHARACTERISTIC",
        "MISSING_REQUIRED_COMPONENT_FIELD",
        "UNRESOLVED_HIGH_RISK",
        "OPPORTUNITY_PARTITION_EXCEEDS_LIMIT",
    ]
    evidence_request_codes: tuple[str, ...] = Field(min_length=1)
    related_component_ids: tuple[str, ...] = ()
    related_work_need_ids: tuple[str, ...] = ()
    material_evidence_item_ids: tuple[str, ...] = ()
    unknown_ids: tuple[str, ...] = ()
    conflict_ids: tuple[str, ...] = ()
    source_spans: tuple[SourceSpan, ...] = ()
    decision_input_trace: tuple[DecisionTraceEntry, ...] = Field(min_length=1)
    evidence_coverage: Literal[EvidenceCoverage.LOW] = EvidenceCoverage.LOW
    rationale: str = Field(min_length=1)


class PreliminaryActivityResultV2(_Frozen):
    result_type: ActivityResultType
    construction_code: Literal["PAR2-001", "PAR2-002", "PAR2-003", "PAR2-004"]
    activity_identity: str = Field(min_length=1)
    source_document_id: str = Field(min_length=1)
    evaluator_id: Literal["preliminary-evaluator.v0.2"] = EVALUATOR_ID
    evaluator_version: Literal["0.2.0"] = EVALUATOR_VERSION
    rule_set_id: Literal["preliminary-evaluator-rules.v0.2"] = RULE_SET_ID
    rule_set_version: Literal["0.2.0"] = RULE_SET_VERSION
    rule_set_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_schema_id: Literal["preliminary-assessment.v0.2"] = OUTPUT_SCHEMA_ID
    documented_facts: tuple[EvidenceRecord, ...] = ()
    reviewed_inferences: tuple[EvidenceRecord, ...] = ()
    rule_derived_inferences: tuple[RuleDerivedInference, ...] = ()
    unknowns: tuple[EvidenceRecord, ...] = ()
    conflicts: tuple[EvidenceRecord, ...] = ()
    components: tuple[PreliminaryComponent, ...] = ()
    work_needs: tuple[WorkNeed, ...] = ()
    opportunities: tuple[Opportunity, ...] = ()
    scoped_discoveries: tuple[ScopedDiscoveryNeed, ...] = ()
    candidate_partition_trace: tuple[str, ...] = ()
    decision_input_trace: tuple[DecisionTraceEntry, ...] = Field(min_length=1)
    evidence_coverage: EvidenceCoverage
    rationale: str = Field(min_length=1)
    next_evidence_to_collect: tuple[str, ...] = ()
    deciding_rule_code: str | None = None

    @model_validator(mode="after")
    def validate_variant(self) -> "PreliminaryActivityResultV2":
        component_sets = [set(item.component_ids) for item in self.opportunities]
        if any(component_sets[i] & component_sets[j] for i in range(len(component_sets)) for j in range(i)):
            raise ValueError("Opportunity component sets must be disjoint")
        if self.result_type is ActivityResultType.ACTIONABLE:
            if not 1 <= len(self.opportunities) <= 5 or self.construction_code not in {"PAR2-001", "PAR2-002"}:
                raise ValueError("ACTIONABLE requires one to five opportunities")
        elif self.result_type is ActivityResultType.DISCOVERY_REQUIRED:
            if self.opportunities or not self.scoped_discoveries or self.construction_code != "PAR2-003":
                raise ValueError("DISCOVERY_REQUIRED requires discoveries and no opportunities")
        else:
            if self.opportunities or self.scoped_discoveries or self.construction_code != "PAR2-004" or self.deciding_rule_code != "PA2-010":
                raise ValueError("NO_CHANGE requires the affirmative PA2-010 form")
        return self


class PreliminaryAssessmentLineageV2(_Frozen):
    source_document_id: str = Field(min_length=1)
    extraction_run_id: str = Field(min_length=1)
    approved_review_artifact_id: str = Field(min_length=1)
    approval_event_id: str = Field(min_length=1)
    validated_process_id: str = Field(min_length=1)
    validated_process_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class PreliminaryAssessmentV2(_Frozen):
    schema_version: Literal["preliminary-assessment.v0.2"] = OUTPUT_SCHEMA_ID
    assessment_kind: Literal["PRELIMINARY_ASSESSMENT"] = "PRELIMINARY_ASSESSMENT"
    status: Literal["PROVISIONAL EXPLORATION — NOT VALIDATED"] = CONTRACT_STATUS
    preliminary_assessment_id: str = Field(min_length=1)
    evaluator_id: Literal["preliminary-evaluator.v0.2"] = EVALUATOR_ID
    evaluator_version: Literal["0.2.0"] = EVALUATOR_VERSION
    rule_set_id: Literal["preliminary-evaluator-rules.v0.2"] = RULE_SET_ID
    rule_set_version: Literal["0.2.0"] = RULE_SET_VERSION
    rule_set_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    lineage: PreliminaryAssessmentLineageV2
    process_id: str = Field(min_length=1)
    process_name: str = Field(min_length=1)
    activity_results: tuple[PreliminaryActivityResultV2, ...] = Field(min_length=1)
    evidence_coverage: EvidenceCoverage
    high_activity_count: int = Field(ge=0)
    medium_activity_count: int = Field(ge=0)
    low_activity_count: int = Field(ge=0)
    disclaimer: Literal[
        "Provisional exploration only. This Preliminary Assessment is not an organisational decision, formal outcome, gate result, Decision Package, or approval to implement. It does not satisfy formal evidence requirements."
    ] = DISCLAIMER

    @model_validator(mode="after")
    def validate_counts_and_lineage(self) -> "PreliminaryAssessmentV2":
        counts = {
            EvidenceCoverage.HIGH: self.high_activity_count,
            EvidenceCoverage.MEDIUM: self.medium_activity_count,
            EvidenceCoverage.LOW: self.low_activity_count,
        }
        if sum(counts.values()) != len(self.activity_results):
            raise ValueError("Activity coverage counts must cover every activity")
        if any(item.source_document_id != self.lineage.source_document_id for item in self.activity_results):
            raise ValueError("Every activity must use the pinned source document")
        return self

    def canonical_json_bytes(self) -> bytes:
        return canonical_json_bytes(self)


class PreliminaryEvaluationFailureCodeV2(StrEnum):
    APPROVED_REVIEW_REQUIRED = "APPROVED_REVIEW_REQUIRED"
    INVALID_APPROVAL_ARTIFACT = "INVALID_APPROVAL_ARTIFACT"
    INVALID_PROCESS_PROJECTION = "INVALID_PROCESS_PROJECTION"
    INVALID_SOURCE_LINEAGE = "INVALID_SOURCE_LINEAGE"
    INVALID_SOURCE_SPAN = "INVALID_SOURCE_SPAN"
    INVALID_RULE_SET = "INVALID_RULE_SET"
    UNSUPPORTED_VERSION = "UNSUPPORTED_VERSION"
    OUTPUT_VALIDATION_FAILED = "OUTPUT_VALIDATION_FAILED"


class PreliminaryEvaluationErrorV2(_Frozen):
    code: PreliminaryEvaluationFailureCodeV2
    message: str = Field(min_length=1)
    field_path: str | None = None


class PreliminaryEvaluationSuccessV2(_Frozen):
    status: Literal["SUCCESS"] = "SUCCESS"
    assessment: PreliminaryAssessmentV2


class PreliminaryEvaluationFailureV2(_Frozen):
    status: Literal["FAILURE"] = "FAILURE"
    evaluator_id: Literal["preliminary-evaluator.v0.2"] = EVALUATOR_ID
    evaluator_version: Literal["0.2.0"] = EVALUATOR_VERSION
    rule_set_id: Literal["preliminary-evaluator-rules.v0.2"] = RULE_SET_ID
    rule_set_version: Literal["0.2.0"] = RULE_SET_VERSION
    rule_set_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    errors: tuple[PreliminaryEvaluationErrorV2, ...] = Field(min_length=1)
    assessment: None = None


PreliminaryEvaluationResultV2 = PreliminaryEvaluationSuccessV2 | PreliminaryEvaluationFailureV2
