"""Stable document-level contracts produced by Phase 2 ingestion."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DocumentInputType(StrEnum):
    PDF = "pdf"
    PLAIN_TEXT_FILE = "plain_text_file"
    RAW_TEXT = "raw_text"


class IngestionStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class IssueSeverity(StrEnum):
    WARNING = "warning"
    ERROR = "error"


class DocumentSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_type: DocumentInputType
    original_filename: str | None = None
    media_type: str
    byte_size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    detected_encoding: str | None = None
    parser_name: str
    parser_version: str


class DocumentMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    author: str | None = None
    subject: str | None = None
    creator: str | None = None
    producer: str | None = None
    created_at: str | None = None
    modified_at: str | None = None
    page_count: int | None = Field(default=None, ge=0)


class TextBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    block_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    page_number: int | None = Field(default=None, ge=1)
    block_number: int = Field(ge=1)
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    document_start_offset: int = Field(ge=0)
    document_end_offset: int = Field(ge=0)
    source_locator: str = Field(min_length=1)
    extracted_text: str
    has_extractable_text: bool = True

    @model_validator(mode="after")
    def validate_span(self) -> "TextBlock":
        if self.document_end_offset < self.document_start_offset:
            raise ValueError("Block end offset cannot precede its start offset")
        if self.has_extractable_text != bool(self.extracted_text):
            raise ValueError(
                "has_extractable_text must match whether extracted_text is non-empty"
            )
        if (self.line_start is None) != (self.line_end is None):
            raise ValueError("Line start and end must be supplied together")
        if self.line_start is not None and self.line_end < self.line_start:
            raise ValueError("Line end cannot precede line start")
        return self


class IngestedDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(pattern=r"^doc-[0-9a-f]{64}$")
    source: DocumentSource
    metadata: DocumentMetadata
    canonical_text: str
    blocks: list[TextBlock] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_block_contract(self) -> "IngestedDocument":
        block_ids = [block.block_id for block in self.blocks]
        if len(block_ids) != len(set(block_ids)):
            raise ValueError("Block IDs must be unique")
        sequences = [block.sequence for block in self.blocks]
        if sequences != list(range(1, len(self.blocks) + 1)):
            raise ValueError("Block sequences must be contiguous and ordered")
        previous_end = 0
        for block in self.blocks:
            if block.document_start_offset < previous_end:
                raise ValueError("Block offsets must be ordered and non-overlapping")
            resolved = self.canonical_text[
                block.document_start_offset : block.document_end_offset
            ]
            if resolved != block.extracted_text:
                raise ValueError(
                    f"Block {block.block_id} offsets do not resolve to its text"
                )
            previous_end = block.document_end_offset
        return self


class IngestionIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: IssueSeverity
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    page_number: int | None = Field(default=None, ge=1)
    block_id: str | None = None


class IngestionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: IngestionStatus
    document: IngestedDocument | None = None
    issues: list[IngestionIssue] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_result(self) -> "IngestionResult":
        if self.status is IngestionStatus.FAILED and self.document is not None:
            raise ValueError("Failed ingestion cannot contain a document")
        if self.status is not IngestionStatus.FAILED and self.document is None:
            raise ValueError("Successful or partial ingestion requires a document")
        if self.status is IngestionStatus.FAILED and not self.issues:
            raise ValueError("Failed ingestion requires at least one issue")
        return self
