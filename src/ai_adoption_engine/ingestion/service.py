"""File/domain entry points that route inputs to document-only parsers."""

from pathlib import Path

from ai_adoption_engine.ingestion.pdf import ingest_pdf_bytes
from ai_adoption_engine.ingestion.text import ingest_raw_text, ingest_text_bytes
from ai_adoption_engine.models.document import (
    IngestionIssue,
    IngestionResult,
    IngestionStatus,
    IssueSeverity,
)


def ingest_file(path: str | Path) -> IngestionResult:
    source_path = Path(path)
    try:
        payload = source_path.read_bytes()
    except OSError as exc:
        return IngestionResult(
            status=IngestionStatus.FAILED,
            issues=[
                IngestionIssue(
                    severity=IssueSeverity.ERROR,
                    code="file-read-failed",
                    message=f"Input file could not be read: {exc}",
                )
            ],
        )
    suffix = source_path.suffix.lower()
    if suffix == ".pdf":
        return ingest_pdf_bytes(payload, source_path.name)
    if suffix == ".txt":
        return ingest_text_bytes(payload, source_path.name)
    return IngestionResult(
        status=IngestionStatus.FAILED,
        issues=[
            IngestionIssue(
                severity=IssueSeverity.ERROR,
                code="unsupported-file-type",
                message="Phase 2 supports only .pdf and .txt files.",
            )
        ],
    )


__all__ = ["ingest_file", "ingest_raw_text"]

