"""Provider-neutral contracts used while producing Phase 3 candidates."""

from __future__ import annotations

from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_adoption_engine.models.candidate_process import (
    CapabilitySignalName,
    CandidateBusinessProcess,
    CollectionCompleteness,
)
from ai_adoption_engine.models.enums import CriterionName, KnowledgeState


T = TypeVar("T")


class ExtractionStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class ExtractionIssueSeverity(StrEnum):
    WARNING = "warning"
    ERROR = "error"


class RawEvidencePointer(BaseModel):
    """Untrusted provider citation; it never carries trusted offsets."""

    model_config = ConfigDict(extra="forbid")

    block_id: str = Field(min_length=1)
    exact_snippet: str = Field(min_length=1)
    occurrence: int | None = Field(default=None, ge=1)
    slice_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def use_one_disambiguator(self) -> "RawEvidencePointer":
        if self.occurrence is not None and self.slice_id is not None:
            raise ValueError("Use occurrence or slice_id, not both")
        return self


class RawCandidateAssertion(BaseModel, Generic[T]):
    model_config = ConfigDict(extra="forbid")

    value: T | None = None
    knowledge_state: KnowledgeState
    rationale: str = Field(min_length=1)
    evidence: list[RawEvidencePointer] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_provenance(self) -> "RawCandidateAssertion[T]":
        if self.knowledge_state is KnowledgeState.UNKNOWN:
            if self.value is not None:
                raise ValueError("Unknown assertions must use a null value")
            if self.evidence:
                raise ValueError("Unknown assertions cannot claim evidence")
            if self.confidence is not None:
                raise ValueError("Unknown assertions cannot carry confidence")
            return self
        if self.value is None:
            raise ValueError("Known or inferred assertions require a value")
        if not self.evidence:
            raise ValueError("Known or inferred assertions require evidence pointers")
        if self.knowledge_state is KnowledgeState.INFERRED:
            if self.confidence is None:
                raise ValueError("Inferred assertions require extraction confidence")
        elif self.confidence is not None:
            raise ValueError("Known assertions do not use model confidence")
        return self


class RawCandidateOrdinalAssertion(RawCandidateAssertion[int]):
    value: int | None = Field(default=None, ge=0, le=5)


class RawCandidateCollection(BaseModel, Generic[T]):
    model_config = ConfigDict(extra="forbid")

    completeness: CollectionCompleteness
    rationale: str = Field(min_length=1)
    items: list[RawCandidateAssertion[T]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_completeness(self) -> "RawCandidateCollection[T]":
        if self.completeness is CollectionCompleteness.UNKNOWN and self.items:
            raise ValueError("An unknown collection cannot contain assertions")
        return self


class RawCandidateCharacteristic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: CriterionName
    assertion: RawCandidateOrdinalAssertion


class RawCandidateCapabilitySignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: CapabilitySignalName
    assertion: RawCandidateAssertion[bool]


class RawCandidateTaskCharacteristics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criteria: list[RawCandidateCharacteristic]
    human_accountability_required: RawCandidateAssertion[bool]
    capability_signals: list[RawCandidateCapabilitySignal]

    @model_validator(mode="after")
    def require_explicit_unknowns(self) -> "RawCandidateTaskCharacteristics":
        criterion_names = [item.name for item in self.criteria]
        if len(criterion_names) != len(set(criterion_names)):
            raise ValueError("Raw candidate criterion names must be unique")
        if set(criterion_names) != set(CriterionName):
            raise ValueError("Every raw candidate criterion must be represented")
        signal_names = [item.name for item in self.capability_signals]
        if len(signal_names) != len(set(signal_names)):
            raise ValueError("Raw capability signal names must be unique")
        if set(signal_names) != set(CapabilitySignalName):
            raise ValueError("Every raw capability signal must be represented")
        return self


class RawCandidateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    condition: RawCandidateAssertion[str]
    branches: RawCandidateCollection[str]


class RawCandidateDependency(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_label: RawCandidateAssertion[str]
    relationship: RawCandidateAssertion[str]


class RawCandidateProcessStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local_step_id: str = Field(min_length=1)
    document_order: RawCandidateAssertion[int]
    activity: RawCandidateAssertion[str]
    description: RawCandidateAssertion[str]
    actors: RawCandidateCollection[str]
    responsible_roles: RawCandidateCollection[str]
    systems: RawCandidateCollection[str]
    inputs: RawCandidateCollection[str]
    outputs: RawCandidateCollection[str]
    decisions: list[RawCandidateDecision] = Field(default_factory=list)
    dependencies: list[RawCandidateDependency] = Field(default_factory=list)
    exceptions: RawCandidateCollection[str]
    operational_characteristics: RawCandidateCollection[str]
    characteristics: RawCandidateTaskCharacteristics

    @model_validator(mode="after")
    def require_supported_activity(self) -> "RawCandidateProcessStep":
        if self.activity.knowledge_state is KnowledgeState.UNKNOWN:
            raise ValueError("A raw candidate step requires a supported activity")
        return self


class RawChunkExtraction(BaseModel):
    """Strict provider output for one bounded document chunk."""

    model_config = ConfigDict(extra="forbid")

    process_name: RawCandidateAssertion[str]
    process_description: RawCandidateAssertion[str]
    process_objective: RawCandidateAssertion[str]
    steps: list[RawCandidateProcessStep] = Field(default_factory=list)
    multiple_processes_detected: bool


class ProviderUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


class ProviderInvocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_name: str = Field(min_length=1)
    requested_model: str = Field(min_length=1)
    effective_model: str | None = None
    request_id: str | None = None
    chunk_id: str = Field(min_length=1)
    attempt: int = Field(ge=1)
    usage: ProviderUsage = Field(default_factory=ProviderUsage)


class ExtractionIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: ExtractionIssueSeverity
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    chunk_id: str | None = None
    block_id: str | None = None
    field_path: str | None = None


class CandidateExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ExtractionStatus
    candidate: CandidateBusinessProcess | None = None
    issues: list[ExtractionIssue] = Field(default_factory=list)
    provider_invocations: list[ProviderInvocation] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_result(self) -> "CandidateExtractionResult":
        if self.status is ExtractionStatus.FAILED and self.candidate is not None:
            raise ValueError("Failed extraction cannot contain a candidate")
        if self.status is not ExtractionStatus.FAILED and self.candidate is None:
            raise ValueError("Successful or partial extraction requires a candidate")
        if self.status is ExtractionStatus.FAILED and not self.issues:
            raise ValueError("Failed extraction requires at least one issue")
        return self
