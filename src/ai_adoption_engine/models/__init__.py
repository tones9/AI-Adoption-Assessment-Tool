"""Typed domain contracts for the assessment engine."""

from ai_adoption_engine.models.assessment import ProcessAssessment, StepAssessment
from ai_adoption_engine.models.candidate_process import (
    CandidateBusinessProcess,
    CandidateProcessStep,
)
from ai_adoption_engine.models.document import IngestedDocument, IngestionResult, TextBlock
from ai_adoption_engine.models.enums import Capability, RecommendationMode
from ai_adoption_engine.models.evidence import (
    BooleanCriterionInput,
    CriterionInput,
    EvidenceReference,
)
from ai_adoption_engine.models.process import (
    BusinessProcess,
    CapabilitySignalInput,
    CapabilitySignals,
    ProcessStep,
)

__all__ = [
    "BusinessProcess",
    "BooleanCriterionInput",
    "Capability",
    "CapabilitySignalInput",
    "CapabilitySignals",
    "CandidateBusinessProcess",
    "CandidateProcessStep",
    "CriterionInput",
    "EvidenceReference",
    "IngestedDocument",
    "IngestionResult",
    "ProcessAssessment",
    "ProcessStep",
    "RecommendationMode",
    "StepAssessment",
    "TextBlock",
]
