"""Unconfirmed Phase 3 process-extraction contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_adoption_engine.models.enums import CriterionName, KnowledgeState


T = TypeVar("T")


class CandidateProcessStatus(StrEnum):
    CANDIDATE_UNCONFIRMED = "CANDIDATE / UNCONFIRMED PROCESS EXTRACTION"


class CollectionCompleteness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class OrderBasis(StrEnum):
    EXPLICIT = "explicit"
    SOURCE_POSITION = "source_position"
    UNRESOLVED = "unresolved"


class CapabilitySignalName(StrEnum):
    READS_UNSTRUCTURED_DOCUMENTS = "reads_unstructured_documents"
    CATEGORISES_ITEMS = "categorises_items"
    PREDICTS_FUTURE_OUTCOMES = "predicts_future_outcomes"
    DETECTS_ANOMALIES_OR_PATTERNS = "detects_anomalies_or_patterns"
    CREATES_NEW_CONTENT = "creates_new_content"
    SEARCHES_REFERENCE_KNOWLEDGE = "searches_reference_knowledge"
    RANKS_OR_SUGGESTS_OPTIONS = "ranks_or_suggests_options"
    SUPPORTS_COMPLEX_DECISIONS = "supports_complex_decisions"
    INTERPRETS_IMAGES_OR_VIDEO = "interprets_images_or_video"
    ROUTES_OR_ORCHESTRATES_WORK = "routes_or_orchestrates_work"


class ResolvedEvidenceReference(BaseModel):
    """Evidence whose location has been computed from trusted Phase 2 text."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(pattern=r"^cev-[0-9a-f]{64}$")
    document_id: str = Field(pattern=r"^doc-[0-9a-f]{64}$")
    block_id: str = Field(min_length=1)
    block_start_offset: int = Field(ge=0)
    block_end_offset: int = Field(gt=0)
    document_start_offset: int = Field(ge=0)
    document_end_offset: int = Field(gt=0)
    source_locator: str = Field(min_length=1)
    exact_snippet: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_offsets(self) -> "ResolvedEvidenceReference":
        if self.block_end_offset <= self.block_start_offset:
            raise ValueError("Evidence block offsets must describe a non-empty span")
        if self.document_end_offset <= self.document_start_offset:
            raise ValueError("Evidence document offsets must describe a non-empty span")
        span_length = self.block_end_offset - self.block_start_offset
        if span_length != len(self.exact_snippet):
            raise ValueError("Evidence block offsets must match snippet length")
        if self.document_end_offset - self.document_start_offset != span_length:
            raise ValueError("Evidence document offsets must match snippet length")
        return self


class CandidateAssertion(BaseModel, Generic[T]):
    """One unconfirmed value and its fully resolved supporting evidence."""

    model_config = ConfigDict(extra="forbid")

    value: T | None = None
    knowledge_state: KnowledgeState
    rationale: str = Field(min_length=1)
    evidence: list[ResolvedEvidenceReference] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_provenance(self) -> "CandidateAssertion[T]":
        if self.knowledge_state is KnowledgeState.UNKNOWN:
            if self.value is not None:
                raise ValueError("Unknown assertions must use a null value")
            if self.evidence:
                raise ValueError("Unknown assertions cannot claim supporting evidence")
            if self.confidence is not None:
                raise ValueError("Unknown assertions cannot carry confidence")
            return self
        if self.value is None:
            raise ValueError("Known or inferred assertions require a value")
        if not self.evidence:
            raise ValueError("Known or inferred assertions require resolved evidence")
        if self.knowledge_state is KnowledgeState.INFERRED:
            if self.confidence is None:
                raise ValueError("Inferred assertions require extraction confidence")
        elif self.confidence is not None:
            raise ValueError("Directly known assertions do not use model confidence")
        return self


class CandidateOrdinalAssertion(CandidateAssertion[int]):
    value: int | None = Field(default=None, ge=0, le=5)


class CandidateCollection(BaseModel, Generic[T]):
    """A collection that distinguishes unknown from supported-empty content."""

    model_config = ConfigDict(extra="forbid")

    completeness: CollectionCompleteness
    rationale: str = Field(min_length=1)
    items: list[CandidateAssertion[T]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_completeness(self) -> "CandidateCollection[T]":
        if self.completeness is CollectionCompleteness.UNKNOWN and self.items:
            raise ValueError("An unknown collection cannot contain asserted items")
        return self


class CandidateCharacteristic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: CriterionName
    assertion: CandidateOrdinalAssertion


class CandidateCapabilitySignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: CapabilitySignalName
    assertion: CandidateAssertion[bool]


class CandidateTaskCharacteristics(BaseModel):
    """Unconfirmed Phase 1-compatible inputs; no recommendation logic lives here."""

    model_config = ConfigDict(extra="forbid")

    criteria: list[CandidateCharacteristic]
    human_accountability_required: CandidateAssertion[bool]
    capability_signals: list[CandidateCapabilitySignal]

    @model_validator(mode="after")
    def require_explicit_unknowns(self) -> "CandidateTaskCharacteristics":
        criterion_names = [item.name for item in self.criteria]
        if len(criterion_names) != len(set(criterion_names)):
            raise ValueError("Candidate criterion names must be unique")
        if set(criterion_names) != set(CriterionName):
            raise ValueError("Every candidate criterion must be explicitly represented")
        signal_names = [item.name for item in self.capability_signals]
        if len(signal_names) != len(set(signal_names)):
            raise ValueError("Candidate capability signal names must be unique")
        if set(signal_names) != set(CapabilitySignalName):
            raise ValueError(
                "Every candidate capability signal must be explicitly represented"
            )
        return self


class CandidateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    condition: CandidateAssertion[str]
    branches: CandidateCollection[str]


class CandidateDependency(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_label: CandidateAssertion[str]
    relationship: CandidateAssertion[str]
    target_candidate_step_id: str | None = None


class CandidateProcessStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_step_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    order_basis: OrderBasis
    document_order: CandidateAssertion[int]
    activity: CandidateAssertion[str]
    description: CandidateAssertion[str]
    actors: CandidateCollection[str]
    responsible_roles: CandidateCollection[str]
    systems: CandidateCollection[str]
    inputs: CandidateCollection[str]
    outputs: CandidateCollection[str]
    decisions: list[CandidateDecision] = Field(default_factory=list)
    dependencies: list[CandidateDependency] = Field(default_factory=list)
    exceptions: CandidateCollection[str]
    operational_characteristics: CandidateCollection[str]
    characteristics: CandidateTaskCharacteristics

    @model_validator(mode="after")
    def require_supported_activity(self) -> "CandidateProcessStep":
        if self.activity.knowledge_state is KnowledgeState.UNKNOWN:
            raise ValueError("A candidate step requires a supported activity")
        return self


class CandidateBusinessProcess(BaseModel):
    """Phase 3 output that cannot be mistaken for validated Phase 1 input."""

    model_config = ConfigDict(extra="forbid")

    candidate_status: CandidateProcessStatus = (
        CandidateProcessStatus.CANDIDATE_UNCONFIRMED
    )
    extraction_run_id: str = Field(min_length=1)
    source_document_id: str = Field(pattern=r"^doc-[0-9a-f]{64}$")
    schema_version: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    process_name: CandidateAssertion[str]
    process_description: CandidateAssertion[str]
    process_objective: CandidateAssertion[str]
    steps: list[CandidateProcessStep] = Field(default_factory=list)

    @field_validator("steps")
    @classmethod
    def validate_step_order(
        cls, steps: list[CandidateProcessStep]
    ) -> list[CandidateProcessStep]:
        sequences = [step.sequence for step in steps]
        if sequences != list(range(1, len(steps) + 1)):
            raise ValueError("Candidate step sequences must be contiguous and ordered")
        ids = [step.candidate_step_id for step in steps]
        if len(ids) != len(set(ids)):
            raise ValueError("Candidate step IDs must be unique")
        return steps
