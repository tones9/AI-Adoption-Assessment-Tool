"""Shared enums used by input models, policy, and assessment output."""

from enum import StrEnum


class RecommendationMode(StrEnum):
    AUTOMATE = "AUTOMATE"
    AUGMENT = "AUGMENT"
    INVESTIGATE_FURTHER = "INVESTIGATE_FURTHER"
    DO_NOT_RECOMMEND = "DO_NOT_RECOMMEND"


class Capability(StrEnum):
    DOCUMENT_INFORMATION_EXTRACTION = "DOCUMENT_INFORMATION_EXTRACTION"
    CLASSIFICATION = "CLASSIFICATION"
    PREDICTION_FORECASTING = "PREDICTION_FORECASTING"
    ANOMALY_PATTERN_DETECTION = "ANOMALY_PATTERN_DETECTION"
    GENERATIVE_AI = "GENERATIVE_AI"
    KNOWLEDGE_RETRIEVAL = "KNOWLEDGE_RETRIEVAL"
    RECOMMENDATION = "RECOMMENDATION"
    DECISION_SUPPORT = "DECISION_SUPPORT"
    COMPUTER_VISION = "COMPUTER_VISION"
    WORKFLOW_AUTOMATION = "WORKFLOW_AUTOMATION"


class KnowledgeState(StrEnum):
    KNOWN = "known"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


class UncertaintyStatus(StrEnum):
    CERTAIN = "certain"
    UNCERTAIN = "uncertain"
    UNKNOWN = "unknown"


class CriterionName(StrEnum):
    REPETITION = "repetition"
    PREDICTABILITY = "predictability"
    DATA_READINESS = "data_readiness"
    AI_CAPABILITY_FIT = "ai_capability_fit"
    HUMAN_JUDGEMENT_REQUIREMENT = "human_judgement_requirement"
    BUSINESS_VALUE = "business_value"
    RISK_CONSEQUENCE = "risk_consequence"
    RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT = "residual_risk_with_human_oversight"
    IMPLEMENTATION_COMPLEXITY = "implementation_complexity"
    CONVENTIONAL_SOLUTION_FIT = "conventional_solution_fit"


class GateName(StrEnum):
    EVIDENCE_SUFFICIENCY = "evidence_sufficiency"
    TECHNICAL_FIT = "technical_fit"
    BUSINESS_VALUE = "business_value"
    RISK_AND_AUTONOMY = "risk_and_autonomy"


class GateStatus(StrEnum):
    PASSED = "passed"
    PASSED_WITH_CONSTRAINTS = "passed_with_constraints"
    FAILED = "failed"
    NOT_EVALUATED = "not_evaluated"


class PriorityBand(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

