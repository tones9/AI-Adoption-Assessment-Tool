from ai_adoption_engine.extraction.errors import (
    ExtractionProviderInvalidOutput,
    ExtractionProviderTimeout,
)
from ai_adoption_engine.extraction.service import ProcessExtractionService
from ai_adoption_engine.ingestion.text import ingest_raw_text
from ai_adoption_engine.models.candidate_process import CandidateProcessStatus
from ai_adoption_engine.models.enums import KnowledgeState
from ai_adoption_engine.models.extraction import ExtractionStatus
from tests.fakes.extraction_provider import (
    ScriptedExtractionProvider,
    known,
    raw_chunk,
    raw_step,
)


def test_fake_provider_end_to_end_preserves_unknowns() -> None:
    ingestion = ingest_raw_text(
        "Customer complaint handling\n\nAgent records the complaint."
    )
    assert ingestion.document is not None
    provider = ScriptedExtractionProvider(
        [
            raw_chunk(
                raw_step(
                    local_step_id="step-1",
                    activity="Record complaint",
                    block_id="t-b0002",
                    snippet="Agent records the complaint.",
                ),
                process_name=known(
                    "Customer complaint handling",
                    block_id="t-b0001",
                    snippet="Customer complaint handling",
                ),
            )
        ]
    )
    result = ProcessExtractionService(
        provider, run_id_factory=lambda: "extraction-test"
    ).extract(ingestion.document)

    assert result.status is ExtractionStatus.SUCCESS
    assert result.candidate is not None
    assert (
        result.candidate.candidate_status
        is CandidateProcessStatus.CANDIDATE_UNCONFIRMED
    )
    assert result.candidate.process_description.knowledge_state is KnowledgeState.UNKNOWN
    step = result.candidate.steps[0]
    assert step.description.knowledge_state is KnowledgeState.UNKNOWN
    assert all(
        item.assertion.knowledge_state is KnowledgeState.UNKNOWN
        and item.assertion.value is None
        for item in step.characteristics.criteria
    )


def test_invalid_evidence_is_repaired_once() -> None:
    ingestion = ingest_raw_text("Agent records the complaint.")
    assert ingestion.document is not None
    invalid = raw_chunk(
        raw_step(
            local_step_id="step-1",
            activity="Record complaint",
            block_id="t-b0001",
            snippet="Fabricated activity",
        )
    )
    repaired = raw_chunk(
        raw_step(
            local_step_id="step-1",
            activity="Record complaint",
            block_id="t-b0001",
            snippet="Agent records the complaint.",
        )
    )
    provider = ScriptedExtractionProvider([invalid, repaired])
    result = ProcessExtractionService(provider).extract(ingestion.document)
    assert result.status is ExtractionStatus.SUCCESS
    assert result.candidate is not None
    assert len(provider.requests) == 2
    assert provider.requests[1].attempt == 2
    assert provider.requests[1].repair_feedback == (
        "snippet-not-found",
        "step-activity-unverified",
    )


def test_fabricated_evidence_after_repair_fails_safely() -> None:
    ingestion = ingest_raw_text("Agent records the complaint.")
    assert ingestion.document is not None
    invalid = raw_chunk(
        raw_step(
            local_step_id="step-1",
            activity="Approve refund",
            block_id="t-b0001",
            snippet="Manager approves a refund.",
        )
    )
    provider = ScriptedExtractionProvider([invalid, invalid])
    result = ProcessExtractionService(provider).extract(ingestion.document)
    assert result.status is ExtractionStatus.FAILED
    assert result.candidate is None
    assert any(item.code == "snippet-not-found" for item in result.issues)


def test_provider_timeout_is_sanitised() -> None:
    ingestion = ingest_raw_text("Agent records the complaint.")
    assert ingestion.document is not None
    provider = ScriptedExtractionProvider(
        [ExtractionProviderTimeout("secret source prompt content")]
    )
    result = ProcessExtractionService(provider).extract(ingestion.document)
    assert result.status is ExtractionStatus.FAILED
    assert result.issues[0].code == "provider-timeout"
    assert "secret" not in result.issues[0].message


def test_invalid_structured_output_uses_single_repair_attempt() -> None:
    ingestion = ingest_raw_text("Agent records the complaint.")
    assert ingestion.document is not None
    valid = raw_chunk(
        raw_step(
            local_step_id="step-1",
            activity="Record complaint",
            block_id="t-b0001",
            snippet="Agent records the complaint.",
        )
    )
    provider = ScriptedExtractionProvider(
        [ExtractionProviderInvalidOutput("sensitive malformed output"), valid]
    )
    result = ProcessExtractionService(provider).extract(ingestion.document)
    assert result.status is ExtractionStatus.SUCCESS
    assert result.candidate is not None
    assert [request.attempt for request in provider.requests] == [1, 2]
    assert provider.requests[1].repair_feedback == (
        "provider-invalid-structured-output",
    )
