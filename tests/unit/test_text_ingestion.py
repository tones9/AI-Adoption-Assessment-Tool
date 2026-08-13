from ai_adoption_engine.ingestion.text import ingest_raw_text, ingest_text_bytes
from ai_adoption_engine.models.document import IngestionStatus


def test_utf8_text_file_preserves_blocks_and_line_locators() -> None:
    payload = b" First line \r\nsecond line\r\n\r\nFinal line\r\n"
    result = ingest_text_bytes(payload, "sample.txt")
    assert result.status is IngestionStatus.SUCCESS
    assert result.document is not None
    assert result.document.canonical_text == "First line\nsecond line\n\nFinal line"
    assert [block.source_locator for block in result.document.blocks] == [
        "lines 1-2",
        "line 4",
    ]
    assert result.document.source.detected_encoding == "utf-8"


def test_utf8_bom_is_decoded_without_fallback_warning() -> None:
    result = ingest_text_bytes(b"\xef\xbb\xbfHello", "bom.txt")
    assert result.status is IngestionStatus.SUCCESS
    assert result.document is not None
    assert result.document.canonical_text == "Hello"
    assert result.issues == []


def test_non_utf8_encoding_is_inferred_and_warned() -> None:
    payload = "Smart quotes: “approved” and café".encode("cp1252")
    result = ingest_text_bytes(payload, "legacy.txt")
    assert result.status is IngestionStatus.PARTIAL
    assert result.document is not None
    assert "approved" in result.document.canonical_text
    assert result.document.source.detected_encoding != "utf-8"
    assert result.issues[0].code == "text-encoding-inferred"


def test_binary_text_fails_cleanly() -> None:
    result = ingest_text_bytes(b"\x00\x01\x02", "binary.txt")
    assert result.status is IngestionStatus.FAILED
    assert result.document is None
    assert result.issues[0].code == "text-decode-failed"


def test_empty_raw_text_fails_cleanly() -> None:
    result = ingest_raw_text(" \r\n\t")
    assert result.status is IngestionStatus.FAILED
    assert result.issues[0].code == "empty-text"


def test_identical_raw_input_has_stable_identifiers_and_offsets() -> None:
    first = ingest_raw_text("Alpha\r\n\r\nBeta")
    second = ingest_raw_text("Alpha\r\n\r\nBeta")
    assert first.model_dump(mode="json") == second.model_dump(mode="json")

