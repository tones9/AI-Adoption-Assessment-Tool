"""Load and validate a replaceable, versioned decision policy."""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_adoption_engine.models.enums import CriterionName, RecommendationMode

PROVISIONAL_STATUS = "PROVISIONAL — NOT YET ACADEMICALLY VALIDATED"


class CriterionScale(BaseModel):
    model_config = ConfigDict(extra="forbid")

    direction: Literal["favourable", "unfavourable"]
    meaning: str = Field(min_length=1)


class ScalePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minimum: int
    maximum: int
    unknown_representation: str = Field(min_length=1)
    criteria: dict[CriterionName, CriterionScale]


class EvidencePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minimum_inferred_confidence: float = Field(ge=0, le=1)
    require_evidence_reference: bool
    required_criteria: list[CriterionName]


class GateThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minimum_ai_capability_fit: int = Field(ge=0, le=5)
    minimum_business_value: int = Field(ge=0, le=5)
    minimum_data_readiness: int = Field(ge=0, le=5)
    conventional_solution_fit_cutoff: int = Field(ge=0, le=5)
    unacceptable_residual_risk: int = Field(ge=0, le=5)
    augment_human_judgement: int = Field(ge=0, le=5)
    augment_risk_consequence: int = Field(ge=0, le=5)
    augment_residual_risk: int = Field(ge=0, le=5)
    automate_minimum_predictability: int = Field(ge=0, le=5)
    automate_minimum_data_readiness: int = Field(ge=0, le=5)
    automate_maximum_human_judgement: int = Field(ge=0, le=5)
    automate_maximum_risk_consequence: int = Field(ge=0, le=5)
    automate_maximum_residual_risk: int = Field(ge=0, le=5)


class ScoringCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weight: float = Field(gt=0, le=1)
    direction: Literal["favourable", "unfavourable"]


class ScoreBands(BaseModel):
    model_config = ConfigDict(extra="forbid")

    high_minimum: float = Field(ge=0, le=100)
    medium_minimum: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validate_order(self) -> "ScoreBands":
        if self.high_minimum <= self.medium_minimum:
            raise ValueError("The high band must start above the medium band")
        return self


class ScoringPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eligible_recommendations: list[RecommendationMode]
    criteria: dict[CriterionName, ScoringCriterion]
    bands: ScoreBands

    @model_validator(mode="after")
    def validate_weights(self) -> "ScoringPolicy":
        total = sum(item.weight for item in self.criteria.values())
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"Scoring weights must sum to 1.0, got {total}")
        return self


class DecisionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    status: str
    description: str = Field(min_length=1)
    scale: ScalePolicy
    evidence: EvidencePolicy
    gates: GateThresholds
    scoring: ScoringPolicy

    @model_validator(mode="after")
    def validate_policy_contract(self) -> "DecisionPolicy":
        if self.status != PROVISIONAL_STATUS:
            raise ValueError(f"Phase 1 policy status must be: {PROVISIONAL_STATUS}")
        if self.scale.minimum != 0 or self.scale.maximum != 5:
            raise ValueError("Phase 1 policy must use the approved 0-5 scale")
        missing_scales = set(CriterionName) - set(self.scale.criteria)
        if missing_scales:
            raise ValueError(f"Missing scale definitions: {sorted(missing_scales)}")
        if set(self.evidence.required_criteria) != set(CriterionName):
            raise ValueError("Evidence policy must cover every Phase 1 criterion")
        expected_eligible = {
            RecommendationMode.AUTOMATE,
            RecommendationMode.AUGMENT,
        }
        if set(self.scoring.eligible_recommendations) != expected_eligible:
            raise ValueError("Only AUTOMATE and AUGMENT may receive priority scores")
        return self


def load_policy(path: str | Path) -> DecisionPolicy:
    policy_path = Path(path)
    with policy_path.open(encoding="utf-8") as handle:
        return DecisionPolicy.model_validate(json.load(handle))

