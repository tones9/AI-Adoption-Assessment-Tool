"""Current-state business-process input models."""

from collections.abc import Iterator

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_adoption_engine.models.enums import CriterionName, KnowledgeState
from ai_adoption_engine.models.evidence import (
    BooleanCriterionInput,
    CriterionInput,
    EvidenceReference,
)


class CapabilitySignalInput(BooleanCriterionInput):
    """A provenance-aware boolean input for one capability signal."""


def _unknown_capability_signal() -> CapabilitySignalInput:
    return CapabilitySignalInput(
        value=None,
        knowledge_state=KnowledgeState.UNKNOWN,
        rationale="No capability signal was supplied.",
    )


class CapabilitySignals(BaseModel):
    """Explicit Phase 1 task signals consumed by the deterministic mapper."""

    model_config = ConfigDict(extra="forbid")

    reads_unstructured_documents: CapabilitySignalInput = Field(
        default_factory=_unknown_capability_signal
    )
    categorises_items: CapabilitySignalInput = Field(
        default_factory=_unknown_capability_signal
    )
    predicts_future_outcomes: CapabilitySignalInput = Field(
        default_factory=_unknown_capability_signal
    )
    detects_anomalies_or_patterns: CapabilitySignalInput = Field(
        default_factory=_unknown_capability_signal
    )
    creates_new_content: CapabilitySignalInput = Field(
        default_factory=_unknown_capability_signal
    )
    searches_reference_knowledge: CapabilitySignalInput = Field(
        default_factory=_unknown_capability_signal
    )
    ranks_or_suggests_options: CapabilitySignalInput = Field(
        default_factory=_unknown_capability_signal
    )
    supports_complex_decisions: CapabilitySignalInput = Field(
        default_factory=_unknown_capability_signal
    )
    interprets_images_or_video: CapabilitySignalInput = Field(
        default_factory=_unknown_capability_signal
    )
    routes_or_orchestrates_work: CapabilitySignalInput = Field(
        default_factory=_unknown_capability_signal
    )

    @field_validator("*", mode="before")
    @classmethod
    def migrate_legacy_boolean(cls, value: object) -> object:
        if isinstance(value, bool):
            return {
                "value": value,
                "knowledge_state": KnowledgeState.KNOWN,
                "rationale": (
                    "Migrated from a legacy explicit boolean capability signal."
                ),
                "evidence_ids": [],
            }
        return value

    def inputs(self) -> Iterator[CapabilitySignalInput]:
        for field_name in type(self).model_fields:
            yield getattr(self, field_name)


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
    description: str | None = Field(default=None, min_length=1)
    actor: str | None = Field(default=None, min_length=1)
    responsible_role: str | None = None
    systems: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    exceptions: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    characteristics: TaskCharacteristics

    @field_validator("step_id", "activity", "description", "actor", "responsible_role")
    @classmethod
    def reject_blank_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Text values cannot be empty or whitespace-only")
        return value


class BusinessProcess(BaseModel):
    model_config = ConfigDict(extra="forbid")

    process_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str | None = Field(default=None, min_length=1)
    business_objective: str | None = Field(default=None, min_length=1)
    organisation: str | None = None
    evidence: list[EvidenceReference]
    steps: list[ProcessStep] = Field(min_length=1)

    @field_validator(
        "process_id", "name", "description", "business_objective", "organisation"
    )
    @classmethod
    def reject_blank_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Text values cannot be empty or whitespace-only")
        return value

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
            for signal in step.characteristics.capability_signals.inputs():
                referenced_evidence.update(signal.evidence_ids)
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
