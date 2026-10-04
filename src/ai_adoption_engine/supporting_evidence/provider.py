"""Closed provider boundary for value-free supporting-evidence extraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from ai_adoption_engine.extraction.chunking import DocumentChunk
from ai_adoption_engine.models.formal_evidence import (
    DocumentCategory,
    EvidenceClassification,
    ExtractorIdentity,
    FormalTarget,
)
from ai_adoption_engine.models.four_gate_assessment import FourGateName


SUPPORTING_EVIDENCE_PROVIDER_SCHEMA = "supporting-evidence-provider-output.v0.1"
SUPPORTING_EVIDENCE_PROVIDER_SCHEMA_VERSION = "0.1.0"
SUPPORTING_EVIDENCE_PROMPT_ID = "supporting-evidence-extraction.v0.1"
SUPPORTING_EVIDENCE_PROMPT_VERSION = "0.1.0"
SUPPORTING_EVIDENCE_EXTRACTOR_ID = "supporting-evidence-extractor.v0.1"
SUPPORTING_EVIDENCE_EXTRACTOR_VERSION = "0.1.0"


class _ClosedProviderModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RawSupportingCitation(_ClosedProviderModel):
    document_id: str = Field(min_length=1)
    block_id: str = Field(min_length=1)
    exact_excerpt: str = Field(min_length=1)
    block_character_start: int | None = Field(default=None, ge=0)
    block_character_end_exclusive: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_optional_offsets(self) -> "RawSupportingCitation":
        if (self.block_character_start is None) != (
            self.block_character_end_exclusive is None
        ):
            raise ValueError("citation offsets must be supplied together")
        if self.block_character_start is not None:
            if self.block_character_end_exclusive <= self.block_character_start:
                raise ValueError("citation offsets must be non-empty and half-open")
            if (
                self.block_character_end_exclusive - self.block_character_start
                != len(self.exact_excerpt)
            ):
                raise ValueError("citation offset length must equal the excerpt length")
        return self


class RawSupportingEvidenceItem(_ClosedProviderModel):
    proposed_claim: str = Field(min_length=1)
    proposed_classification: EvidenceClassification
    primary_citation: RawSupportingCitation
    related_citations: tuple[RawSupportingCitation, ...] = ()
    proposed_category: DocumentCategory
    suggested_activity_ids: tuple[str, ...] = ()
    suggested_formal_targets: tuple[FormalTarget, ...] = ()
    explanatory_gate_relevance: FourGateName | None = None
    ambiguity_indicated: StrictBool
    conflict_indicated: StrictBool
    relevance_explanation: str = Field(min_length=1)
    extraction_confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def require_unique_suggestions(self) -> "RawSupportingEvidenceItem":
        if len(self.suggested_activity_ids) != len(set(self.suggested_activity_ids)):
            raise ValueError("suggested activity identities must be unique")
        citations = (self.primary_citation, *self.related_citations)
        citation_keys = [item.model_dump_json() for item in citations]
        if len(citation_keys) != len(set(citation_keys)):
            raise ValueError("provider citations must be unique")
        target_keys = [item.model_dump_json() for item in self.suggested_formal_targets]
        if len(target_keys) != len(set(target_keys)):
            raise ValueError("suggested formal targets must be unique")
        return self


class RawSupportingEvidenceBatch(_ClosedProviderModel):
    schema_version: Literal["supporting-evidence-provider-output.v0.1"]
    items: tuple[RawSupportingEvidenceItem, ...]


@dataclass(frozen=True)
class ApprovedActivity:
    activity_id: str
    activity_name: str


@dataclass(frozen=True)
class SupportingEvidenceProviderRequest:
    document_id: str
    document_content_sha256: str
    chunk: DocumentChunk
    approved_activities: tuple[ApprovedActivity, ...]
    schema_version: str = SUPPORTING_EVIDENCE_PROVIDER_SCHEMA
    prompt_id: str = SUPPORTING_EVIDENCE_PROMPT_ID
    prompt_version: str = SUPPORTING_EVIDENCE_PROMPT_VERSION


class SupportingEvidenceProvider(Protocol):
    @property
    def is_external(self) -> bool: ...

    @property
    def extractor_identity(self) -> ExtractorIdentity: ...

    def extract(
        self, request: SupportingEvidenceProviderRequest
    ) -> RawSupportingEvidenceBatch: ...


class SupportingEvidenceProviderInterrupted(RuntimeError):
    """Injected provider work stopped without producing a terminal response."""


class ScriptedSupportingEvidenceProvider:
    """Deterministic injected provider for offline tests and controlled demos."""

    def __init__(
        self,
        responses: tuple[RawSupportingEvidenceBatch | Exception, ...],
        *,
        external: bool = False,
        provider_id: str = "scripted-local",
        provider_version: str = "1",
    ) -> None:
        self.responses = responses
        self._external = external
        self.calls: list[SupportingEvidenceProviderRequest] = []
        self._identity = ExtractorIdentity(
            extractor_id=SUPPORTING_EVIDENCE_EXTRACTOR_ID,
            extractor_version=SUPPORTING_EVIDENCE_EXTRACTOR_VERSION,
            provider_id=provider_id,
            provider_version=provider_version,
            output_schema_id=SUPPORTING_EVIDENCE_PROVIDER_SCHEMA,
            output_schema_version=SUPPORTING_EVIDENCE_PROVIDER_SCHEMA_VERSION,
            prompt_id=SUPPORTING_EVIDENCE_PROMPT_ID,
            prompt_version=SUPPORTING_EVIDENCE_PROMPT_VERSION,
        )

    @property
    def is_external(self) -> bool:
        return self._external

    @property
    def extractor_identity(self) -> ExtractorIdentity:
        return self._identity

    def extract(
        self, request: SupportingEvidenceProviderRequest
    ) -> RawSupportingEvidenceBatch:
        index = len(self.calls)
        self.calls.append(request)
        if index >= len(self.responses):
            raise RuntimeError("No scripted supporting-evidence response remains")
        response = self.responses[index]
        if isinstance(response, Exception):
            raise response
        return response


def raw_schema_forbids_formal_values() -> bool:
    schema_text = str(RawSupportingEvidenceBatch.model_json_schema())
    forbidden = {
        "approved_mapping",
        "formal_value",
        "knowledge_state",
        "gate_result",
        "evidence_sufficiency",
        "organisational_outcome",
    }
    return not any(item in schema_text for item in forbidden)
