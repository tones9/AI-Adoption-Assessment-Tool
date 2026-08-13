"""Structured output models for explainable deterministic assessments."""

from pydantic import BaseModel, ConfigDict, Field

from ai_adoption_engine.models.enums import (
    Capability,
    CriterionName,
    GateName,
    GateStatus,
    KnowledgeState,
    PriorityBand,
    PriorityStatus,
    RecommendationMode,
)
from ai_adoption_engine.models.evidence import EvidenceReference


class GateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gate: GateName
    status: GateStatus
    rationale: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    material_criteria: list[CriterionName] = Field(default_factory=list)
    accountability_material: bool = False


class CriterionAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion: CriterionName
    value: int | None
    knowledge_state: KnowledgeState
    rationale: str
    evidence_ids: list[str]
    confidence: float | None
    material_to_recommendation: bool
    material_to_priority: bool
    material_at_gates: list[GateName]


class AccountabilityAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: bool | None
    knowledge_state: KnowledgeState
    rationale: str
    evidence_ids: list[str]
    confidence: float | None
    material_to_recommendation: bool
    material_at_gates: list[GateName]


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
    criteria: list[CriterionAssessment]
    human_accountability: AccountabilityAssessment
    gate_results: list[GateResult]
    priority: PriorityScore | None
    priority_status: PriorityStatus
    priority_missing_criteria: list[CriterionName] = Field(default_factory=list)
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
