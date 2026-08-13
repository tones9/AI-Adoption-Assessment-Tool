import pytest

from ai_adoption_engine.extraction.chunking import plan_chunks
from ai_adoption_engine.extraction.evidence import EvidenceResolver
from ai_adoption_engine.ingestion.text import ingest_raw_text
from ai_adoption_engine.models.extraction import RawEvidencePointer


def _resolver(text: str) -> EvidenceResolver:
    result = ingest_raw_text(text)
    assert result.document is not None
    return EvidenceResolver(result.document, plan_chunks(result.document)[0])


def test_application_resolves_trusted_offsets_from_exact_snippet() -> None:
    resolver = _resolver("Agent records the complaint.")
    reference = resolver.resolve_pointer(
        RawEvidencePointer(
            block_id="t-b0001",
            exact_snippet="records the complaint",
        )
    )
    assert reference.block_start_offset == len("Agent ")
    assert reference.block_end_offset == len("Agent records the complaint")
    assert reference.document_start_offset == reference.block_start_offset
    assert reference.exact_snippet == "records the complaint"


def test_fabricated_snippet_is_rejected() -> None:
    resolver = _resolver("Agent records the complaint.")
    with pytest.raises(ValueError, match="snippet-not-found"):
        resolver.resolve_pointer(
            RawEvidencePointer(
                block_id="t-b0001",
                exact_snippet="Manager approves the refund",
            )
        )


def test_duplicate_snippet_requires_disambiguation() -> None:
    resolver = _resolver("review then review again")
    with pytest.raises(ValueError, match="ambiguous-snippet"):
        resolver.resolve_pointer(
            RawEvidencePointer(block_id="t-b0001", exact_snippet="review")
        )
    second = resolver.resolve_pointer(
        RawEvidencePointer(
            block_id="t-b0001", exact_snippet="review", occurrence=2
        )
    )
    assert second.block_start_offset == len("review then ")


def test_provider_cannot_supply_trusted_offsets() -> None:
    assert "block_start_offset" not in RawEvidencePointer.model_fields
    assert "document_start_offset" not in RawEvidencePointer.model_fields
