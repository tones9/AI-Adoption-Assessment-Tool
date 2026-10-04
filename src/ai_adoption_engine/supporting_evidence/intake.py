"""Explicit supporting-document intake with pre-persistence file safety checks."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject, NameObject

from ai_adoption_engine.ingestion.pdf import ingest_pdf_bytes
from ai_adoption_engine.ingestion.text import ingest_text_bytes
from ai_adoption_engine.models.document import IngestedDocument, IngestionStatus
from ai_adoption_engine.persistence.base import ArtifactNotFoundError
from ai_adoption_engine.models.formal_evidence import (
    FORMAL_EVIDENCE_FAMILY,
    MAX_CURRENT_DOCUMENTS,
    MAX_EXTRACTED_CHARACTERS,
    MAX_FORMAL_LIFECYCLE_BYTES,
    MAX_PDF_PAGES,
    MAX_SUPPORTING_FILE_BYTES,
    SUPPORTING_DOCUMENT_METADATA_REVISION_SCHEMA,
    SUPPORTING_DOCUMENT_SCHEMA,
    SUPPORTING_SOURCE_BLOB_SCHEMA,
    CoveredPeriod,
    DocumentCategory,
    FormalEvidenceLineage,
    ReviewerDeclaration,
    SourceBlobState,
    SupportingDocument,
    SupportingDocumentMetadataRevision,
    SupportingDocumentReference,
    SupportingFileRejectionCode,
    SupportingSourceBlob,
)
from ai_adoption_engine.persistence.formal_evidence import (
    FormalEvidenceIdempotencyError,
    FormalEvidenceIntegrityError,
    FormalEvidenceLineageError,
    SQLiteFormalEvidenceRepository,
)
from ai_adoption_engine.supporting_evidence.common import (
    Clock,
    IdFactory,
    new_id,
    request_identity,
    require_lineage,
    utc_now,
)
from ai_adoption_engine.supporting_evidence.errors import (
    SupportingEvidenceDuplicateSourceError,
    SupportingEvidenceEncryptedPdfError,
    SupportingEvidenceInvalidTextError,
    SupportingEvidenceLimitError,
    SupportingEvidenceLineageError,
    SupportingEvidenceMalformedPdfError,
    SupportingEvidenceRequestConflictError,
    SupportingEvidenceServiceError,
    SupportingEvidenceUnsafePdfError,
    SupportingEvidenceUnreadablePdfError,
    SupportingEvidenceUnsupportedFileError,
)


_ACTIVE_PDF_NAMES = frozenset(
    {
        "/AA",
        "/EmbeddedFile",
        "/EmbeddedFiles",
        "/JavaScript",
        "/JS",
        "/Launch",
        "/OpenAction",
        "/RichMedia",
    }
)
_ARCHIVE_SIGNATURES = (
    b"PK\x03\x04",
    b"PK\x05\x06",
    b"PK\x07\x08",
    b"Rar!",
    b"7z\xbc\xaf\x27\x1c",
)
_EXECUTABLE_SIGNATURES = (b"MZ", b"\x7fELF", b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf")


@dataclass(frozen=True)
class SupportingFileInspection:
    safe_filename: str
    content_sha256: str
    media_type: str
    ingestion: IngestedDocument | None
    ingestion_issue_codes: tuple[str, ...]
    rejection_code: SupportingFileRejectionCode | None = None


@dataclass(frozen=True)
class SupportingDocumentIntakeResult:
    document: SupportingDocument
    ingestion_preview: IngestedDocument | None
    ingestion_issue_codes: tuple[str, ...]
    replayed: bool
    reused_existing_document: bool


def _safe_filename(filename: str) -> str:
    basename = Path(filename.replace("\\", "/")).name
    safe = "".join(
        character if 32 <= ord(character) < 127 else "_"
        for character in basename
    ).strip()
    if not safe or safe in {".", ".."}:
        raise SupportingEvidenceUnsupportedFileError(
            "The supporting filename is not usable."
        )
    return safe[:255]


def _pdf_has_active_content(reader: PdfReader) -> bool:
    seen: set[tuple[int, int]] = set()

    def visit(value: Any, depth: int = 0) -> bool:
        if depth > 80:
            return True
        if isinstance(value, IndirectObject):
            identity = (value.idnum, value.generation)
            if identity in seen:
                return False
            seen.add(identity)
            try:
                value = value.get_object()
            except Exception:
                return True
        if isinstance(value, DictionaryObject):
            for key, item in value.items():
                if str(key) in _ACTIVE_PDF_NAMES or visit(item, depth + 1):
                    return True
        elif isinstance(value, ArrayObject):
            return any(visit(item, depth + 1) for item in value)
        elif isinstance(value, NameObject) and str(value) in _ACTIVE_PDF_NAMES:
            return True
        return False

    try:
        return visit(reader.trailer["/Root"])
    except Exception:
        return True


def _binary_text(text: str) -> bool:
    if not text:
        return False
    controls = sum(
        1
        for character in text
        if ord(character) < 32 and character not in "\n\r\t\f"
    )
    return controls / len(text) > 0.01


def inspect_supporting_file(filename: str, raw_bytes: bytes) -> SupportingFileInspection:
    safe_filename = _safe_filename(filename)
    digest = hashlib.sha256(raw_bytes).hexdigest()
    suffix = Path(safe_filename).suffix.lower()

    if len(raw_bytes) > MAX_SUPPORTING_FILE_BYTES:
        return SupportingFileInspection(
            safe_filename,
            digest,
            "application/octet-stream",
            None,
            (),
            SupportingFileRejectionCode.FILE_TOO_LARGE,
        )
    if suffix not in {".pdf", ".txt"}:
        code = {
            ".doc": SupportingFileRejectionCode.WORD_DOCUMENT,
            ".docx": SupportingFileRejectionCode.WORD_DOCUMENT,
            ".xls": SupportingFileRejectionCode.SPREADSHEET,
            ".xlsx": SupportingFileRejectionCode.SPREADSHEET,
            ".ppt": SupportingFileRejectionCode.PRESENTATION,
            ".pptx": SupportingFileRejectionCode.PRESENTATION,
            ".zip": SupportingFileRejectionCode.ARCHIVE,
        }.get(suffix, SupportingFileRejectionCode.UNSUPPORTED_FILE_TYPE)
        return SupportingFileInspection(
            safe_filename, digest, "application/octet-stream", None, (), code
        )

    if raw_bytes.startswith(_EXECUTABLE_SIGNATURES):
        return SupportingFileInspection(
            safe_filename,
            digest,
            "application/octet-stream",
            None,
            (),
            SupportingFileRejectionCode.EXECUTABLE,
        )
    if raw_bytes.startswith(_ARCHIVE_SIGNATURES):
        return SupportingFileInspection(
            safe_filename,
            digest,
            "application/zip",
            None,
            (),
            SupportingFileRejectionCode.ARCHIVE,
        )

    if suffix == ".pdf":
        if not raw_bytes.startswith(b"%PDF-"):
            return SupportingFileInspection(
                safe_filename,
                digest,
                "application/pdf",
                None,
                (),
                SupportingFileRejectionCode.MALFORMED,
            )
        try:
            reader = PdfReader(BytesIO(raw_bytes), strict=True)
            if reader.is_encrypted:
                code = SupportingFileRejectionCode.ENCRYPTED
            elif len(reader.pages) > MAX_PDF_PAGES:
                code = SupportingFileRejectionCode.PDF_PAGE_LIMIT_EXCEEDED
            elif _pdf_has_active_content(reader):
                code = SupportingFileRejectionCode.ACTIVE_CONTENT
            else:
                code = None
        except Exception:
            code = SupportingFileRejectionCode.MALFORMED
        if code is not None:
            return SupportingFileInspection(
                safe_filename, digest, "application/pdf", None, (), code
            )
        result = ingest_pdf_bytes(raw_bytes, safe_filename)
        if result.status is IngestionStatus.FAILED or result.document is None:
            issue_codes = tuple(item.code for item in result.issues)
            rejection = (
                SupportingFileRejectionCode.ENCRYPTED
                if "encrypted-pdf" in issue_codes
                else SupportingFileRejectionCode.MALFORMED
            )
            return SupportingFileInspection(
                safe_filename,
                digest,
                "application/pdf",
                None,
                issue_codes,
                rejection,
            )
        document = result.document
        if not document.canonical_text.strip():
            return SupportingFileInspection(
                safe_filename,
                digest,
                "application/pdf",
                None,
                tuple(item.code for item in result.issues),
                SupportingFileRejectionCode.SCANNED_OR_NO_TEXT,
            )
        if len(document.canonical_text) > MAX_EXTRACTED_CHARACTERS:
            return SupportingFileInspection(
                safe_filename,
                digest,
                "application/pdf",
                None,
                tuple(item.code for item in result.issues),
                SupportingFileRejectionCode.EXTRACTED_CHARACTER_LIMIT_EXCEEDED,
            )
        return SupportingFileInspection(
            safe_filename,
            digest,
            "application/pdf",
            document,
            tuple(item.code for item in result.issues),
        )

    if raw_bytes.startswith(b"%PDF-"):
        return SupportingFileInspection(
            safe_filename,
            digest,
            "text/plain",
            None,
            (),
            SupportingFileRejectionCode.UNSUPPORTED_FILE_TYPE,
        )
    result = ingest_text_bytes(raw_bytes, safe_filename)
    if result.status is IngestionStatus.FAILED or result.document is None:
        return SupportingFileInspection(
            safe_filename,
            digest,
            "text/plain",
            None,
            tuple(item.code for item in result.issues),
            SupportingFileRejectionCode.MALFORMED,
        )
    if _binary_text(result.document.canonical_text):
        return SupportingFileInspection(
            safe_filename,
            digest,
            "text/plain",
            None,
            (),
            SupportingFileRejectionCode.MALFORMED,
        )
    if len(result.document.canonical_text) > MAX_EXTRACTED_CHARACTERS:
        return SupportingFileInspection(
            safe_filename,
            digest,
            "text/plain",
            None,
            tuple(item.code for item in result.issues),
            SupportingFileRejectionCode.EXTRACTED_CHARACTER_LIMIT_EXCEEDED,
        )
    return SupportingFileInspection(
        safe_filename,
        digest,
        "text/plain",
        result.document,
        tuple(item.code for item in result.issues),
    )


def _failure_for_rejection(
    code: SupportingFileRejectionCode,
    *,
    media_type: str | None = None,
    result: Any | None = None,
) -> SupportingEvidenceServiceError:
    if code is SupportingFileRejectionCode.ENCRYPTED:
        return SupportingEvidenceEncryptedPdfError(
            "Encrypted or password-protected PDFs are not supported.", result=result
        )
    if code is SupportingFileRejectionCode.ACTIVE_CONTENT:
        return SupportingEvidenceUnsafePdfError(
            "The PDF contains unsupported active or embedded content.", result=result
        )
    if code is SupportingFileRejectionCode.SCANNED_OR_NO_TEXT:
        return SupportingEvidenceUnreadablePdfError(
            "The PDF contains no usable text and OCR is not available.", result=result
        )
    if code in {
        SupportingFileRejectionCode.FILE_TOO_LARGE,
        SupportingFileRejectionCode.PDF_PAGE_LIMIT_EXCEEDED,
        SupportingFileRejectionCode.EXTRACTED_CHARACTER_LIMIT_EXCEEDED,
    }:
        return SupportingEvidenceLimitError(
            "The supporting file exceeds an approved intake limit.", result=result
        )
    if code is SupportingFileRejectionCode.MALFORMED:
        if media_type == "application/pdf":
            return SupportingEvidenceMalformedPdfError(
                "The supporting PDF is malformed and cannot be read safely.",
                result=result,
            )
        return SupportingEvidenceInvalidTextError(
            "The supporting file is malformed or is not valid plain text.", result=result
        )
    return SupportingEvidenceUnsupportedFileError(
        "This supporting file type is not supported.", result=result
    )


class SupportingDocumentIntakeService:
    def __init__(
        self,
        repository: SQLiteFormalEvidenceRepository,
        *,
        clock: Clock | None = None,
        id_factory: IdFactory | None = None,
    ) -> None:
        self.repository = repository
        self.clock = clock or utc_now
        self.id_factory = id_factory or new_id

    def accept(
        self,
        *,
        lineage: FormalEvidenceLineage,
        request_token: str,
        filename: str,
        raw_bytes: bytes,
        description: str,
        primary_category: DocumentCategory,
        submitter: ReviewerDeclaration,
        additional_categories: tuple[DocumentCategory, ...] = (),
        source_organisation_or_owner: str | None = None,
        covered_period: CoveredPeriod | None = None,
        supersedes_document_id: str | None = None,
    ) -> SupportingDocumentIntakeResult:
        require_lineage(self.repository, lineage)
        safe_filename = _safe_filename(filename)
        content_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        canonical_request = {
            "operation": "supporting-document-intake.v0.1",
            "lineage": lineage.model_dump(mode="json"),
            "safe_filename": safe_filename,
            "content_sha256": content_sha256,
            "byte_size": len(raw_bytes),
            "description": description,
            "primary_category": primary_category.value,
            "additional_categories": [item.value for item in additional_categories],
            "source_organisation_or_owner": source_organisation_or_owner,
            "covered_period": (
                None if covered_period is None else covered_period.model_dump(mode="json")
            ),
            "submitter": submitter.model_dump(mode="json"),
            "supersedes_document_id": supersedes_document_id,
        }
        request = request_identity(request_token, canonical_request)
        replay = self.repository.load_operation_replay(request_token)
        if replay is not None:
            if (
                replay.canonical_request_sha256 != request.canonical_request_sha256
                or replay.formal_lifecycle_id != lineage.formal_lifecycle_id
            ):
                raise SupportingEvidenceRequestConflictError(
                    "This request token was already used for different intake content or metadata."
                )
            if isinstance(replay.record, SupportingDocument):
                return SupportingDocumentIntakeResult(
                    document=replay.record,
                    ingestion_preview=None,
                    ingestion_issue_codes=(),
                    replayed=True,
                    reused_existing_document=False,
                )
            if isinstance(replay.record, SupportingSourceBlob) and (
                replay.record.rejection_code is not None
            ):
                raise _failure_for_rejection(
                    replay.record.rejection_code,
                    media_type=replay.record.detected_media_type,
                    result=replay,
                )
            raise SupportingEvidenceRequestConflictError(
                "This request token does not identify a supporting-document intake."
            )

        inspection = inspect_supporting_file(safe_filename, raw_bytes)
        now = self.clock()
        if inspection.rejection_code is not None:
            # Filename-only/type mismatch rejections are intentionally not bound to
            # the content-derived blob identity: the same safe bytes may later be
            # resubmitted under their correct supported extension.
            if inspection.rejection_code in {
                SupportingFileRejectionCode.UNSUPPORTED_FILE_TYPE,
                SupportingFileRejectionCode.WORD_DOCUMENT,
                SupportingFileRejectionCode.SPREADSHEET,
                SupportingFileRejectionCode.PRESENTATION,
            }:
                raise _failure_for_rejection(
                    inspection.rejection_code,
                    media_type=inspection.media_type,
                )
            rejected = SupportingSourceBlob(
                schema_version=SUPPORTING_SOURCE_BLOB_SCHEMA,
                contract_family=FORMAL_EVIDENCE_FAMILY,
                source_blob_id=f"blob-{inspection.content_sha256}",
                content_sha256=inspection.content_sha256,
                byte_size=len(raw_bytes),
                detected_media_type=inspection.media_type,
                original_filename=inspection.safe_filename,
                state=SourceBlobState.REJECTED,
                rejection_code=inspection.rejection_code,
                created_at=now,
            )
            try:
                existing_rejection = self.repository.load_record(
                    SUPPORTING_SOURCE_BLOB_SCHEMA,
                    rejected.source_blob_id,
                )
            except ArtifactNotFoundError:
                existing_rejection = None
            if (
                isinstance(existing_rejection, SupportingSourceBlob)
                and existing_rejection.state is SourceBlobState.REJECTED
                and existing_rejection.content_sha256 == rejected.content_sha256
                and existing_rejection.byte_size == rejected.byte_size
                and existing_rejection.rejection_code == rejected.rejection_code
            ):
                rejected = existing_rejection
            try:
                stored = self.repository.store_source_blob(
                    rejected,
                    lineage=lineage,
                    request=request,
                    content_bytes=None,
                )
            except FormalEvidenceIdempotencyError as exc:
                raise SupportingEvidenceRequestConflictError(
                    "This request token was already used for different intake content."
                ) from exc
            except FormalEvidenceIntegrityError as exc:
                raise SupportingEvidenceLineageError(
                    "The content-derived rejection history conflicts with "
                    "immutable evidence history."
                ) from exc
            raise _failure_for_rejection(
                inspection.rejection_code,
                media_type=inspection.media_type,
                result=stored,
            )

        if content_sha256 == lineage.source_document_sha256:
            raise SupportingEvidenceDuplicateSourceError(
                "The approved process source is not additional organisational evidence."
            )

        duplicate = self.repository.find_document_by_content(
            formal_lifecycle_id=lineage.formal_lifecycle_id,
            content_sha256=content_sha256,
        )
        if duplicate is not None:
            if supersedes_document_id is not None:
                raise SupportingEvidenceRequestConflictError(
                    "A replacement must contain different immutable source content."
                )
            stored = self.repository.record_document_reuse(
                duplicate,
                request=request,
            )
            return SupportingDocumentIntakeResult(
                document=stored.record,
                ingestion_preview=inspection.ingestion,
                ingestion_issue_codes=inspection.ingestion_issue_codes,
                replayed=stored.replayed,
                reused_existing_document=True,
            )

        current = self.repository.current_documents(lineage.formal_lifecycle_id)
        superseded: SupportingDocument | None = None
        if supersedes_document_id is not None:
            superseded = next(
                (item for item in current if item.document_id == supersedes_document_id),
                None,
            )
            if superseded is None:
                raise SupportingEvidenceLineageError(
                    "A replacement must identify one current same-lifecycle document."
                )
        resulting_count = len(current) + (0 if superseded is not None else 1)
        resulting_bytes = sum(item.byte_size for item in current) + len(raw_bytes)
        if superseded is not None:
            resulting_bytes -= superseded.byte_size
        if resulting_count > MAX_CURRENT_DOCUMENTS:
            raise SupportingEvidenceLimitError(
                "The formal lifecycle already has the maximum number of current documents."
            )
        if resulting_bytes > MAX_FORMAL_LIFECYCLE_BYTES:
            raise SupportingEvidenceLimitError(
                "The formal lifecycle would exceed its current supporting-byte limit."
            )

        document_id = self.id_factory("supporting-document")
        metadata_id = self.id_factory("supporting-metadata")
        blob = SupportingSourceBlob(
            schema_version=SUPPORTING_SOURCE_BLOB_SCHEMA,
            contract_family=FORMAL_EVIDENCE_FAMILY,
            source_blob_id=f"blob-{content_sha256}",
            content_sha256=content_sha256,
            byte_size=len(raw_bytes),
            detected_media_type=inspection.media_type,
            original_filename=inspection.safe_filename,
            state=SourceBlobState.ACCEPTED,
            created_at=now,
        )
        document = SupportingDocument(
            schema_version=SUPPORTING_DOCUMENT_SCHEMA,
            contract_family=FORMAL_EVIDENCE_FAMILY,
            document_id=document_id,
            lineage=lineage,
            source_blob_id=blob.source_blob_id,
            source_blob_sha256=blob.content_sha256,
            original_filename=inspection.safe_filename,
            media_type=inspection.media_type,
            byte_size=len(raw_bytes),
            initial_metadata_revision_id=metadata_id,
            superseded_document=(
                None
                if superseded is None
                else SupportingDocumentReference(
                    lineage=lineage,
                    document_id=superseded.document_id,
                    content_sha256=superseded.source_blob_sha256,
                )
            ),
            submitter=submitter,
            created_at=now,
        )
        metadata = SupportingDocumentMetadataRevision(
            schema_version=SUPPORTING_DOCUMENT_METADATA_REVISION_SCHEMA,
            contract_family=FORMAL_EVIDENCE_FAMILY,
            lineage=lineage,
            document_id=document_id,
            revision_id=metadata_id,
            revision_number=1,
            description=description,
            primary_category=primary_category,
            additional_categories=additional_categories,
            source_organisation_or_owner=source_organisation_or_owner,
            covered_period=covered_period,
            request=request,
            revised_at=now,
        )
        try:
            stored = self.repository.store_document_intake(
                blob,
                document,
                metadata,
                request=request,
                content_bytes=raw_bytes,
            )
        except FormalEvidenceIdempotencyError as exc:
            raise SupportingEvidenceRequestConflictError(
                "This request token was already used for different intake content."
            ) from exc
        except (FormalEvidenceLineageError, FormalEvidenceIntegrityError) as exc:
            raise SupportingEvidenceLineageError(
                "The supporting document no longer matches current immutable history."
            ) from exc
        return SupportingDocumentIntakeResult(
            document=stored.record,
            ingestion_preview=inspection.ingestion,
            ingestion_issue_codes=inspection.ingestion_issue_codes,
            replayed=stored.replayed,
            reused_existing_document=False,
        )
