from ai_adoption_engine.ingestion.pdf import ingest_pdf_bytes
from ai_adoption_engine.models.document import IngestionStatus


def test_text_native_pdf_preserves_page_order_and_metadata(pdf_fixture_bytes: bytes) -> None:
    result = ingest_pdf_bytes(pdf_fixture_bytes, "traceable.pdf")
    assert result.status is IngestionStatus.PARTIAL
    assert result.document is not None
    assert result.document.metadata.title == "Traceable Phase 2 Fixture"
    assert result.document.metadata.page_count == 3
    assert [block.page_number for block in result.document.blocks] == [1, 2, 3]
    assert result.document.blocks[1].has_extractable_text is False
    assert result.document.blocks[1].extracted_text == ""
    assert result.issues[0].code == "pdf-page-no-extractable-text"
    assert result.issues[0].page_number == 2
    assert "OCR is outside Phase 2 scope" in result.issues[0].message


def test_pdf_offsets_and_ids_are_stable(pdf_fixture_bytes: bytes) -> None:
    first = ingest_pdf_bytes(pdf_fixture_bytes, "traceable.pdf")
    second = ingest_pdf_bytes(pdf_fixture_bytes, "traceable.pdf")
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.document is not None
    for block in first.document.blocks:
        assert (
            first.document.canonical_text[
                block.document_start_offset : block.document_end_offset
            ]
            == block.extracted_text
        )


def test_invalid_pdf_fails_cleanly() -> None:
    result = ingest_pdf_bytes(b"not a pdf", "fake.pdf")
    assert result.status is IngestionStatus.FAILED
    assert result.issues[0].code == "invalid-pdf"


def test_encrypted_pdf_is_rejected(encrypted_pdf_bytes: bytes) -> None:
    result = ingest_pdf_bytes(encrypted_pdf_bytes, "encrypted.pdf")
    assert result.status is IngestionStatus.FAILED
    assert result.issues[0].code == "encrypted-pdf"


def test_page_extraction_error_is_partial_and_preserves_page_position(
    monkeypatch, pdf_fixture_bytes: bytes
) -> None:
    from pypdf._page import PageObject

    original = PageObject.extract_text
    calls = 0

    def fail_second_page(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("synthetic page failure")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(PageObject, "extract_text", fail_second_page)
    result = ingest_pdf_bytes(pdf_fixture_bytes, "traceable.pdf")
    assert result.status is IngestionStatus.PARTIAL
    assert result.document is not None
    assert [block.page_number for block in result.document.blocks] == [1, 2, 3]
    assert result.issues[0].code == "pdf-page-extraction-failed"
    assert result.issues[0].page_number == 2
