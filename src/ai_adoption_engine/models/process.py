"""Current-state business-process input models."""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_adoption_engine.models.enums import CriterionName
from ai_adoption_engine.models.evidence import (
    BooleanCriterionInput,
    CriterionInput,
    EvidenceReference,
)


class CapabilitySignals(BaseModel):
    """Explicit Phase 1 task signals consumed by the deterministic mapper."""

    model_config = ConfigDict(extra="forbid")

    reads_unstructured_documents: bool = False
    categorises_items: bool = False
    predicts_future_outcomes: bool = False
    detects_anomalies_or_patterns: bool = False
    creates_new_content: bool = False
    searches_reference_knowledge: bool = False
    ranks_or_suggests_options: bool = False
    supports_complex_decisions: bool = False
    interprets_images_or_video: bool = False
    routes_or_orchestrates_work: bool = False


class TaskCharacteristics(BaseModel):
    """Hand-authored characteristics; Phase 1 performs no LLM inference."""

    model_config = ConfigDict(extra="forbid")

    repetition: CriterionInput
    predictability: CriterionInput
    data_readiness: CriterionInput
    ai_capability_fit: CriterionInput
    human_judgement_requirement: CriterionInput
    business_value: CriterionInput
    risk_consequence: CriterionInput
    residual_risk_with_human_oversight: CriterionInput
    implementation_complexity: CriterionInput
    conventional_solution_fit: CriterionInput
    human_accountability_required: BooleanCriterionInput
    capability_signals: CapabilitySignals = Field(default_factory=CapabilitySignals)

    def criterion(self, name: CriterionName | str) -> CriterionInput:
        key = CriterionName(name).value
        return getattr(self, key)


class ProcessStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    activity: str = Field(min_length=1)
    description: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    responsible_role: str | None = None
    systems: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    exceptions: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    characteristics: TaskCharacteristics


class BusinessProcess(BaseModel):
    model_config = ConfigDict(extra="forbid")

    process_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    business_objective: str = Field(min_length=1)
    organisation: str | None = None
    evidence: list[EvidenceReference]
    steps: list[ProcessStep] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_references_and_order(self) -> "BusinessProcess":
        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("Evidence IDs must be unique")

        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("Step IDs must be unique")
        sequences = [step.sequence for step in self.steps]
        if len(sequences) != len(set(sequences)):
            raise ValueError("Step sequence numbers must be unique")

        known_evidence = set(evidence_ids)
        known_steps = set(step_ids)
        for step in self.steps:
            referenced_evidence = set(step.evidence_ids)
            for criterion_name in CriterionName:
                referenced_evidence.update(
                    step.characteristics.criterion(criterion_name).evidence_ids
                )
            referenced_evidence.update(
                step.characteristics.human_accountability_required.evidence_ids
            )
            missing_evidence = referenced_evidence - known_evidence
            if missing_evidence:
                raise ValueError(
                    f"Step {step.step_id} references unknown evidence IDs: "
                    f"{sorted(missing_evidence)}"
                )
            missing_dependencies = set(step.dependencies) - known_steps
            if missing_dependencies:
                raise ValueError(
                    f"Step {step.step_id} references unknown dependencies: "
                    f"{sorted(missing_dependencies)}"
                )
            if step.step_id in step.dependencies:
                raise ValueError(f"Step {step.step_id} cannot depend on itself")

        self.steps.sort(key=lambda step: step.sequence)
        return self
