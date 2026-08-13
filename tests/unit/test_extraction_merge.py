from ai_adoption_engine.extraction.chunking import ChunkingConfig
from ai_adoption_engine.extraction.service import ProcessExtractionService
from ai_adoption_engine.ingestion.text import ingest_raw_text
from ai_adoption_engine.models.extraction import ExtractionStatus
from tests.fakes.extraction_provider import (
    ScriptedExtractionProvider,
    raw_chunk,
    raw_step,
)


def test_overlap_duplicate_is_removed_and_source_order_is_preserved() -> None:
    ingestion = ingest_raw_text("Receive request\n\nReview request\n\nSend response")
    assert ingestion.document is not None
    provider = ScriptedExtractionProvider(
        [
            raw_chunk(
                raw_step(
                    local_step_id="one",
                    activity="Receive request",
                    block_id="t-b0001",
                    snippet="Receive request",
                ),
                raw_step(
                    local_step_id="two",
                    activity="Review request",
                    block_id="t-b0002",
                    snippet="Review request",
                ),
            ),
            raw_chunk(
                raw_step(
                    local_step_id="duplicate-two",
                    activity="Review request",
                    block_id="t-b0002",
                    snippet="Review request",
                ),
                raw_step(
                    local_step_id="three",
                    activity="Send response",
                    block_id="t-b0003",
                    snippet="Send response",
                ),
            ),
        ]
    )
    result = ProcessExtractionService(
        provider,
        chunking=ChunkingConfig(
            max_characters=100, max_non_empty_blocks=2, overlap_blocks=1
        ),
    ).extract(ingestion.document)
    assert result.status is ExtractionStatus.SUCCESS
    assert result.candidate is not None
    assert [step.activity.value for step in result.candidate.steps] == [
        "Receive request",
        "Review request",
        "Send response",
    ]
    assert any(item.code == "duplicate-step-merged" for item in result.issues)


def test_similarly_named_steps_without_shared_evidence_are_retained() -> None:
    ingestion = ingest_raw_text("Review request\n\nReview request")
    assert ingestion.document is not None
    provider = ScriptedExtractionProvider(
        [
            raw_chunk(
                raw_step(
                    local_step_id="one",
                    activity="Review request",
                    block_id="t-b0001",
                    snippet="Review request",
                ),
                raw_step(
                    local_step_id="two",
                    activity="Review request",
                    block_id="t-b0002",
                    snippet="Review request",
                ),
            )
        ]
    )
    result = ProcessExtractionService(provider).extract(ingestion.document)
    assert result.candidate is not None
    assert len(result.candidate.steps) == 2
    assert any(item.code == "possible-duplicate-step" for item in result.issues)
