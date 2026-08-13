"""Deterministic Phase 4 candidate and service fixtures."""

from datetime import UTC, datetime

from ai_adoption_engine.extraction.service import ProcessExtractionService
from ai_adoption_engine.ingestion.text import ingest_raw_text
from ai_adoption_engine.models.extraction import CandidateExtractionResult
from ai_adoption_engine.review.service import ProcessReviewService
from tests.fakes.extraction_provider import ScriptedExtractionProvider, known, raw_chunk, raw_step


FIXED_TIME = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)


def candidate_result() -> CandidateExtractionResult:
    ingestion = ingest_raw_text(
        "Complaint handling\n\n"
        "Agent records the complaint.\n\n"
        "Manager reviews the complaint."
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
                process_name=known(
                    "Complaint handling",
                    block_id="t-b0001",
                    snippet="Complaint handling",
                ),
            )
        ]
    )
    return ProcessExtractionService(
        provider, run_id_factory=lambda: "phase4-fixture"
    ).extract(ingestion.document)


def review_service() -> ProcessReviewService:
    counter = iter(range(1, 1000))
    return ProcessReviewService(
        clock=lambda: FIXED_TIME,
        id_factory=lambda prefix: f"{prefix}-{next(counter)}",
    )
