"""Text-native PDF ingestion with page-preserving provenance."""

import hashlib
from io import BytesIO

import pypdf
from pypdf import PdfReader

from ai_adoption_engine.ingestion.builders import BlockDraft, build_blocks
from ai_adoption_engine.ingestion.normalization import split_pdf_page_blocks
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

PDF_PARSER_NAME = "pypdf"


def _failed(code: str, message: str) -> IngestionResult:
    return IngestionResult(
        status=IngestionStatus.FAILED,
        issues=[IngestionIssue(severity=IssueSeverity.ERROR, code=code, message=message)],
    )


def _metadata_value(metadata: object, name: str) -> str | None:
    try:
        value = getattr(metadata, name, None) if metadata is not None else None
    except Exception:
        return None
    return str(value) if value is not None else None


def ingest_pdf_bytes(payload: bytes, filename: str) -> IngestionResult:
    if not filename.lower().endswith(".pdf") or not payload.startswith(b"%PDF-"):
        return _failed("invalid-pdf", "Input is not a supported PDF file.")
    try:
        reader = PdfReader(BytesIO(payload), strict=False)
    except Exception as exc:
        return _failed("pdf-open-failed", f"PDF could not be opened: {exc}")
    if reader.is_encrypted:
        return _failed("encrypted-pdf", "Encrypted PDFs are not supported in Phase 2.")

    drafts: list[BlockDraft] = []
    issues: list[IngestionIssue] = []
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            extracted = page.extract_text() or ""
        except Exception as exc:
            block_id = f"p{page_number:04d}-b0001"
            drafts.append(
                BlockDraft(
                    text="",
                    page_number=page_number,
                    has_extractable_text=False,
                )
            )
            issues.append(
                IngestionIssue(
                    severity=IssueSeverity.ERROR,
                    code="pdf-page-extraction-failed",
                    message=f"Page text extraction failed: {exc}",
                    page_number=page_number,
                    block_id=block_id,
                )
            )
            continue
        page_blocks = split_pdf_page_blocks(extracted)
        if not page_blocks:
            block_id = f"p{page_number:04d}-b0001"
            drafts.append(
                BlockDraft(
                    text="",
                    page_number=page_number,
                    has_extractable_text=False,
                )
            )
            issues.append(
                IngestionIssue(
                    severity=IssueSeverity.WARNING,
                    code="pdf-page-no-extractable-text",
                    message=(
                        "Page contains no extractable text. OCR is outside Phase 2 scope."
                    ),
                    page_number=page_number,
                    block_id=block_id,
                )
            )
        else:
            drafts.extend(
                BlockDraft(text=block.text, page_number=page_number)
                for block in page_blocks
            )

    if not drafts:
        return _failed("empty-pdf", "The PDF contains no pages to ingest.")

    canonical_text, blocks = build_blocks(drafts, DocumentInputType.PDF)
    digest = hashlib.sha256(payload).hexdigest()
    metadata = reader.metadata
    document = IngestedDocument(
        document_id=f"doc-{digest}",
        source=DocumentSource(
            input_type=DocumentInputType.PDF,
            original_filename=filename,
            media_type="application/pdf",
            byte_size=len(payload),
            sha256=digest,
            detected_encoding=None,
            parser_name=PDF_PARSER_NAME,
            parser_version=pypdf.__version__,
        ),
        metadata=DocumentMetadata(
            title=_metadata_value(metadata, "title"),
            author=_metadata_value(metadata, "author"),
            subject=_metadata_value(metadata, "subject"),
            creator=_metadata_value(metadata, "creator"),
            producer=_metadata_value(metadata, "producer"),
            created_at=_metadata_value(metadata, "creation_date"),
            modified_at=_metadata_value(metadata, "modification_date"),
            page_count=len(reader.pages),
        ),
        canonical_text=canonical_text,
        blocks=blocks,
    )
    return IngestionResult(
        status=IngestionStatus.PARTIAL if issues else IngestionStatus.SUCCESS,
        document=document,
        issues=issues,
    )
