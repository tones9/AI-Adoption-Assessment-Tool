"""Immutable contracts for the opt-in Preliminary Assessment journey.

These contracts describe provisional exploration only. They intentionally do not
depend on the formal four-gate assessment, gate-result, or package contracts.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)


JOURNEY_SELECTION_SCHEMA_VERSION = "journey-selection.v0.1"
PRELIMINARY_ASSESSMENT_SCHEMA_VERSION = "preliminary-assessment.v0.1"
PRELIMINARY_EVALUATOR_RULES_V0_1_FINGERPRINT = (
    "3db8a54561bcfe263a5483e5d4c49e203bfac40eafbc8bc778cf773ed6ad1790"
)
PRELIMINARY_ASSESSMENT_DISCLAIMER = (
    "Provisional exploration only. This Preliminary Assessment is not an "
    "official four-gate outcome, Decision Package, organisational assessment, "
    "or approval to implement."
)


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AssessmentJourney(StrEnum):
    EXPLORE_PROCESS = "EXPLORE_PROCESS"
    ORGANISATIONAL_ASSESSMENT = "ORGANISATIONAL_ASSESSMENT"


class ProvisionalDirection(StrEnum):
    LIKELY_NO_CHANGE = "Likely no change"
    LIKELY_PROCESS_IMPROVEMENT_FIRST = "Likely process improvement first"
    LIKELY_CONVENTIONAL_AUTOMATION = "Likely conventional automation"
    LIKELY_HUMAN_LED = "Likely human-led"
    POTENTIAL_AI_ASSISTED_WORK = "Potential AI-assisted work"
    POTENTIAL_AI_AUTOMATION = "Potential AI automation"
    INSUFFICIENT_BASIS = "Insufficient basis to suggest a direction"


class PreliminaryConfidence(StrEnum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class PreliminaryEvidenceClassification(StrEnum):
    DOCUMENTED = "DOCUMENTED"
    REASONABLE_INFERENCE = "REASONABLE_INFERENCE"
    UNKNOWN = "UNKNOWN"
    CONFLICT = "CONFLICT"


class PreliminaryEvaluationStage(StrEnum):
    CHANGE_CASE = "CHANGE_CASE"
    READINESS = "READINESS"
    INTERVENTION_SELECTION = "INTERVENTION_SELECTION"
    AI_CAPABILITY = "AI_CAPABILITY"
    SAFETY_PERMISSION = "SAFETY_PERMISSION"
    AUTONOMY = "AUTONOMY"


class PreliminaryValueType(StrEnum):
    ORDINAL = "ORDINAL"
    BOOLEAN = "BOOLEAN"
    TEXT = "TEXT"


class PreliminaryComparisonOperator(StrEnum):
    PRESENT = "PRESENT"
    LT = "LT"
    LTE = "LTE"
    EQ = "EQ"
    GTE = "GTE"
    GT = "GT"
    IS_TRUE = "IS_TRUE"
    IS_FALSE = "IS_FALSE"
    IS_UNKNOWN = "IS_UNKNOWN"
    IS_CONFLICT = "IS_CONFLICT"


class PreliminaryInputName(StrEnum):
    ACTIVITY_IDENTITY = "activity_identity"
    BUSINESS_VALUE = "business_value"
    DATA_READINESS = "data_readiness"
    IMPLEMENTATION_COMPLEXITY = "implementation_complexity"
    CONVENTIONAL_SOLUTION_FIT = "conventional_solution_fit"
    AI_CAPABILITY_FIT = "ai_capability_fit"
    CAPABILITY_READS_UNSTRUCTURED_DOCUMENTS = (
        "capability.reads_unstructured_documents"
    )
    CAPABILITY_CATEGORISES_ITEMS = "capability.categorises_items"
    CAPABILITY_PREDICTS_FUTURE_OUTCOMES = (
        "capability.predicts_future_outcomes"
    )
    CAPABILITY_DETECTS_ANOMALIES_OR_PATTERNS = (
        "capability.detects_anomalies_or_patterns"
    )
    CAPABILITY_CREATES_NEW_CONTENT = "capability.creates_new_content"
    CAPABILITY_SEARCHES_REFERENCE_KNOWLEDGE = (
        "capability.searches_reference_knowledge"
    )
    CAPABILITY_RANKS_OR_SUGGESTS_OPTIONS = (
        "capability.ranks_or_suggests_options"
    )
    CAPABILITY_SUPPORTS_COMPLEX_DECISIONS = (
        "capability.supports_complex_decisions"
    )
    CAPABILITY_INTERPRETS_IMAGES_OR_VIDEO = (
        "capability.interprets_images_or_video"
    )
    CAPABILITY_ROUTES_OR_ORCHESTRATES_WORK = (
        "capability.routes_or_orchestrates_work"
    )
    RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT = (
        "residual_risk_with_human_oversight"
    )
    HUMAN_JUDGEMENT_REQUIREMENT = "human_judgement_requirement"
    RISK_CONSEQUENCE = "risk_consequence"
    HUMAN_ACCOUNTABILITY_REQUIRED = "human_accountability_required"
    PREDICTABILITY = "predictability"
    REPETITION = "repetition"


CAPABILITY_INPUT_NAMES = (
    PreliminaryInputName.CAPABILITY_READS_UNSTRUCTURED_DOCUMENTS,
    PreliminaryInputName.CAPABILITY_CATEGORISES_ITEMS,
    PreliminaryInputName.CAPABILITY_PREDICTS_FUTURE_OUTCOMES,
    PreliminaryInputName.CAPABILITY_DETECTS_ANOMALIES_OR_PATTERNS,
    PreliminaryInputName.CAPABILITY_CREATES_NEW_CONTENT,
    PreliminaryInputName.CAPABILITY_SEARCHES_REFERENCE_KNOWLEDGE,
    PreliminaryInputName.CAPABILITY_RANKS_OR_SUGGESTS_OPTIONS,
    PreliminaryInputName.CAPABILITY_SUPPORTS_COMPLEX_DECISIONS,
    PreliminaryInputName.CAPABILITY_INTERPRETS_IMAGES_OR_VIDEO,
    PreliminaryInputName.CAPABILITY_ROUTES_OR_ORCHESTRATES_WORK,
)


PRELIMINARY_INPUT_ORDER = (
    PreliminaryInputName.ACTIVITY_IDENTITY,
    PreliminaryInputName.BUSINESS_VALUE,
    PreliminaryInputName.DATA_READINESS,
    PreliminaryInputName.IMPLEMENTATION_COMPLEXITY,
    PreliminaryInputName.CONVENTIONAL_SOLUTION_FIT,
    PreliminaryInputName.AI_CAPABILITY_FIT,
    *CAPABILITY_INPUT_NAMES,
    PreliminaryInputName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT,
    PreliminaryInputName.HUMAN_JUDGEMENT_REQUIREMENT,
    PreliminaryInputName.RISK_CONSEQUENCE,
    PreliminaryInputName.HUMAN_ACCOUNTABILITY_REQUIRED,
    PreliminaryInputName.PREDICTABILITY,
    PreliminaryInputName.REPETITION,
)


class PreliminaryDecidingRuleCode(StrEnum):
    INSUFFICIENT_ACTIVITY_IDENTITY = "PA-001"
    INSUFFICIENT_CHANGE_CASE = "PA-010"
    LIKELY_NO_CHANGE = "PA-011"
    LIKELY_PROCESS_IMPROVEMENT_FIRST = "PA-020"
    INSUFFICIENT_READINESS = "PA-021"
    INSUFFICIENT_CONVENTIONAL_FIT = "PA-030"
    LIKELY_CONVENTIONAL_AUTOMATION = "PA-031"
    INSUFFICIENT_AI_FIT = "PA-040"
    LIKELY_HUMAN_LED_LOW_AI_FIT = "PA-041"
    INSUFFICIENT_AI_CAPABILITY = "PA-042"
    LIKELY_HUMAN_LED_NO_CAPABILITY = "PA-043"
    LIKELY_HUMAN_LED_SAFETY_VETO = "PA-050"
    INSUFFICIENT_RESIDUAL_RISK = "PA-051"
    POTENTIAL_AI_ASSISTED_CONSTRAINT = "PA-052"
    POTENTIAL_AI_ASSISTED_AUTONOMY_UNKNOWN = "PA-053"
    POTENTIAL_AI_AUTOMATION = "PA-054"


class PreliminaryComparisonClause(StrEnum):
    ACTIVITY_PRESENT = "ACTIVITY_PRESENT"
    ACTIVITY_UNRESOLVED = "ACTIVITY_UNRESOLVED"
    BUSINESS_LT_MINIMUM = "BUSINESS_LT_MINIMUM"
    BUSINESS_GTE_MINIMUM = "BUSINESS_GTE_MINIMUM"
    BUSINESS_UNRESOLVED = "BUSINESS_UNRESOLVED"
    DATA_LT_MINIMUM = "DATA_LT_MINIMUM"
    DATA_GTE_MINIMUM = "DATA_GTE_MINIMUM"
    DATA_GTE_AUTOMATION = "DATA_GTE_AUTOMATION"
    DATA_LT_AUTOMATION = "DATA_LT_AUTOMATION"
    DATA_UNRESOLVED = "DATA_UNRESOLVED"
    COMPLEXITY_GT_READY_MAX = "COMPLEXITY_GT_READY_MAX"
    COMPLEXITY_LTE_READY_MAX = "COMPLEXITY_LTE_READY_MAX"
    COMPLEXITY_LTE_AUTOMATION_MAX = "COMPLEXITY_LTE_AUTOMATION_MAX"
    COMPLEXITY_GT_AUTOMATION_MAX = "COMPLEXITY_GT_AUTOMATION_MAX"
    COMPLEXITY_UNRESOLVED = "COMPLEXITY_UNRESOLVED"
    CONVENTIONAL_GTE_CUTOFF = "CONVENTIONAL_GTE_CUTOFF"
    CONVENTIONAL_LT_CUTOFF = "CONVENTIONAL_LT_CUTOFF"
    CONVENTIONAL_UNRESOLVED = "CONVENTIONAL_UNRESOLVED"
    AI_FIT_LT_MINIMUM = "AI_FIT_LT_MINIMUM"
    AI_FIT_GTE_MINIMUM = "AI_FIT_GTE_MINIMUM"
    AI_FIT_UNRESOLVED = "AI_FIT_UNRESOLVED"
    CAPABILITY_TRUE = "CAPABILITY_TRUE"
    CAPABILITY_FALSE = "CAPABILITY_FALSE"
    CAPABILITY_UNRESOLVED = "CAPABILITY_UNRESOLVED"
    RESIDUAL_GTE_VETO = "RESIDUAL_GTE_VETO"
    RESIDUAL_LT_VETO = "RESIDUAL_LT_VETO"
    RESIDUAL_EQ_ASSISTANCE = "RESIDUAL_EQ_ASSISTANCE"
    RESIDUAL_LTE_AUTOMATION_MAX = "RESIDUAL_LTE_AUTOMATION_MAX"
    RESIDUAL_UNRESOLVED = "RESIDUAL_UNRESOLVED"
    JUDGEMENT_GTE_ASSISTANCE = "JUDGEMENT_GTE_ASSISTANCE"
    JUDGEMENT_LT_ASSISTANCE = "JUDGEMENT_LT_ASSISTANCE"
    JUDGEMENT_UNRESOLVED = "JUDGEMENT_UNRESOLVED"
    CONSEQUENCE_GTE_ASSISTANCE = "CONSEQUENCE_GTE_ASSISTANCE"
    CONSEQUENCE_LT_ASSISTANCE = "CONSEQUENCE_LT_ASSISTANCE"
    CONSEQUENCE_UNRESOLVED = "CONSEQUENCE_UNRESOLVED"
    ACCOUNTABILITY_TRUE = "ACCOUNTABILITY_TRUE"
    ACCOUNTABILITY_FALSE = "ACCOUNTABILITY_FALSE"
    ACCOUNTABILITY_UNRESOLVED = "ACCOUNTABILITY_UNRESOLVED"
    PREDICTABILITY_GTE_AUTOMATION = "PREDICTABILITY_GTE_AUTOMATION"
    PREDICTABILITY_LT_AUTOMATION = "PREDICTABILITY_LT_AUTOMATION"
    PREDICTABILITY_UNRESOLVED = "PREDICTABILITY_UNRESOLVED"


RULE_DIRECTION_BY_CODE = {
    PreliminaryDecidingRuleCode.INSUFFICIENT_ACTIVITY_IDENTITY: ProvisionalDirection.INSUFFICIENT_BASIS,
    PreliminaryDecidingRuleCode.INSUFFICIENT_CHANGE_CASE: ProvisionalDirection.INSUFFICIENT_BASIS,
    PreliminaryDecidingRuleCode.LIKELY_NO_CHANGE: ProvisionalDirection.LIKELY_NO_CHANGE,
    PreliminaryDecidingRuleCode.LIKELY_PROCESS_IMPROVEMENT_FIRST: ProvisionalDirection.LIKELY_PROCESS_IMPROVEMENT_FIRST,
    PreliminaryDecidingRuleCode.INSUFFICIENT_READINESS: ProvisionalDirection.INSUFFICIENT_BASIS,
    PreliminaryDecidingRuleCode.INSUFFICIENT_CONVENTIONAL_FIT: ProvisionalDirection.INSUFFICIENT_BASIS,
    PreliminaryDecidingRuleCode.LIKELY_CONVENTIONAL_AUTOMATION: ProvisionalDirection.LIKELY_CONVENTIONAL_AUTOMATION,
    PreliminaryDecidingRuleCode.INSUFFICIENT_AI_FIT: ProvisionalDirection.INSUFFICIENT_BASIS,
    PreliminaryDecidingRuleCode.LIKELY_HUMAN_LED_LOW_AI_FIT: ProvisionalDirection.LIKELY_HUMAN_LED,
    PreliminaryDecidingRuleCode.INSUFFICIENT_AI_CAPABILITY: ProvisionalDirection.INSUFFICIENT_BASIS,
    PreliminaryDecidingRuleCode.LIKELY_HUMAN_LED_NO_CAPABILITY: ProvisionalDirection.LIKELY_HUMAN_LED,
    PreliminaryDecidingRuleCode.LIKELY_HUMAN_LED_SAFETY_VETO: ProvisionalDirection.LIKELY_HUMAN_LED,
    PreliminaryDecidingRuleCode.INSUFFICIENT_RESIDUAL_RISK: ProvisionalDirection.INSUFFICIENT_BASIS,
    PreliminaryDecidingRuleCode.POTENTIAL_AI_ASSISTED_CONSTRAINT: ProvisionalDirection.POTENTIAL_AI_ASSISTED_WORK,
    PreliminaryDecidingRuleCode.POTENTIAL_AI_ASSISTED_AUTONOMY_UNKNOWN: ProvisionalDirection.POTENTIAL_AI_ASSISTED_WORK,
    PreliminaryDecidingRuleCode.POTENTIAL_AI_AUTOMATION: ProvisionalDirection.POTENTIAL_AI_AUTOMATION,
}


_BASE_CHANGE = {
    PreliminaryInputName.ACTIVITY_IDENTITY,
    PreliminaryInputName.BUSINESS_VALUE,
}
_BASE_READY = {
    *_BASE_CHANGE,
    PreliminaryInputName.DATA_READINESS,
    PreliminaryInputName.IMPLEMENTATION_COMPLEXITY,
}
_BASE_CONVENTIONAL = {
    *_BASE_READY,
    PreliminaryInputName.CONVENTIONAL_SOLUTION_FIT,
}
_BASE_AI = {*_BASE_CONVENTIONAL, PreliminaryInputName.AI_CAPABILITY_FIT}
_AUTONOMY_INPUTS = {
    PreliminaryInputName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT,
    PreliminaryInputName.HUMAN_JUDGEMENT_REQUIREMENT,
    PreliminaryInputName.RISK_CONSEQUENCE,
    PreliminaryInputName.HUMAN_ACCOUNTABILITY_REQUIRED,
    PreliminaryInputName.PREDICTABILITY,
}


RULE_MATERIAL_MANIFESTS = {
    PreliminaryDecidingRuleCode.INSUFFICIENT_ACTIVITY_IDENTITY: (
        {PreliminaryInputName.ACTIVITY_IDENTITY},
        (),
        {PreliminaryInputName.ACTIVITY_IDENTITY},
    ),
    PreliminaryDecidingRuleCode.INSUFFICIENT_CHANGE_CASE: (
        _BASE_CHANGE,
        (),
        _BASE_CHANGE,
    ),
    PreliminaryDecidingRuleCode.LIKELY_NO_CHANGE: (
        _BASE_CHANGE,
        (),
        _BASE_CHANGE,
    ),
    PreliminaryDecidingRuleCode.LIKELY_PROCESS_IMPROVEMENT_FIRST: (
        _BASE_CHANGE,
        ({PreliminaryInputName.DATA_READINESS, PreliminaryInputName.IMPLEMENTATION_COMPLEXITY},),
        _BASE_READY,
    ),
    PreliminaryDecidingRuleCode.INSUFFICIENT_READINESS: (
        _BASE_READY,
        (),
        _BASE_READY,
    ),
    PreliminaryDecidingRuleCode.INSUFFICIENT_CONVENTIONAL_FIT: (
        _BASE_CONVENTIONAL,
        (),
        _BASE_CONVENTIONAL,
    ),
    PreliminaryDecidingRuleCode.LIKELY_CONVENTIONAL_AUTOMATION: (
        _BASE_CONVENTIONAL,
        (),
        _BASE_CONVENTIONAL,
    ),
    PreliminaryDecidingRuleCode.INSUFFICIENT_AI_FIT: (
        _BASE_AI,
        (),
        _BASE_AI,
    ),
    PreliminaryDecidingRuleCode.LIKELY_HUMAN_LED_LOW_AI_FIT: (
        _BASE_AI,
        (),
        _BASE_AI,
    ),
    PreliminaryDecidingRuleCode.INSUFFICIENT_AI_CAPABILITY: (
        _BASE_AI | set(CAPABILITY_INPUT_NAMES),
        (),
        _BASE_AI | set(CAPABILITY_INPUT_NAMES),
    ),
    PreliminaryDecidingRuleCode.LIKELY_HUMAN_LED_NO_CAPABILITY: (
        _BASE_AI | set(CAPABILITY_INPUT_NAMES),
        (),
        _BASE_AI | set(CAPABILITY_INPUT_NAMES),
    ),
}
for _code in (
    PreliminaryDecidingRuleCode.LIKELY_HUMAN_LED_SAFETY_VETO,
    PreliminaryDecidingRuleCode.INSUFFICIENT_RESIDUAL_RISK,
):
    RULE_MATERIAL_MANIFESTS[_code] = (
        _BASE_AI | {PreliminaryInputName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT},
        (set(CAPABILITY_INPUT_NAMES),),
        _BASE_AI
        | set(CAPABILITY_INPUT_NAMES)
        | {PreliminaryInputName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT},
    )
for _code in (
    PreliminaryDecidingRuleCode.POTENTIAL_AI_ASSISTED_CONSTRAINT,
    PreliminaryDecidingRuleCode.POTENTIAL_AI_ASSISTED_AUTONOMY_UNKNOWN,
):
    RULE_MATERIAL_MANIFESTS[_code] = (
        _BASE_AI | {PreliminaryInputName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT},
        (set(CAPABILITY_INPUT_NAMES),),
        _BASE_AI | set(CAPABILITY_INPUT_NAMES) | _AUTONOMY_INPUTS,
    )
RULE_MATERIAL_MANIFESTS[PreliminaryDecidingRuleCode.POTENTIAL_AI_AUTOMATION] = (
    _BASE_AI | _AUTONOMY_INPUTS,
    (set(CAPABILITY_INPUT_NAMES),),
    _BASE_AI | set(CAPABILITY_INPUT_NAMES) | _AUTONOMY_INPUTS,
)


INSUFFICIENT_RULE_CODES = {
    code
    for code, direction in RULE_DIRECTION_BY_CODE.items()
    if direction is ProvisionalDirection.INSUFFICIENT_BASIS
}


RULE_DECIDING_CLAUSES = {
    PreliminaryDecidingRuleCode.INSUFFICIENT_ACTIVITY_IDENTITY: {
        PreliminaryComparisonClause.ACTIVITY_UNRESOLVED
    },
    PreliminaryDecidingRuleCode.INSUFFICIENT_CHANGE_CASE: {
        PreliminaryComparisonClause.BUSINESS_UNRESOLVED
    },
    PreliminaryDecidingRuleCode.LIKELY_NO_CHANGE: {
        PreliminaryComparisonClause.BUSINESS_LT_MINIMUM
    },
    PreliminaryDecidingRuleCode.LIKELY_PROCESS_IMPROVEMENT_FIRST: {
        PreliminaryComparisonClause.DATA_LT_MINIMUM,
        PreliminaryComparisonClause.COMPLEXITY_GT_READY_MAX,
    },
    PreliminaryDecidingRuleCode.INSUFFICIENT_READINESS: {
        PreliminaryComparisonClause.DATA_UNRESOLVED,
        PreliminaryComparisonClause.COMPLEXITY_UNRESOLVED,
    },
    PreliminaryDecidingRuleCode.INSUFFICIENT_CONVENTIONAL_FIT: {
        PreliminaryComparisonClause.CONVENTIONAL_UNRESOLVED
    },
    PreliminaryDecidingRuleCode.LIKELY_CONVENTIONAL_AUTOMATION: {
        PreliminaryComparisonClause.CONVENTIONAL_GTE_CUTOFF
    },
    PreliminaryDecidingRuleCode.INSUFFICIENT_AI_FIT: {
        PreliminaryComparisonClause.AI_FIT_UNRESOLVED
    },
    PreliminaryDecidingRuleCode.LIKELY_HUMAN_LED_LOW_AI_FIT: {
        PreliminaryComparisonClause.AI_FIT_LT_MINIMUM
    },
    PreliminaryDecidingRuleCode.INSUFFICIENT_AI_CAPABILITY: {
        PreliminaryComparisonClause.CAPABILITY_UNRESOLVED
    },
    PreliminaryDecidingRuleCode.LIKELY_HUMAN_LED_NO_CAPABILITY: {
        PreliminaryComparisonClause.CAPABILITY_FALSE
    },
    PreliminaryDecidingRuleCode.LIKELY_HUMAN_LED_SAFETY_VETO: {
        PreliminaryComparisonClause.RESIDUAL_GTE_VETO
    },
    PreliminaryDecidingRuleCode.INSUFFICIENT_RESIDUAL_RISK: {
        PreliminaryComparisonClause.RESIDUAL_UNRESOLVED
    },
    PreliminaryDecidingRuleCode.POTENTIAL_AI_ASSISTED_CONSTRAINT: {
        PreliminaryComparisonClause.RESIDUAL_EQ_ASSISTANCE,
        PreliminaryComparisonClause.DATA_LT_AUTOMATION,
        PreliminaryComparisonClause.COMPLEXITY_GT_AUTOMATION_MAX,
        PreliminaryComparisonClause.JUDGEMENT_GTE_ASSISTANCE,
        PreliminaryComparisonClause.CONSEQUENCE_GTE_ASSISTANCE,
        PreliminaryComparisonClause.ACCOUNTABILITY_TRUE,
        PreliminaryComparisonClause.PREDICTABILITY_LT_AUTOMATION,
    },
    PreliminaryDecidingRuleCode.POTENTIAL_AI_ASSISTED_AUTONOMY_UNKNOWN: {
        PreliminaryComparisonClause.JUDGEMENT_UNRESOLVED,
        PreliminaryComparisonClause.CONSEQUENCE_UNRESOLVED,
        PreliminaryComparisonClause.ACCOUNTABILITY_UNRESOLVED,
        PreliminaryComparisonClause.PREDICTABILITY_UNRESOLVED,
    },
    PreliminaryDecidingRuleCode.POTENTIAL_AI_AUTOMATION: {
        PreliminaryComparisonClause.PREDICTABILITY_GTE_AUTOMATION
    },
}


CLAUSE_INPUTS = {
    PreliminaryComparisonClause.ACTIVITY_PRESENT: {PreliminaryInputName.ACTIVITY_IDENTITY},
    PreliminaryComparisonClause.ACTIVITY_UNRESOLVED: {PreliminaryInputName.ACTIVITY_IDENTITY},
    PreliminaryComparisonClause.BUSINESS_LT_MINIMUM: {PreliminaryInputName.BUSINESS_VALUE},
    PreliminaryComparisonClause.BUSINESS_GTE_MINIMUM: {PreliminaryInputName.BUSINESS_VALUE},
    PreliminaryComparisonClause.BUSINESS_UNRESOLVED: {PreliminaryInputName.BUSINESS_VALUE},
    PreliminaryComparisonClause.DATA_LT_MINIMUM: {PreliminaryInputName.DATA_READINESS},
    PreliminaryComparisonClause.DATA_GTE_MINIMUM: {PreliminaryInputName.DATA_READINESS},
    PreliminaryComparisonClause.DATA_GTE_AUTOMATION: {PreliminaryInputName.DATA_READINESS},
    PreliminaryComparisonClause.DATA_LT_AUTOMATION: {PreliminaryInputName.DATA_READINESS},
    PreliminaryComparisonClause.DATA_UNRESOLVED: {PreliminaryInputName.DATA_READINESS},
    PreliminaryComparisonClause.COMPLEXITY_GT_READY_MAX: {PreliminaryInputName.IMPLEMENTATION_COMPLEXITY},
    PreliminaryComparisonClause.COMPLEXITY_LTE_READY_MAX: {PreliminaryInputName.IMPLEMENTATION_COMPLEXITY},
    PreliminaryComparisonClause.COMPLEXITY_LTE_AUTOMATION_MAX: {PreliminaryInputName.IMPLEMENTATION_COMPLEXITY},
    PreliminaryComparisonClause.COMPLEXITY_GT_AUTOMATION_MAX: {PreliminaryInputName.IMPLEMENTATION_COMPLEXITY},
    PreliminaryComparisonClause.COMPLEXITY_UNRESOLVED: {PreliminaryInputName.IMPLEMENTATION_COMPLEXITY},
    PreliminaryComparisonClause.CONVENTIONAL_GTE_CUTOFF: {PreliminaryInputName.CONVENTIONAL_SOLUTION_FIT},
    PreliminaryComparisonClause.CONVENTIONAL_LT_CUTOFF: {PreliminaryInputName.CONVENTIONAL_SOLUTION_FIT},
    PreliminaryComparisonClause.CONVENTIONAL_UNRESOLVED: {PreliminaryInputName.CONVENTIONAL_SOLUTION_FIT},
    PreliminaryComparisonClause.AI_FIT_LT_MINIMUM: {PreliminaryInputName.AI_CAPABILITY_FIT},
    PreliminaryComparisonClause.AI_FIT_GTE_MINIMUM: {PreliminaryInputName.AI_CAPABILITY_FIT},
    PreliminaryComparisonClause.AI_FIT_UNRESOLVED: {PreliminaryInputName.AI_CAPABILITY_FIT},
    PreliminaryComparisonClause.CAPABILITY_TRUE: set(CAPABILITY_INPUT_NAMES),
    PreliminaryComparisonClause.CAPABILITY_FALSE: set(CAPABILITY_INPUT_NAMES),
    PreliminaryComparisonClause.CAPABILITY_UNRESOLVED: set(CAPABILITY_INPUT_NAMES),
    PreliminaryComparisonClause.RESIDUAL_GTE_VETO: {PreliminaryInputName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT},
    PreliminaryComparisonClause.RESIDUAL_LT_VETO: {PreliminaryInputName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT},
    PreliminaryComparisonClause.RESIDUAL_EQ_ASSISTANCE: {PreliminaryInputName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT},
    PreliminaryComparisonClause.RESIDUAL_LTE_AUTOMATION_MAX: {PreliminaryInputName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT},
    PreliminaryComparisonClause.RESIDUAL_UNRESOLVED: {PreliminaryInputName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT},
    PreliminaryComparisonClause.JUDGEMENT_GTE_ASSISTANCE: {PreliminaryInputName.HUMAN_JUDGEMENT_REQUIREMENT},
    PreliminaryComparisonClause.JUDGEMENT_LT_ASSISTANCE: {PreliminaryInputName.HUMAN_JUDGEMENT_REQUIREMENT},
    PreliminaryComparisonClause.JUDGEMENT_UNRESOLVED: {PreliminaryInputName.HUMAN_JUDGEMENT_REQUIREMENT},
    PreliminaryComparisonClause.CONSEQUENCE_GTE_ASSISTANCE: {PreliminaryInputName.RISK_CONSEQUENCE},
    PreliminaryComparisonClause.CONSEQUENCE_LT_ASSISTANCE: {PreliminaryInputName.RISK_CONSEQUENCE},
    PreliminaryComparisonClause.CONSEQUENCE_UNRESOLVED: {PreliminaryInputName.RISK_CONSEQUENCE},
    PreliminaryComparisonClause.ACCOUNTABILITY_TRUE: {PreliminaryInputName.HUMAN_ACCOUNTABILITY_REQUIRED},
    PreliminaryComparisonClause.ACCOUNTABILITY_FALSE: {PreliminaryInputName.HUMAN_ACCOUNTABILITY_REQUIRED},
    PreliminaryComparisonClause.ACCOUNTABILITY_UNRESOLVED: {PreliminaryInputName.HUMAN_ACCOUNTABILITY_REQUIRED},
    PreliminaryComparisonClause.PREDICTABILITY_GTE_AUTOMATION: {PreliminaryInputName.PREDICTABILITY},
    PreliminaryComparisonClause.PREDICTABILITY_LT_AUTOMATION: {PreliminaryInputName.PREDICTABILITY},
    PreliminaryComparisonClause.PREDICTABILITY_UNRESOLVED: {PreliminaryInputName.PREDICTABILITY},
}


class PreliminaryRuleSetReference(_FrozenContract):
    rule_set_id: Literal["preliminary-evaluator-rules.v0.1"]
    rule_set_version: Literal["0.1.0"]
    rule_set_status: Literal["PROVISIONAL CONTINUITY — NOT VALIDATED"]
    rule_set_fingerprint: Literal[
        "3db8a54561bcfe263a5483e5d4c49e203bfac40eafbc8bc778cf773ed6ad1790"
    ]


NormalizedPreliminaryValue = StrictInt | StrictBool | StrictStr | None


class PreliminaryRuleComparison(_FrozenContract):
    clause_code: PreliminaryComparisonClause
    operator: PreliminaryComparisonOperator
    threshold_value: NormalizedPreliminaryValue = None
    matched: Literal[True]


class PreliminaryDecisionInputTrace(_FrozenContract):
    input_name: PreliminaryInputName
    reviewed_field_path: str = Field(min_length=1)
    value_type: PreliminaryValueType
    normalized_value: NormalizedPreliminaryValue = None
    classification: PreliminaryEvidenceClassification
    evidence_item_ids: tuple[str, ...] = Field(min_length=1)
    material: bool
    material_stage: PreliminaryEvaluationStage | None = None
    comparison: PreliminaryRuleComparison | None = None

    @field_validator("reviewed_field_path")
    @classmethod
    def reject_blank_path(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Reviewed field path cannot be blank")
        return value

    @field_validator("evidence_item_ids")
    @classmethod
    def validate_evidence_item_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() for item in value):
            raise ValueError("Trace evidence item IDs cannot be blank")
        if len(value) != len(set(value)):
            raise ValueError("Trace evidence item IDs must be unique")
        return value

    @model_validator(mode="after")
    def validate_trace_semantics(self) -> "PreliminaryDecisionInputTrace":
        unresolved = self.classification in {
            PreliminaryEvidenceClassification.UNKNOWN,
            PreliminaryEvidenceClassification.CONFLICT,
        }
        if unresolved and self.normalized_value is not None:
            raise ValueError("Unknown or conflicted trace inputs cannot carry a value")
        if not unresolved and self.normalized_value is None:
            raise ValueError("Documented or inferred trace inputs require a value")
        if self.value_type is PreliminaryValueType.ORDINAL and self.normalized_value is not None:
            if isinstance(self.normalized_value, bool) or not isinstance(self.normalized_value, int):
                raise ValueError("Ordinal trace inputs require an integer value")
            if not 0 <= self.normalized_value <= 5:
                raise ValueError("Ordinal trace values must be between 0 and 5")
        if self.value_type is PreliminaryValueType.BOOLEAN and self.normalized_value is not None:
            if not isinstance(self.normalized_value, bool):
                raise ValueError("Boolean trace inputs require a boolean value")
        if self.value_type is PreliminaryValueType.TEXT and self.normalized_value is not None:
            if not isinstance(self.normalized_value, str) or not self.normalized_value.strip():
                raise ValueError("Text trace inputs require non-blank text")
        if self.material != (self.material_stage is not None and self.comparison is not None):
            raise ValueError(
                "Material trace inputs require a stage and comparison; "
                "non-material inputs cannot carry them"
            )
        if self.material and unresolved:
            expected_operator = (
                PreliminaryComparisonOperator.IS_CONFLICT
                if self.classification is PreliminaryEvidenceClassification.CONFLICT
                else PreliminaryComparisonOperator.IS_UNKNOWN
            )
            if self.comparison is None or self.comparison.operator is not expected_operator:
                raise ValueError(
                    "Material unknown and conflict inputs require their matching "
                    "unresolved comparison operator"
                )
        if (
            self.material
            and not unresolved
            and self.comparison is not None
            and self.comparison.operator
            in {
                PreliminaryComparisonOperator.IS_UNKNOWN,
                PreliminaryComparisonOperator.IS_CONFLICT,
            }
        ):
            raise ValueError(
                "Resolved material inputs cannot use an unresolved comparison"
            )
        if self.comparison is not None and not _comparison_matches(
            self.normalized_value, self.comparison
        ):
            raise ValueError("Trace comparison does not match its normalized value")
        return self


def _comparison_matches(
    value: NormalizedPreliminaryValue,
    comparison: PreliminaryRuleComparison,
) -> bool:
    operator = comparison.operator
    threshold = comparison.threshold_value
    if operator is PreliminaryComparisonOperator.PRESENT:
        return value is not None and threshold is None
    if operator is PreliminaryComparisonOperator.IS_UNKNOWN:
        return value is None and threshold is None
    if operator is PreliminaryComparisonOperator.IS_CONFLICT:
        return value is None and threshold is None
    if operator is PreliminaryComparisonOperator.IS_TRUE:
        return value is True and threshold is None
    if operator is PreliminaryComparisonOperator.IS_FALSE:
        return value is False and threshold is None
    if value is None or threshold is None:
        return False
    if isinstance(value, bool) or isinstance(threshold, bool):
        return operator is PreliminaryComparisonOperator.EQ and value == threshold
    if not isinstance(value, (int, str)) or not isinstance(threshold, type(value)):
        return False
    if operator is PreliminaryComparisonOperator.EQ:
        return value == threshold
    if not isinstance(value, int):
        return False
    if operator is PreliminaryComparisonOperator.LT:
        return value < threshold
    if operator is PreliminaryComparisonOperator.LTE:
        return value <= threshold
    if operator is PreliminaryComparisonOperator.GTE:
        return value >= threshold
    if operator is PreliminaryComparisonOperator.GT:
        return value > threshold
    return False


class JourneySelection(_FrozenContract):
    schema_version: Literal["journey-selection.v0.1"]
    journey: AssessmentJourney


class EvidenceCoverageConfidence(_FrozenContract):
    """A coverage label, never a statistical probability or outcome likelihood."""

    level: PreliminaryConfidence
    meaning: Literal["EVIDENCE_COVERAGE_ONLY"] = "EVIDENCE_COVERAGE_ONLY"
    basis: str = Field(min_length=1)

    @field_validator("basis")
    @classmethod
    def reject_blank_basis(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Confidence basis cannot be blank")
        return value


class DocumentedFact(_FrozenContract):
    """A fact supported by an exact excerpt from an identified document."""

    evidence_class: Literal["DOCUMENTED_FACT"] = "DOCUMENTED_FACT"
    information_origin: Literal["DOCUMENT_SUPPORTED"] = "DOCUMENT_SUPPORTED"
    fact_id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    source_document_id: str = Field(pattern=r"^doc-[0-9a-f]{64}$")
    exact_excerpt: str = Field(min_length=1)
    source_locator: str = Field(min_length=1)

    @field_validator("fact_id", "statement", "exact_excerpt", "source_locator")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Documented fact text cannot be blank")
        return value


class ReasonableInference(_FrozenContract):
    """A provisional inference with explicit documentary lineage."""

    evidence_class: Literal["REASONABLE_INFERENCE"] = "REASONABLE_INFERENCE"
    information_origin: Literal["INFERRED_FROM_DOCUMENTED_FACTS"] = (
        "INFERRED_FROM_DOCUMENTED_FACTS"
    )
    inference_id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    derived_from_fact_ids: tuple[str, ...] = Field(min_length=1)
    rationale: str = Field(min_length=1)
    confidence: EvidenceCoverageConfidence

    @field_validator("inference_id", "statement", "rationale", "derived_from_fact_ids")
    @classmethod
    def reject_blank_text_and_fact_ids(cls, value):
        if isinstance(value, str):
            if not value.strip():
                raise ValueError("Inference text cannot be blank")
            return value
        if any(not item.strip() for item in value):
            raise ValueError("Inference fact references cannot be blank")
        if len(value) != len(set(value)):
            raise ValueError("Inference fact references must be unique")
        return value


class PreliminaryUnknown(_FrozenContract):
    """An unresolved question without an imputed value or supporting evidence."""

    evidence_class: Literal["UNKNOWN"] = "UNKNOWN"
    information_origin: Literal["UNKNOWN"] = "UNKNOWN"
    unknown_id: str = Field(min_length=1)
    unresolved_question: str = Field(min_length=1)
    evidence_needed: str | None = Field(default=None, min_length=1)
    owner_needed: str | None = Field(default=None, min_length=1)

    @field_validator(
        "unknown_id", "unresolved_question", "evidence_needed", "owner_needed"
    )
    @classmethod
    def reject_blank_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Unknown-resolution text cannot be blank")
        return value

    @model_validator(mode="after")
    def require_resolution_need(self) -> "PreliminaryUnknown":
        if self.evidence_needed is None and self.owner_needed is None:
            raise ValueError(
                "An unknown requires evidence or an owner to resolve it"
            )
        return self


PreliminaryEvidence = Annotated[
    DocumentedFact | ReasonableInference | PreliminaryUnknown,
    Field(discriminator="evidence_class"),
]


class NextEvidenceToCollect(_FrozenContract):
    request_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    resolves_unknown_ids: tuple[str, ...] = Field(min_length=1)
    suggested_owner: str | None = Field(default=None, min_length=1)

    @field_validator("request_id", "description", "suggested_owner")
    @classmethod
    def reject_blank_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Next-evidence text cannot be blank")
        return value

    @field_validator("resolves_unknown_ids")
    @classmethod
    def validate_unknown_references(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() for item in value):
            raise ValueError("Unknown references cannot be blank")
        if len(value) != len(set(value)):
            raise ValueError("Unknown references must be unique")
        return value


class PreliminaryActivityResult(_FrozenContract):
    step_id: str = Field(min_length=1)
    activity: str = Field(min_length=1)
    provisional_direction: ProvisionalDirection
    deciding_rule_code: PreliminaryDecidingRuleCode
    confidence: EvidenceCoverageConfidence
    rationale: str = Field(min_length=1)
    documented_facts: tuple[DocumentedFact, ...] = ()
    reasonable_inferences: tuple[ReasonableInference, ...] = ()
    unknowns: tuple[PreliminaryUnknown, ...] = ()
    next_evidence_to_collect: tuple[NextEvidenceToCollect, ...] = ()
    decision_input_trace: tuple[PreliminaryDecisionInputTrace, ...] = Field(
        min_length=1
    )

    @field_validator("step_id", "activity", "rationale")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Activity-result text cannot be blank")
        return value

    @model_validator(mode="after")
    def validate_evidence_semantics(self) -> "PreliminaryActivityResult":
        if (
            self.provisional_direction is ProvisionalDirection.INSUFFICIENT_BASIS
            and self.confidence.level is not PreliminaryConfidence.LOW
        ):
            raise ValueError(
                "Insufficient basis to suggest a direction requires Low confidence"
            )
        expected_direction = RULE_DIRECTION_BY_CODE[self.deciding_rule_code]
        if self.provisional_direction is not expected_direction:
            raise ValueError(
                "Deciding rule code does not produce the stated provisional direction"
            )

        fact_ids = [item.fact_id for item in self.documented_facts]
        inference_ids = [item.inference_id for item in self.reasonable_inferences]
        unknown_ids = [item.unknown_id for item in self.unknowns]
        evidence_ids = [*fact_ids, *inference_ids, *unknown_ids]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("Preliminary evidence identifiers must be unique")
        if not evidence_ids:
            raise ValueError(
                "An activity result requires a documented fact, inference, or unknown"
            )

        known_fact_ids = set(fact_ids)
        for inference in self.reasonable_inferences:
            missing = set(inference.derived_from_fact_ids) - known_fact_ids
            if missing:
                raise ValueError(
                    "Inference references unknown documented facts: "
                    f"{sorted(missing)}"
                )

        known_unknown_ids = set(unknown_ids)
        request_ids = [item.request_id for item in self.next_evidence_to_collect]
        if len(request_ids) != len(set(request_ids)):
            raise ValueError("Next-evidence request identifiers must be unique")
        for request in self.next_evidence_to_collect:
            missing = set(request.resolves_unknown_ids) - known_unknown_ids
            if missing:
                raise ValueError(
                    "Next evidence references unknown unresolved questions: "
                    f"{sorted(missing)}"
                )

        trace_names = [item.input_name for item in self.decision_input_trace]
        if len(trace_names) != len(set(trace_names)):
            raise ValueError("Decision-input trace names must be unique")
        expected_order = sorted(
            trace_names, key=lambda name: PRELIMINARY_INPUT_ORDER.index(name)
        )
        if trace_names != expected_order:
            raise ValueError("Decision-input trace ordering must be deterministic")

        facts = {item.fact_id: item for item in self.documented_facts}
        inferences = {
            item.inference_id: item for item in self.reasonable_inferences
        }
        unknowns = {item.unknown_id: item for item in self.unknowns}
        evidence_by_classification = {
            PreliminaryEvidenceClassification.DOCUMENTED: facts,
            PreliminaryEvidenceClassification.REASONABLE_INFERENCE: inferences,
            PreliminaryEvidenceClassification.UNKNOWN: unknowns,
            PreliminaryEvidenceClassification.CONFLICT: unknowns,
        }
        for trace_item in self.decision_input_trace:
            valid_items = evidence_by_classification[trace_item.classification]
            missing = set(trace_item.evidence_item_ids) - set(valid_items)
            if missing:
                raise ValueError(
                    "Trace evidence references do not resolve to evidence of the "
                    f"declared classification: {sorted(missing)}"
                )
            if (
                trace_item.comparison is not None
                and trace_item.input_name
                not in CLAUSE_INPUTS[trace_item.comparison.clause_code]
            ):
                raise ValueError(
                    "Trace comparison clause does not apply to its input name"
                )

        material_items = {
            item.input_name: item
            for item in self.decision_input_trace
            if item.material
        }
        material_names = set(material_items)
        required_all, required_any_groups, allowed = RULE_MATERIAL_MANIFESTS[
            self.deciding_rule_code
        ]
        if not required_all <= material_names:
            raise ValueError(
                "Decision-input trace omits inputs required by the deciding rule"
            )
        if any(not (group & material_names) for group in required_any_groups):
            raise ValueError(
                "Decision-input trace omits a required material input group"
            )
        if not material_names <= allowed:
            raise ValueError(
                "Decision-input trace names inputs outside the deciding-rule manifest"
            )
        deciding_clauses = RULE_DECIDING_CLAUSES[self.deciding_rule_code]
        if not any(
            item.comparison is not None
            and item.comparison.clause_code in deciding_clauses
            for item in material_items.values()
        ):
            raise ValueError(
                "Decision-input trace does not prove the deciding-rule comparison"
            )

        material_unresolved = {
            item.classification
            for item in material_items.values()
            if item.classification
            in {
                PreliminaryEvidenceClassification.UNKNOWN,
                PreliminaryEvidenceClassification.CONFLICT,
            }
        }
        if material_unresolved and self.deciding_rule_code not in (
            INSUFFICIENT_RULE_CODES
            | {
                PreliminaryDecidingRuleCode.POTENTIAL_AI_ASSISTED_AUTONOMY_UNKNOWN
            }
        ):
            raise ValueError(
                "Resolved directions cannot depend on unknown or conflicted inputs"
            )

        material_inferences = sum(
            item.classification
            is PreliminaryEvidenceClassification.REASONABLE_INFERENCE
            for item in material_items.values()
        )
        if (
            self.deciding_rule_code in INSUFFICIENT_RULE_CODES
            or self.deciding_rule_code
            is PreliminaryDecidingRuleCode.POTENTIAL_AI_ASSISTED_AUTONOMY_UNKNOWN
            or material_inferences >= 2
        ):
            expected_confidence = PreliminaryConfidence.LOW
        elif material_inferences == 1:
            expected_confidence = PreliminaryConfidence.MEDIUM
        else:
            expected_confidence = PreliminaryConfidence.HIGH
        if self.confidence.level is not expected_confidence:
            raise ValueError(
                "Activity confidence does not match path-material evidence coverage"
            )
        return self


class PreliminaryAssessmentLineage(_FrozenContract):
    """Exact link to the approved current-state review and its projection."""

    source_document_id: str = Field(pattern=r"^doc-[0-9a-f]{64}$")
    extraction_run_id: str = Field(min_length=1)
    review_id: str = Field(min_length=1)
    approval_event_id: str = Field(min_length=1)
    approval_statement: Literal["APPROVE CURRENT-STATE PROCESS"]
    approved_at: datetime
    validated_process_id: str = Field(min_length=1)
    validated_process_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator(
        "extraction_run_id", "review_id", "approval_event_id", "validated_process_id"
    )
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Lineage identifiers cannot be blank")
        return value


class PreliminaryAssessment(_FrozenContract):
    """Process-level envelope for a persistence-free exploratory result."""

    schema_version: Literal["preliminary-assessment.v0.1"]
    assessment_kind: Literal["PRELIMINARY_ASSESSMENT"]
    preliminary_assessment_id: str = Field(min_length=1)
    created_at: datetime
    rule_set: PreliminaryRuleSetReference
    journey_selection: JourneySelection
    lineage: PreliminaryAssessmentLineage
    process_id: str = Field(min_length=1)
    process_name: str = Field(min_length=1)
    confidence: EvidenceCoverageConfidence
    activity_results: tuple[PreliminaryActivityResult, ...] = Field(min_length=1)
    disclaimer: Literal[
        "Provisional exploration only. This Preliminary Assessment is not an "
        "official four-gate outcome, Decision Package, organisational assessment, "
        "or approval to implement."
    ]

    @field_validator("preliminary_assessment_id", "process_id", "process_name")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Preliminary Assessment identity cannot be blank")
        return value

    @model_validator(mode="after")
    def validate_exploration_lineage(self) -> "PreliminaryAssessment":
        if self.journey_selection.journey is not AssessmentJourney.EXPLORE_PROCESS:
            raise ValueError(
                "A Preliminary Assessment requires the EXPLORE_PROCESS journey"
            )
        if self.process_id != self.lineage.validated_process_id:
            raise ValueError(
                "Preliminary Assessment process ID must match approved lineage"
            )
        for activity_result in self.activity_results:
            for fact in activity_result.documented_facts:
                if fact.source_document_id != self.lineage.source_document_id:
                    raise ValueError(
                        "Every documented fact must reference the approved "
                        "current-state process document"
                    )
        step_ids = [item.step_id for item in self.activity_results]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("Preliminary activity result step IDs must be unique")
        return self

    def canonical_json_bytes(self) -> bytes:
        """Return deterministic semantic JSON for repeatability checks."""

        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

    def substantive_json_bytes(self) -> bytes:
        """Return deterministic decision content excluding run metadata."""

        return json.dumps(
            self.model_dump(
                mode="json",
                exclude={"preliminary_assessment_id", "created_at"},
            ),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
