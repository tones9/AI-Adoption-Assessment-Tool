"""Structured output models for explainable deterministic assessments."""

from pydantic import BaseModel, ConfigDict, Field

from ai_adoption_engine.models.enums import (
    Capability,
    CriterionName,
    GateName,
    GateStatus,
    PriorityBand,
    RecommendationMode,
)
from ai_adoption_engine.models.evidence import EvidenceReference


class GateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gate: GateName
    status: GateStatus
    rationale: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)


class ScoreComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion: CriterionName
    raw_value: int
    favourable_value: int
    weight: float
    contribution: float


class PriorityScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float = Field(ge=0, le=100)
    band: PriorityBand
    components: list[ScoreComponent]


class StepAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str
    activity: str
    recommendation_mode: RecommendationMode
    capabilities: list[Capability]
    gate_results: list[GateResult]
    priority: PriorityScore | None
    reasoning: list[str]
    evidence: list[EvidenceReference]


class ProcessAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    process_id: str
    process_name: str
    policy_id: str
    policy_version: str
    policy_status: str
    step_assessments: list[StepAssessment]

