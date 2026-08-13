"""Provider-independent structured extraction boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ai_adoption_engine.extraction.chunking import DocumentChunk
from ai_adoption_engine.models.extraction import ProviderInvocation, RawChunkExtraction


@dataclass(frozen=True)
class ExtractionRequest:
    document_id: str
    chunk: DocumentChunk
    schema_version: str
    prompt_version: str
    attempt: int = 1
    repair_feedback: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProviderExtractionResponse:
    extraction: RawChunkExtraction
    invocation: ProviderInvocation


class StructuredExtractionProvider(Protocol):
    """One structured process-extraction call for one document chunk."""

    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    def extract_chunk(self, request: ExtractionRequest) -> ProviderExtractionResponse: ...
