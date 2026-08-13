from ai_adoption_engine.extraction.service import ProcessExtractionService
from ai_adoption_engine.ingestion.text import ingest_raw_text
from ai_adoption_engine.models.extraction import ExtractionStatus
from tests.fakes.extraction_provider import (
    ScriptedExtractionProvider,
    raw_chunk,
    raw_step,
)


def test_ingested_document_to_unconfirmed_candidate_process() -> None:
    ingestion = ingest_raw_text(
        "Complaint handling\n\nAgent records the complaint.\n\nManager reviews the complaint."
    )
    assert ingestion.document is not None
    provider = ScriptedExtractionProvider(
        [
            raw_chunk(
                raw_step(
                    local_step_id="record",
                    activity="Record complaint",
                    block_id="t-b0002",
                    snippet="Agent records the complaint.",
                ),
                raw_step(
                    local_step_id="review",
                    activity="Review complaint",
                    block_id="t-b0003",
                    snippet="Manager reviews the complaint.",
                ),
            )
        ]
    )
    result = ProcessExtractionService(
        provider, run_id_factory=lambda: "extraction-integration-fixture"
    ).extract(ingestion.document)
    assert result.status is ExtractionStatus.SUCCESS
    assert result.candidate is not None
    assert result.candidate.source_document_id == ingestion.document.document_id
    assert [item.sequence for item in result.candidate.steps] == [1, 2]
    assert all(
        reference.document_id == ingestion.document.document_id
        for step in result.candidate.steps
        for reference in step.activity.evidence
    )
