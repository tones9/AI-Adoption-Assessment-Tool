"""Strict loader for the explicitly selected four-gate successor policy."""

import json
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_adoption_engine.models.enums import CriterionName
from ai_adoption_engine.models.four_gate_assessment import FourGateName, OutcomeCode

PROVISIONAL_STATUS = "PROVISIONAL — NOT YET ACADEMICALLY VALIDATED"


class FourGateCriterionScale(BaseModel):
    model_config = ConfigDict(extra="forbid")

    direction: Literal["favourable", "unfavourable"]
    meaning: str = Field(min_length=1)


class FourGateScalePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minimum: int
    maximum: int
    unknown_representation: str = Field(min_length=1)
    criteria: dict[CriterionName, FourGateCriterionScale]


class FourGateEvidencePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minimum_inferred_confidence: float = Field(ge=0, le=1)
    require_step_evidence_reference: bool
    require_material_criterion_evidence_reference: bool
    require_material_capability_signal_evidence_reference: bool
    material_by_gate: dict[FourGateName, list[CriterionName]]
    conditional_by_gate: dict[FourGateName, list[CriterionName]]
    context_by_gate: dict[FourGateName, list[CriterionName]]

    @model_validator(mode="after")
    def validate_gate_coverage(self) -> Self:
        expected = set(FourGateName)
        for field_name in (
            "material_by_gate",
            "conditional_by_gate",
            "context_by_gate",
        ):
            if set(getattr(self, field_name)) != expected:
                raise ValueError(f"{field_name} must define all four successor gates")
        return self


class FourGateThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minimum_business_value: int = Field(ge=0, le=5)
    minimum_data_readiness: int = Field(ge=0, le=5)
    maximum_implementation_complexity_for_readiness: int = Field(ge=0, le=5)
    conventional_solution_fit_cutoff: int = Field(ge=0, le=5)
    minimum_ai_capability_fit: int = Field(ge=0, le=5)
    unacceptable_residual_risk: int = Field(ge=0, le=5)
    augment_human_judgement: int = Field(ge=0, le=5)
    augment_risk_consequence: int = Field(ge=0, le=5)
    augment_residual_risk: int = Field(ge=0, le=5)
    automate_minimum_predictability: int = Field(ge=0, le=5)
    automate_minimum_data_readiness: int = Field(ge=0, le=5)
    automate_maximum_human_judgement: int = Field(ge=0, le=5)
    automate_maximum_risk_consequence: int = Field(ge=0, le=5)
    automate_maximum_residual_risk: int = Field(ge=0, le=5)

    @model_validator(mode="after")
    def validate_threshold_order(self) -> Self:
        if self.augment_human_judgement <= self.automate_maximum_human_judgement:
            raise ValueError("Human-judgement assistance threshold must exceed automation max")
        if self.augment_risk_consequence <= self.automate_maximum_risk_consequence:
            raise ValueError("Risk assistance threshold must exceed automation max")
        if self.augment_residual_risk <= self.automate_maximum_residual_risk:
            raise ValueError("Residual-risk assistance threshold must exceed automation max")
        if self.unacceptable_residual_risk <= self.augment_residual_risk:
            raise ValueError("Residual-risk veto must exceed its assistance threshold")
        return self


class FourGateScoringCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weight: float = Field(gt=0, le=1)
    direction: Literal["favourable", "unfavourable"]


class FourGateScoreBands(BaseModel):
    model_config = ConfigDict(extra="forbid")

    high_minimum: float = Field(ge=0, le=100)
    medium_minimum: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if self.high_minimum <= self.medium_minimum:
            raise ValueError("The high band must start above the medium band")
        return self


class FourGateScoringPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eligible_outcomes: list[OutcomeCode]
    criteria: dict[CriterionName, FourGateScoringCriterion]
    bands: FourGateScoreBands

    @model_validator(mode="after")
    def validate_scoring_contract(self) -> Self:
        total = sum(item.weight for item in self.criteria.values())
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"Scoring weights must sum to 1.0, got {total}")
        expected = {OutcomeCode.AI_AUTOMATION, OutcomeCode.AI_ASSISTED_WORK}
        if set(self.eligible_outcomes) != expected:
            raise ValueError("Only final AI automation and assisted outcomes are scoreable")
        return self


class FourGateDecisionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_id: Literal["decision_policy.v0.3"]
    version: Literal["0.3.0"]
    status: str
    description: str = Field(min_length=1)
    framework_id: Literal["four-gate-framework.v0.1"]
    framework_version: Literal["0.1"]
    decision_contract_version: Literal["phase1-v0.4"]
    scale: FourGateScalePolicy
    evidence: FourGateEvidencePolicy
    gates: FourGateThresholds
    scoring: FourGateScoringPolicy

    @model_validator(mode="after")
    def validate_policy_contract(self) -> Self:
        if self.status != PROVISIONAL_STATUS:
            raise ValueError(f"Successor policy status must be: {PROVISIONAL_STATUS}")
        if self.scale.minimum != 0 or self.scale.maximum != 5:
            raise ValueError("Successor policy must use the approved 0-5 scale")
        if set(self.scale.criteria) != set(CriterionName):
            raise ValueError("Scale must define exactly the ten approved criteria")

        expected_material = {
            FourGateName.SHOULD_WE_CHANGE: [CriterionName.BUSINESS_VALUE],
            FourGateName.IS_IT_READY: [
                CriterionName.DATA_READINESS,
                CriterionName.IMPLEMENTATION_COMPLEXITY,
            ],
            FourGateName.BEST_INTERVENTION: [
                CriterionName.CONVENTIONAL_SOLUTION_FIT
            ],
            FourGateName.SAFE_AUTONOMY: [
                CriterionName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT
            ],
        }
        if self.evidence.material_by_gate != expected_material:
            raise ValueError("Unconditional materiality must match the approved contract")

        expected_context = {
            FourGateName.SHOULD_WE_CHANGE: [CriterionName.REPETITION],
            FourGateName.IS_IT_READY: [
                CriterionName.REPETITION,
                CriterionName.PREDICTABILITY,
                CriterionName.AI_CAPABILITY_FIT,
            ],
            FourGateName.BEST_INTERVENTION: [],
            FourGateName.SAFE_AUTONOMY: [],
        }
        if self.evidence.context_by_gate != expected_context:
            raise ValueError("Context materiality must match the approved contract")

        expected_conditional = {
            FourGateName.SHOULD_WE_CHANGE: [],
            FourGateName.IS_IT_READY: [],
            FourGateName.BEST_INTERVENTION: [CriterionName.AI_CAPABILITY_FIT],
            FourGateName.SAFE_AUTONOMY: [
                CriterionName.HUMAN_JUDGEMENT_REQUIREMENT,
                CriterionName.RISK_CONSEQUENCE,
                CriterionName.PREDICTABILITY,
            ],
        }
        if self.evidence.conditional_by_gate != expected_conditional:
            raise ValueError("Conditional materiality must match the approved contract")
        return self


def load_four_gate_policy(path: str | Path) -> FourGateDecisionPolicy:
    """Load only the exact v0.3 successor contract; unknown versions fail closed."""

    policy_path = Path(path)
    with policy_path.open(encoding="utf-8") as handle:
        return FourGateDecisionPolicy.model_validate(json.load(handle))
