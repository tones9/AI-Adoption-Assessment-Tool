"""Versioned Phase 3 extraction configuration."""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_adoption_engine.extraction.chunking import ChunkingConfig


class ExtractionConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    configuration_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    reasoning_effort: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    tools_enabled: bool
    streaming_enabled: bool
    store_responses: bool
    timeout_seconds: float = Field(gt=0)
    sdk_max_retries: int = Field(ge=0)
    repair_attempts: int = Field(ge=0, le=1)
    max_output_tokens: int = Field(gt=0)
    chunk_max_characters: int = Field(gt=0)
    chunk_max_non_empty_blocks: int = Field(gt=0)
    chunk_overlap_blocks: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_phase3_constraints(self) -> "ExtractionConfiguration":
        if self.tools_enabled:
            raise ValueError("Phase 3 extraction must not enable model tools")
        if self.streaming_enabled:
            raise ValueError("Phase 3 MVP extraction must not enable streaming")
        if self.store_responses:
            raise ValueError("Phase 3 extraction must not request response storage")
        if self.chunk_overlap_blocks >= self.chunk_max_non_empty_blocks:
            raise ValueError("Chunk overlap must be smaller than the block limit")
        return self

    def chunking_config(self) -> ChunkingConfig:
        return ChunkingConfig(
            max_characters=self.chunk_max_characters,
            max_non_empty_blocks=self.chunk_max_non_empty_blocks,
            overlap_blocks=self.chunk_overlap_blocks,
        )


def load_extraction_configuration(
    path: str | Path,
) -> ExtractionConfiguration:
    with Path(path).open(encoding="utf-8") as handle:
        return ExtractionConfiguration.model_validate(json.load(handle))
