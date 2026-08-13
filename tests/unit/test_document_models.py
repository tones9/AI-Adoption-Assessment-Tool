import pytest
from pydantic import ValidationError

from ai_adoption_engine.models.document import IngestedDocument


def test_block_offsets_resolve_exact_text() -> None:
    from ai_adoption_engine.ingestion.text import ingest_raw_text

    result = ingest_raw_text("Alpha\n\nBeta")
    assert result.document is not None
    for block in result.document.blocks:
        assert (
            result.document.canonical_text[
                block.document_start_offset : block.document_end_offset
            ]
            == block.extracted_text
        )


def test_document_rejects_offsets_that_do_not_resolve() -> None:
    from ai_adoption_engine.ingestion.text import ingest_raw_text

    result = ingest_raw_text("Alpha\n\nBeta")
    assert result.document is not None
    raw = result.document.model_dump(mode="json")
    raw["blocks"][1]["document_start_offset"] -= 1
    with pytest.raises(ValidationError, match="offsets do not resolve"):
        IngestedDocument.model_validate(raw)


def test_offsets_count_unicode_code_points() -> None:
    from ai_adoption_engine.ingestion.text import ingest_raw_text

    result = ingest_raw_text("café\n\nRésumé")
    assert result.document is not None
    assert result.document.blocks[0].document_end_offset == 4
    assert result.document.blocks[1].document_start_offset == 6
    assert result.document.canonical_text[6:12] == "Résumé"
