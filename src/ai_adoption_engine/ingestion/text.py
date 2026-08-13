"""Plain-text file and raw/pasted text ingestion."""

import hashlib
from pathlib import Path

from charset_normalizer import from_bytes

from ai_adoption_engine.ingestion.builders import BlockDraft, build_blocks
from ai_adoption_engine.ingestion.normalization import split_text_blocks
from ai_adoption_engine.models.document import (
    DocumentInputType,
    DocumentMetadata,
    DocumentSource,
    IngestedDocument,
    IngestionIssue,
    IngestionResult,
    IngestionStatus,
    IssueSeverity,
)

TEXT_PARSER_NAME = "ai_adoption_engine.text"
TEXT_PARSER_VERSION = "1"


def _failed(code: str, message: str) -> IngestionResult:
    return IngestionResult(
        status=IngestionStatus.FAILED,
        issues=[IngestionIssue(severity=IssueSeverity.ERROR, code=code, message=message)],
    )


def _decode_text(payload: bytes) -> tuple[str | None, str | None, list[IngestionIssue]]:
    issues: list[IngestionIssue] = []
    if b"\x00" in payload:
        return None, None, [
            IngestionIssue(
                severity=IssueSeverity.ERROR,
                code="text-decode-failed",
                message="The input appears to be binary rather than plain text.",
            )
        ]
    try:
        return payload.decode("utf-8-sig"), "utf-8", issues
    except UnicodeDecodeError:
        match = from_bytes(payload).best()
        if match is None:
            return None, None, [
                IngestionIssue(
                    severity=IssueSeverity.ERROR,
                    code="text-decode-failed",
                    message="No plausible text encoding could be detected.",
                )
            ]
        issues.append(
            IngestionIssue(
                severity=IssueSeverity.WARNING,
                code="text-encoding-inferred",
                message=f"Text encoding was inferred as {match.encoding}.",
            )
        )
        return str(match), match.encoding, issues


def _build_text_document(
    *,
    payload: bytes,
    text: str,
    input_type: DocumentInputType,
    original_filename: str | None,
    detected_encoding: str,
    issues: list[IngestionIssue],
) -> IngestionResult:
    normalized_blocks = split_text_blocks(text)
    if not normalized_blocks:
        return _failed("empty-text", "The supplied text contains no ingestible content.")
    drafts = [
        BlockDraft(
            text=block.text,
            line_start=block.line_start,
            line_end=block.line_end,
        )
        for block in normalized_blocks
    ]
    canonical_text, blocks = build_blocks(drafts, input_type)
    digest = hashlib.sha256(payload).hexdigest()
    document = IngestedDocument(
        document_id=f"doc-{digest}",
        source=DocumentSource(
            input_type=input_type,
            original_filename=original_filename,
            media_type="text/plain",
            byte_size=len(payload),
            sha256=digest,
            detected_encoding=detected_encoding,
            parser_name=TEXT_PARSER_NAME,
            parser_version=TEXT_PARSER_VERSION,
        ),
        metadata=DocumentMetadata(),
        canonical_text=canonical_text,
        blocks=blocks,
    )
    return IngestionResult(
        status=IngestionStatus.PARTIAL if issues else IngestionStatus.SUCCESS,
        document=document,
        issues=issues,
    )


def ingest_text_bytes(payload: bytes, filename: str) -> IngestionResult:
    if not filename.lower().endswith(".txt"):
        return _failed("unsupported-file-type", "Only .txt plain-text files are supported.")
    text, encoding, issues = _decode_text(payload)
    if text is None or encoding is None:
        return IngestionResult(status=IngestionStatus.FAILED, issues=issues)
    return _build_text_document(
        payload=payload,
        text=text,
        input_type=DocumentInputType.PLAIN_TEXT_FILE,
        original_filename=Path(filename).name,
        detected_encoding=encoding,
        issues=issues,
    )


def ingest_raw_text(text: str) -> IngestionResult:
    payload = text.encode("utf-8")
    return _build_text_document(
        payload=payload,
        text=text,
        input_type=DocumentInputType.RAW_TEXT,
        original_filename=None,
        detected_encoding="utf-8",
        issues=[],
    )
