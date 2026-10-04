from __future__ import annotations

import hashlib
import sqlite3
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from ai_adoption_engine.models.formal_evidence import (
    MAX_EXTRACTED_CHARACTERS,
    MAX_PDF_PAGES,
    MAX_SUPPORTING_FILE_BYTES,
    DocumentCategory,
    SupportingFileRejectionCode,
)
from ai_adoption_engine.supporting_evidence import intake as intake_module
from ai_adoption_engine.supporting_evidence.errors import (
    SupportingEvidenceDuplicateSourceError,
    SupportingEvidenceLimitError,
    SupportingEvidenceUnsupportedFileError,
)
from ai_adoption_engine.supporting_evidence.intake import (
    SupportingDocumentIntakeService,
    inspect_supporting_file,
)
from tests.integration.test_formal_evidence_persistence import _prepare, _reviewer
from tests.integration.test_supporting_evidence_slice3_services import StableIds


def _pdf_bytes(*, text: str | None = None, active: bool = False, encrypted: bool = False) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    if text is not None:
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        resources = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {NameObject("/F1"): writer._add_object(font)}
                )
            }
        )
        page[NameObject("/Resources")] = resources
        stream = DecodedStreamObject()
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream.set_data(f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    if active:
        writer.add_js("app.alert('unsafe')")
    if encrypted:
        writer.encrypt("secret")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_valid_plain_text_and_text_native_pdf_are_accepted() -> None:
    text = inspect_supporting_file("safe.txt", b"Monthly volume is 100.")
    pdf = inspect_supporting_file("safe.pdf", _pdf_bytes(text="Monthly volume is 100."))
    assert text.rejection_code is None
    assert text.ingestion is not None
    assert text.ingestion.canonical_text == "Monthly volume is 100."
    assert pdf.rejection_code is None
    assert pdf.ingestion is not None
    assert pdf.ingestion.metadata.page_count == 1
    assert pdf.ingestion.blocks[0].page_number == 1


@pytest.mark.parametrize(
    ("filename", "payload", "code"),
    [
        ("wrong.txt", b"%PDF-1.7 fake", SupportingFileRejectionCode.UNSUPPORTED_FILE_TYPE),
        ("bad.pdf", b"not-a-pdf", SupportingFileRejectionCode.MALFORMED),
        ("binary.txt", b"hello\x00world", SupportingFileRejectionCode.MALFORMED),
        ("archive.txt", b"PK\x03\x04payload", SupportingFileRejectionCode.ARCHIVE),
        ("program.txt", b"MZpayload", SupportingFileRejectionCode.EXECUTABLE),
        ("report.docx", b"payload", SupportingFileRejectionCode.WORD_DOCUMENT),
    ],
)
def test_signature_extension_and_binary_checks(filename: str, payload: bytes, code) -> None:
    assert inspect_supporting_file(filename, payload).rejection_code is code


def test_pdf_safety_encryption_scanning_and_limits() -> None:
    assert inspect_supporting_file(
        "active.pdf", _pdf_bytes(text="safe text", active=True)
    ).rejection_code is SupportingFileRejectionCode.ACTIVE_CONTENT
    assert inspect_supporting_file(
        "encrypted.pdf", _pdf_bytes(text="safe text", encrypted=True)
    ).rejection_code is SupportingFileRejectionCode.ENCRYPTED
    assert inspect_supporting_file(
        "scanned.pdf", _pdf_bytes()
    ).rejection_code is SupportingFileRejectionCode.SCANNED_OR_NO_TEXT

    writer = PdfWriter()
    for _ in range(MAX_PDF_PAGES + 1):
        writer.add_blank_page(width=1, height=1)
    output = BytesIO()
    writer.write(output)
    assert inspect_supporting_file(
        "too-many.pdf", output.getvalue()
    ).rejection_code is SupportingFileRejectionCode.PDF_PAGE_LIMIT_EXCEEDED

    assert inspect_supporting_file(
        "too-long.txt", b"a" * (MAX_EXTRACTED_CHARACTERS + 1)
    ).rejection_code is SupportingFileRejectionCode.EXTRACTED_CHARACTER_LIMIT_EXCEEDED
    assert inspect_supporting_file(
        "too-large.txt", b"a" * (MAX_SUPPORTING_FILE_BYTES + 1)
    ).rejection_code is SupportingFileRejectionCode.FILE_TOO_LARGE


def test_rejected_bytes_are_never_retained_or_contextualized(tmp_path: Path) -> None:
    context = _prepare(tmp_path)
    service = SupportingDocumentIntakeService(
        context.repository, id_factory=StableIds()
    )
    payload = b"hello\x00world"
    with pytest.raises(Exception) as failure:
        service.accept(
            lineage=context.lineage,
            request_token="binary",
            filename="binary.txt",
            raw_bytes=payload,
            description="Not usable",
            primary_category=DocumentCategory.OTHER_ORGANISATIONAL_EVIDENCE,
            submitter=_reviewer(),
        )
    assert getattr(failure.value, "code", None) == "invalid-text"
    with pytest.raises(Exception) as repeated:
        service.accept(
            lineage=context.lineage,
            request_token="binary-again",
            filename="renamed-binary.txt",
            raw_bytes=payload,
            description="Still not usable",
            primary_category=DocumentCategory.OTHER_ORGANISATIONAL_EVIDENCE,
            submitter=_reviewer(),
        )
    assert getattr(repeated.value, "code", None) == "invalid-text"
    digest = hashlib.sha256(payload).hexdigest()
    connection = sqlite3.connect(context.path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM preliminary_supporting_source_blob_bytes"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM preliminary_supporting_documents"
        ).fetchone()[0] == 0
        assert connection.execute(
            """SELECT rejection_code FROM preliminary_supporting_source_blobs
               WHERE content_sha256 = ?""",
            (digest,),
        ).fetchone() == (SupportingFileRejectionCode.MALFORMED.value,)
    finally:
        connection.close()


def test_source_process_duplicate_and_lifecycle_limits(tmp_path: Path, monkeypatch) -> None:
    context = _prepare(tmp_path)
    service = SupportingDocumentIntakeService(
        context.repository, id_factory=StableIds()
    )
    payload = (
        b"Complaint handling\n\n"
        b"Agent records the complaint.\n\n"
        b"Manager reviews the complaint."
    )
    assert hashlib.sha256(payload).hexdigest() == context.lineage.source_document_sha256
    with pytest.raises(SupportingEvidenceDuplicateSourceError):
        service.accept(
            lineage=context.lineage,
            request_token="source-copy",
            filename="source.txt",
            raw_bytes=payload,
            description="Source copy",
            primary_category=DocumentCategory.OTHER_ORGANISATIONAL_EVIDENCE,
            submitter=_reviewer(),
        )

    service.accept(
        lineage=context.lineage,
        request_token="first",
        filename="first.txt",
        raw_bytes=b"first evidence",
        description="First",
        primary_category=DocumentCategory.OTHER_ORGANISATIONAL_EVIDENCE,
        submitter=_reviewer(),
    )
    monkeypatch.setattr(intake_module, "MAX_CURRENT_DOCUMENTS", 1)
    with pytest.raises(SupportingEvidenceLimitError):
        service.accept(
            lineage=context.lineage,
            request_token="count-limit",
            filename="second.txt",
            raw_bytes=b"second evidence",
            description="Second",
            primary_category=DocumentCategory.OTHER_ORGANISATIONAL_EVIDENCE,
            submitter=_reviewer(),
        )
    monkeypatch.setattr(intake_module, "MAX_CURRENT_DOCUMENTS", 20)
    monkeypatch.setattr(intake_module, "MAX_FORMAL_LIFECYCLE_BYTES", 1)
    with pytest.raises(SupportingEvidenceLimitError):
        service.accept(
            lineage=context.lineage,
            request_token="byte-limit",
            filename="third.txt",
            raw_bytes=b"third evidence",
            description="Third",
            primary_category=DocumentCategory.OTHER_ORGANISATIONAL_EVIDENCE,
            submitter=_reviewer(),
        )


def test_filename_is_metadata_only_and_wrong_extension_is_not_blob_poisoning(
    tmp_path: Path,
) -> None:
    context = _prepare(tmp_path)
    service = SupportingDocumentIntakeService(
        context.repository, id_factory=StableIds()
    )
    payload = b"safe evidence"
    with pytest.raises(SupportingEvidenceUnsupportedFileError):
        service.accept(
            lineage=context.lineage,
            request_token="wrong-extension",
            filename="../../safe.docx",
            raw_bytes=payload,
            description="Wrong extension",
            primary_category=DocumentCategory.OTHER_ORGANISATIONAL_EVIDENCE,
            submitter=_reviewer(),
        )
    accepted = service.accept(
        lineage=context.lineage,
        request_token="right-extension",
        filename="../../safe.txt",
        raw_bytes=payload,
        description="Corrected extension",
        primary_category=DocumentCategory.OTHER_ORGANISATIONAL_EVIDENCE,
        submitter=_reviewer(),
    )
    assert accepted.document.original_filename == "safe.txt"
