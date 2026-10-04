"""Approved-review fixtures for deterministic Preliminary Assessment v0.2 tests."""

from datetime import UTC, datetime

from ai_adoption_engine.extraction.service import ProcessExtractionService
from ai_adoption_engine.ingestion.text import ingest_raw_text
from ai_adoption_engine.models.review import ExplicitApproval
from ai_adoption_engine.review.approval import approve_review
from ai_adoption_engine.review.service import ProcessReviewService
from tests.fakes.extraction_provider import ScriptedExtractionProvider, known, raw_chunk, raw_step


FIXED = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)


def approved_review_for(*sentences: str):
    raw = "Test process\n\n" + "\n\n".join(sentences)
    ingestion = ingest_raw_text(raw)
    assert ingestion.document is not None
    steps = tuple(
        raw_step(
            local_step_id=f"step-{index}",
            activity=sentence,
            block_id=f"t-b{index + 2:04d}",
            snippet=sentence,
        )
        for index, sentence in enumerate(sentences)
    )
    extraction = ProcessExtractionService(
        ScriptedExtractionProvider(
            [
                raw_chunk(
                    *steps,
                    process_name=known(
                        "Test process", block_id="t-b0001", snippet="Test process"
                    ),
                )
            ]
        ),
        run_id_factory=lambda: "phase4-v2-fixture",
    ).extract(ingestion.document)
    ids = iter(range(1, 100))
    service = ProcessReviewService(
        clock=lambda: FIXED, id_factory=lambda prefix: f"{prefix}-{next(ids)}"
    )
    review = service.start_review(extraction)
    service.accept_assertion(review, review.process_name, "process.name")
    for step in review.steps:
        service.accept_assertion(
            review, step.activity, f"steps.{step.candidate_step_id}.activity"
        )
    service.accept_step_order(review)
    result = approve_review(
        review,
        ExplicitApproval(
            approval_statement="APPROVE CURRENT-STATE PROCESS",
            approved_at=FIXED,
        ),
    )
    assert result.approved is not None
    return result.approved
