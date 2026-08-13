from ai_adoption_engine.extraction.chunking import ChunkingConfig, plan_chunks
from ai_adoption_engine.ingestion.text import ingest_raw_text


def test_chunking_preserves_block_identity_and_overlap() -> None:
    result = ingest_raw_text("First block\n\nSecond block\n\nThird block")
    assert result.document is not None
    chunks = plan_chunks(
        result.document,
        ChunkingConfig(max_characters=100, max_non_empty_blocks=2, overlap_blocks=1),
    )
    assert len(chunks) == 2
    assert chunks[0].block_ids == ("t-b0001", "t-b0002")
    assert chunks[1].block_ids == ("t-b0002", "t-b0003")


def test_oversized_block_slices_reconstruct_original_text() -> None:
    result = ingest_raw_text("alpha beta gamma delta")
    assert result.document is not None
    chunks = plan_chunks(
        result.document,
        ChunkingConfig(max_characters=8, max_non_empty_blocks=2, overlap_blocks=1),
    )
    slices = [item for chunk in chunks for item in chunk.slices]
    assert len(slices) > 1
    assert {item.block_id for item in slices} == {"t-b0001"}
    assert "".join(item.text for item in slices) == "alpha beta gamma delta"
    assert [item.block_start_offset for item in slices][0] == 0
    assert slices[-1].block_end_offset == len("alpha beta gamma delta")
