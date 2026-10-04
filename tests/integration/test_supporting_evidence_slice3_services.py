from __future__ import annotations

import sqlite3
import shutil
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai_adoption_engine.extraction.errors import ExtractionProviderTimeout
from ai_adoption_engine.ingestion.text import ingest_text_bytes
from ai_adoption_engine.models.document import (
    IngestionIssue,
    IngestionResult,
    IngestionStatus,
    IssueSeverity,
)
from ai_adoption_engine.models.formal_evidence import (
    FORMAL_EVIDENCE_FAMILY,
    AttemptStatus,
    DocumentCategory,
    EvidenceClassification,
    FormalEvidenceLineage,
    ReviewerDeclaration,
)
from ai_adoption_engine.models.preliminary_assessment import AssessmentJourney
from ai_adoption_engine.models.preliminary_journey import ApprovedReviewArtifactPin
from ai_adoption_engine.persistence.formal_evidence import (
    SQLiteFormalEvidenceRepository,
)
from ai_adoption_engine.persistence.preliminary import SQLitePreliminaryJourneyStore
from ai_adoption_engine.persistence.sqlite import SQLiteAssessmentRepository
from ai_adoption_engine.persistence.workspace_protection import (
    FrozenEvaluationWorkspaceError,
)
from ai_adoption_engine.supporting_evidence.errors import (
    SupportingEvidenceCitationError,
    SupportingEvidenceConcurrentAttemptError,
    SupportingEvidenceConsentRequiredError,
    SupportingEvidenceFinalizationError,
    SupportingEvidenceInterruptedError,
    SupportingEvidenceProviderFailure,
    SupportingEvidenceRequestConflictError,
)
from ai_adoption_engine.supporting_evidence.extraction import (
    SupportingEvidenceExtractionService,
)
from ai_adoption_engine.supporting_evidence.ingestion import (
    SupportingDocumentIngestionService,
)
from ai_adoption_engine.supporting_evidence.intake import (
    SupportingDocumentIntakeService,
)
from ai_adoption_engine.supporting_evidence.provider import (
    SUPPORTING_EVIDENCE_PROVIDER_SCHEMA,
    RawSupportingCitation,
    RawSupportingEvidenceBatch,
    RawSupportingEvidenceItem,
    ScriptedSupportingEvidenceProvider,
    SupportingEvidenceProviderInterrupted,
)
from ai_adoption_engine.preliminary.formal import PreliminaryFormalStartService
from ai_adoption_engine.preliminary.journey import PreliminaryJourneyService
from ai_adoption_engine.workspace.models import ArtifactType, ExecutionMode, WorkflowStage
from tests.integration.test_formal_evidence_persistence import _prepare
from tests.fakes.review import approved_review


NOW = datetime(2026, 10, 4, 15, 0, tzinfo=UTC)


class StableIds:
    def __init__(self) -> None:
        self.counts: dict[str, int] = defaultdict(int)

    def __call__(self, prefix: str) -> str:
        self.counts[prefix] += 1
        return f"slice3-{prefix}-{self.counts[prefix]}"


class PrefixedIds(StableIds):
    def __init__(self, namespace: str) -> None:
        super().__init__()
        self.namespace = namespace

    def __call__(self, prefix: str) -> str:
        return f"{self.namespace}-{super().__call__(prefix)}"


def _reviewer() -> ReviewerDeclaration:
    return ReviewerDeclaration(
        schema_version="reviewer-declaration.v0.1",
        contract_family=FORMAL_EVIDENCE_FAMILY,
        reviewer_display_name="Alex Reviewer",
        declared_organisational_role="Process owner",
        identity_and_authority_locally_declared_not_authenticated=True,
        declared_at=NOW,
    )


def _accept(context, ids: StableIds, *, token: str = "intake", content: bytes = b"Monthly volume is 100."):
    service = SupportingDocumentIntakeService(
        context.repository,
        clock=lambda: NOW,
        id_factory=ids,
    )
    return service.accept(
        lineage=context.lineage,
        request_token=token,
        filename="evidence.txt",
        raw_bytes=content,
        description="Monthly operational report",
        primary_category=DocumentCategory.PROCESS_VOLUMES_AND_FREQUENCY,
        submitter=_reviewer(),
    )


def _ingest(context, ids: StableIds, document_id: str, *, token: str = "ingest"):
    service = SupportingDocumentIngestionService(
        context.repository,
        clock=lambda: NOW,
        id_factory=ids,
    )
    return service, service.ingest(
        lineage=context.lineage,
        document_id=document_id,
        request_token=token,
    )


def _batch(document_id: str, block_id: str, activity_id: str, excerpt: str = "Monthly volume is 100."):
    return RawSupportingEvidenceBatch(
        schema_version=SUPPORTING_EVIDENCE_PROVIDER_SCHEMA,
        items=(
            RawSupportingEvidenceItem(
                proposed_claim="Monthly volume is 100.",
                proposed_classification=EvidenceClassification.DOCUMENTED_FACT,
                primary_citation=RawSupportingCitation(
                    document_id=document_id,
                    block_id=block_id,
                    exact_excerpt=excerpt,
                ),
                proposed_category=DocumentCategory.PROCESS_VOLUMES_AND_FREQUENCY,
                suggested_activity_ids=(activity_id,),
                ambiguity_indicated=False,
                conflict_indicated=False,
                relevance_explanation="May inform the evidence review.",
                extraction_confidence=0.9,
            ),
        ),
    )


def _prepared_document(tmp_path: Path):
    context = _prepare(tmp_path)
    ids = StableIds()
    accepted = _accept(context, ids)
    ingestion_service, ingested = _ingest(context, ids, accepted.document.document_id)
    assert ingested.ingested_document is not None
    return context, ids, accepted, ingestion_service, ingested


def _create_second_lineage(path: Path) -> tuple[SQLiteFormalEvidenceRepository, FormalEvidenceLineage]:
    ids = PrefixedIds("second")
    assessment_repository = SQLiteAssessmentRepository(
        path, clock=lambda: NOW, id_factory=ids
    )
    assessment = assessment_repository.create_assessment(
        "Second source assessment", ExecutionMode.OFFLINE_DEMO
    )
    approved = approved_review()
    review_ref = assessment_repository.save_artifact_and_advance(
        assessment.assessment_id,
        ArtifactType.REVIEW_SESSION,
        approved.review,
        artifact_schema_version="phase4-v0.1",
        stage=WorkflowStage.IN_REVIEW,
    )
    approved_ref = assessment_repository.save_artifact_and_advance(
        assessment.assessment_id,
        ArtifactType.APPROVED_REVIEW,
        approved,
        artifact_schema_version="phase4-v0.1",
        stage=WorkflowStage.APPROVED,
        parent_artifact_id=review_ref.artifact_id,
    )
    stored = assessment_repository.load_artifact(approved_ref.artifact_id)
    pin = ApprovedReviewArtifactPin(
        assessment_id=assessment.assessment_id,
        artifact_id=approved_ref.artifact_id,
        artifact_revision=approved_ref.artifact_revision,
        artifact_schema_version=stored.artifact_schema_version,
        payload_sha256=stored.payload_sha256,
    )
    journey_store = SQLitePreliminaryJourneyStore(path, clock=lambda: NOW)
    journey_service = PreliminaryJourneyService(
        journey_store, clock=lambda: NOW, id_factory=ids
    )
    journey = journey_service.create_or_reuse_journey(pin).journey
    route = journey_service.select_route(
        journey.journey_id,
        AssessmentJourney.ORGANISATIONAL_ASSESSMENT,
        request_token="second-formal-route",
        expected_latest_sequence=1,
    ).effective_route_event
    formal = PreliminaryFormalStartService(
        journey_store, clock=lambda: NOW, id_factory=ids
    ).start_formal_lifecycle(
        journey.journey_id,
        request_token="second-formal-start",
        route_choice_event_id=route.event_id,
        route_choice_event_sequence=route.event_sequence,
    ).lifecycle
    source_hash = formal.source.source_document_id.removeprefix("doc-")
    lineage = FormalEvidenceLineage(
        formal_lifecycle_schema=formal.schema_version,
        formal_lifecycle_id=formal.formal_lifecycle_id,
        journey_id=formal.journey_id,
        source_assessment_id=formal.source.source_assessment_id,
        approved_review_artifact_id=formal.source.approved_review_artifact_id,
        approved_review_schema_version=stored.artifact_schema_version,
        approved_review_revision=approved_ref.artifact_revision,
        approved_review_payload_sha256=formal.source.approved_review_payload_sha256,
        source_document_id=formal.source.source_document_id,
        source_document_sha256=source_hash,
        validated_process_id=formal.source.validated_process_id,
        validated_process_fingerprint=formal.source.validated_process_fingerprint,
    )
    return SQLiteFormalEvidenceRepository(path, clock=lambda: NOW), lineage


def test_text_intake_ingestion_extraction_and_exact_replay(tmp_path: Path) -> None:
    context, ids, accepted, _, ingested = _prepared_document(tmp_path)
    block = ingested.ingested_document.blocks[0]
    provider = ScriptedSupportingEvidenceProvider(
        (_batch(accepted.document.document_id, block.block_id, context.activity_id),)
    )
    service = SupportingEvidenceExtractionService(
        context.repository,
        provider,
        clock=lambda: NOW,
        id_factory=ids,
    )

    result = service.extract(
        lineage=context.lineage,
        document_id=accepted.document.document_id,
        ingestion_attempt_id=ingested.attempt.attempt_id,
        request_token="extract",
    )
    replay = service.extract(
        lineage=context.lineage,
        document_id=accepted.document.document_id,
        ingestion_attempt_id=ingested.attempt.attempt_id,
        request_token="extract",
    )

    assert result.attempt.status is AttemptStatus.SUCCEEDED
    assert replay.replayed is True
    assert replay.attempt == result.attempt
    assert replay.proposals == result.proposals
    assert len(provider.calls) == 1
    proposal = result.proposals[0]
    assert proposal.primary_source_span.exact_excerpt == block.extracted_text
    assert proposal.primary_source_span.block_character_start == 0
    assert proposal.primary_source_span.document_character_start == 0
    assert proposal.primary_source_span.locator == block.source_locator
    assert proposal.primary_source_span.line_start == block.line_start
    assert proposal.proposal_id is not None
    assert context.repository.load_source_bytes(accepted.document.source_blob_id) == b"Monthly volume is 100."
    assert ingested.attempt.parsed_document is not None
    assert ingested.attempt.parsed_document.extracted_character_count == len(block.extracted_text)


def test_ingestion_maps_partial_failed_replay_abandonment_and_retry(tmp_path: Path) -> None:
    context = _prepare(tmp_path)
    ids = StableIds()
    accepted = _accept(context, ids)
    calls = 0

    def partial_parser(content: bytes, filename: str) -> IngestionResult:
        nonlocal calls
        calls += 1
        parsed = ingest_text_bytes(content, filename)
        return parsed.model_copy(
            update={
                "status": IngestionStatus.PARTIAL,
                "issues": [
                    IngestionIssue(
                        severity=IssueSeverity.WARNING,
                        code="non-fatal-section",
                        message="One optional section could not be interpreted.",
                    )
                ],
            }
        )

    partial_service = SupportingDocumentIngestionService(
        context.repository,
        text_parser=partial_parser,
        clock=lambda: NOW,
        id_factory=ids,
    )
    partial = partial_service.ingest(
        lineage=context.lineage,
        document_id=accepted.document.document_id,
        request_token="partial-ingestion",
    )
    replay = partial_service.ingest(
        lineage=context.lineage,
        document_id=accepted.document.document_id,
        request_token="partial-ingestion",
    )
    assert partial.attempt.status is AttemptStatus.PARTIAL
    assert partial.attempt.issue_codes == ("non-fatal-section",)
    assert partial.attempt.parsed_document is not None
    assert replay.replayed is True
    assert calls == 1

    failed_document = _accept(
        context, ids, token="failed-intake", content=b"Different source."
    )

    def failed_parser(content: bytes, filename: str) -> IngestionResult:
        return IngestionResult(
            status=IngestionStatus.FAILED,
            issues=[
                IngestionIssue(
                    severity=IssueSeverity.ERROR,
                    code="unusable-source",
                    message="The source is unusable.",
                )
            ],
        )

    failed_service = SupportingDocumentIngestionService(
        context.repository,
        text_parser=failed_parser,
        clock=lambda: NOW,
        id_factory=ids,
    )
    failed = failed_service.ingest(
        lineage=context.lineage,
        document_id=failed_document.document.document_id,
        request_token="failed-ingestion",
    )
    assert failed.attempt.status is AttemptStatus.FAILED
    assert failed.attempt.parsed_document is None

    retry = SupportingDocumentIngestionService(
        context.repository,
        clock=lambda: NOW,
        id_factory=ids,
    ).ingest(
        lineage=context.lineage,
        document_id=failed_document.document.document_id,
        request_token="ingestion-retry",
        predecessor_attempt_id=failed.attempt.attempt_id,
    )
    assert retry.attempt.status is AttemptStatus.SUCCEEDED
    assert retry.attempt.attempt_number == 2
    assert retry.attempt.predecessor_attempt_id == failed.attempt.attempt_id

    abandoned_document = _accept(
        context, ids, token="abandon-intake", content=b"Third source."
    )
    abandon_service = SupportingDocumentIngestionService(
        context.repository, clock=lambda: NOW, id_factory=ids
    )
    pending = abandon_service.begin(
        lineage=context.lineage,
        document_id=abandoned_document.document.document_id,
        request_token="started-ingestion",
    )
    with pytest.raises(SupportingEvidenceInterruptedError):
        abandon_service.begin(
            lineage=context.lineage,
            document_id=abandoned_document.document.document_id,
            request_token="started-ingestion",
        )
    abandoned = abandon_service.abandon(pending, abandonment_token="abandon-ingestion")
    assert abandoned.attempt.status is AttemptStatus.ABANDONED


def test_intake_duplicate_replacement_replay_and_token_conflict(tmp_path: Path) -> None:
    context = _prepare(tmp_path)
    ids = StableIds()
    first = _accept(context, ids)
    replay = _accept(context, ids)
    reused = _accept(context, ids, token="duplicate")
    assert replay.replayed is True
    assert reused.reused_existing_document is True
    assert reused.document == first.document

    with pytest.raises(SupportingEvidenceRequestConflictError):
        _accept(context, ids, token="intake", content=b"Different evidence.")

    replacement = SupportingDocumentIntakeService(
        context.repository, clock=lambda: NOW, id_factory=ids
    ).accept(
        lineage=context.lineage,
        request_token="replace",
        filename="replacement.txt",
        raw_bytes=b"Monthly volume is now 125.",
        description="Replacement report",
        primary_category=DocumentCategory.PROCESS_VOLUMES_AND_FREQUENCY,
        submitter=_reviewer(),
        supersedes_document_id=first.document.document_id,
    )
    assert replacement.document.superseded_document is not None
    assert replacement.document.superseded_document.document_id == first.document.document_id
    assert context.repository.is_current_document(
        formal_lifecycle_id=context.lineage.formal_lifecycle_id,
        document_id=replacement.document.document_id,
    )
    assert not context.repository.is_current_document(
        formal_lifecycle_id=context.lineage.formal_lifecycle_id,
        document_id=first.document.document_id,
    )


def test_same_hash_across_lifecycles_reuses_bytes_but_separates_documents(
    tmp_path: Path,
) -> None:
    context = _prepare(tmp_path)
    payload = b"Shared organisational evidence."
    first = _accept(context, StableIds(), content=payload)
    second_repository, second_lineage = _create_second_lineage(context.path)
    second = SupportingDocumentIntakeService(
        second_repository, clock=lambda: NOW, id_factory=PrefixedIds("second-doc")
    ).accept(
        lineage=second_lineage,
        request_token="second-lifecycle-intake",
        filename="shared.txt",
        raw_bytes=payload,
        description="Shared evidence in a distinct lifecycle",
        primary_category=DocumentCategory.OTHER_ORGANISATIONAL_EVIDENCE,
        submitter=_reviewer(),
    )
    assert second.document.document_id != first.document.document_id
    assert second.document.lineage != first.document.lineage
    assert second.document.source_blob_id == first.document.source_blob_id
    connection = sqlite3.connect(context.path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM preliminary_supporting_source_blobs"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM preliminary_supporting_source_blob_bytes"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM preliminary_supporting_documents"
        ).fetchone()[0] == 2
    finally:
        connection.close()


@pytest.mark.parametrize("explicit_consent", [None, False])
def test_external_provider_never_runs_without_valid_consent(
    tmp_path: Path, explicit_consent: bool | None
) -> None:
    context, ids, accepted, _, ingested = _prepared_document(tmp_path)
    block = ingested.ingested_document.blocks[0]
    provider = ScriptedSupportingEvidenceProvider(
        (_batch(accepted.document.document_id, block.block_id, context.activity_id),),
        external=True,
        provider_id="external-test",
        provider_version="1",
    )
    service = SupportingEvidenceExtractionService(
        context.repository, provider, clock=lambda: NOW, id_factory=ids
    )
    if explicit_consent is not None:
        service.record_provider_consent(
            lineage=context.lineage,
            document_id=accepted.document.document_id,
            request_token="consent",
            explicit_consent=explicit_consent,
            declarant_name="Alex Reviewer",
        )
    with pytest.raises(SupportingEvidenceConsentRequiredError):
        service.extract(
            lineage=context.lineage,
            document_id=accepted.document.document_id,
            ingestion_attempt_id=ingested.attempt.attempt_id,
            request_token="extract-no-consent",
        )
    assert provider.calls == []


def test_valid_external_consent_permits_one_call(tmp_path: Path) -> None:
    context, ids, accepted, _, ingested = _prepared_document(tmp_path)
    block = ingested.ingested_document.blocks[0]
    provider = ScriptedSupportingEvidenceProvider(
        (_batch(accepted.document.document_id, block.block_id, context.activity_id),),
        external=True,
        provider_id="external-test",
        provider_version="1",
    )
    service = SupportingEvidenceExtractionService(
        context.repository, provider, clock=lambda: NOW, id_factory=ids
    )
    service.record_provider_consent(
        lineage=context.lineage,
        document_id=accepted.document.document_id,
        request_token="consent",
        explicit_consent=True,
        declarant_name="Alex Reviewer",
    )
    result = service.extract(
        lineage=context.lineage,
        document_id=accepted.document.document_id,
        ingestion_attempt_id=ingested.attempt.attempt_id,
        request_token="extract-consented",
    )
    assert result.attempt.status is AttemptStatus.SUCCEEDED
    assert len(provider.calls) == 1


def test_provider_version_mismatched_consent_permits_no_call(tmp_path: Path) -> None:
    context, ids, accepted, _, ingested = _prepared_document(tmp_path)
    block = ingested.ingested_document.blocks[0]
    consent_provider = ScriptedSupportingEvidenceProvider(
        (), external=True, provider_id="external-test", provider_version="1"
    )
    SupportingEvidenceExtractionService(
        context.repository, consent_provider, clock=lambda: NOW, id_factory=ids
    ).record_provider_consent(
        lineage=context.lineage,
        document_id=accepted.document.document_id,
        request_token="consent-v1",
        explicit_consent=True,
        declarant_name="Alex Reviewer",
    )
    changed_provider = ScriptedSupportingEvidenceProvider(
        (_batch(accepted.document.document_id, block.block_id, context.activity_id),),
        external=True,
        provider_id="external-test",
        provider_version="2",
    )
    with pytest.raises(SupportingEvidenceConsentRequiredError):
        SupportingEvidenceExtractionService(
            context.repository, changed_provider, clock=lambda: NOW, id_factory=ids
        ).extract(
            lineage=context.lineage,
            document_id=accepted.document.document_id,
            ingestion_attempt_id=ingested.attempt.attempt_id,
            request_token="extract-with-stale-consent",
        )
    assert changed_provider.calls == []


def test_partial_resolution_persists_only_valid_proposals(tmp_path: Path) -> None:
    context, ids, accepted, _, ingested = _prepared_document(tmp_path)
    block = ingested.ingested_document.blocks[0]
    valid = _batch(accepted.document.document_id, block.block_id, context.activity_id).items[0]
    invalid = valid.model_copy(
        update={
            "proposed_claim": "Unresolvable claim",
            "primary_citation": valid.primary_citation.model_copy(
                update={"exact_excerpt": "not in the trusted block"}
            ),
        }
    )
    provider = ScriptedSupportingEvidenceProvider(
        (
            RawSupportingEvidenceBatch(
                schema_version=SUPPORTING_EVIDENCE_PROVIDER_SCHEMA,
                items=(invalid, valid, valid),
            ),
        )
    )
    result = SupportingEvidenceExtractionService(
        context.repository, provider, clock=lambda: NOW, id_factory=ids
    ).extract(
        lineage=context.lineage,
        document_id=accepted.document.document_id,
        ingestion_attempt_id=ingested.attempt.attempt_id,
        request_token="partial",
    )
    assert result.attempt.status is AttemptStatus.PARTIAL
    assert len(result.proposals) == 1
    assert "citation-excerpt-missing" in result.attempt.issue_codes


def test_fixed_inputs_ids_time_and_provider_are_byte_stable(tmp_path: Path) -> None:
    def run(path: Path):
        context, ids, accepted, _, ingested = _prepared_document(path)
        block = ingested.ingested_document.blocks[0]
        provider = ScriptedSupportingEvidenceProvider(
            (_batch(accepted.document.document_id, block.block_id, context.activity_id),)
        )
        return SupportingEvidenceExtractionService(
            context.repository, provider, clock=lambda: NOW, id_factory=ids
        ).extract(
            lineage=context.lineage,
            document_id=accepted.document.document_id,
            ingestion_attempt_id=ingested.attempt.attempt_id,
            request_token="stable-extraction",
        )

    first = run(tmp_path / "first")
    second = run(tmp_path / "second")
    assert first.attempt.canonical_json_bytes() == second.attempt.canonical_json_bytes()
    assert tuple(item.canonical_json_bytes() for item in first.proposals) == tuple(
        item.canonical_json_bytes() for item in second.proposals
    )


@pytest.mark.parametrize(
    "excerpt, expected_issue",
    [("missing", "citation-excerpt-missing"), ("same", "citation-excerpt-ambiguous")],
)
def test_no_valid_citation_persists_failed_attempt(
    tmp_path: Path, excerpt: str, expected_issue: str
) -> None:
    context = _prepare(tmp_path)
    ids = StableIds()
    accepted = _accept(context, ids, content=b"same same")
    _, ingested = _ingest(context, ids, accepted.document.document_id)
    block = ingested.ingested_document.blocks[0]
    provider = ScriptedSupportingEvidenceProvider(
        (_batch(accepted.document.document_id, block.block_id, context.activity_id, excerpt),)
    )
    service = SupportingEvidenceExtractionService(
        context.repository, provider, clock=lambda: NOW, id_factory=ids
    )
    with pytest.raises(SupportingEvidenceCitationError) as failure:
        service.extract(
            lineage=context.lineage,
            document_id=accepted.document.document_id,
            ingestion_attempt_id=ingested.attempt.attempt_id,
            request_token=f"failed-{expected_issue}",
        )
    assert failure.value.result.attempt.status is AttemptStatus.FAILED
    assert expected_issue in failure.value.result.attempt.issue_codes
    assert failure.value.result.proposals == ()


@pytest.mark.parametrize("invalid_kind", ["document", "offset", "activity"])
def test_wrong_document_offset_or_activity_cannot_become_a_proposal(
    tmp_path: Path, invalid_kind: str
) -> None:
    context, ids, accepted, _, ingested = _prepared_document(tmp_path)
    block = ingested.ingested_document.blocks[0]
    item = _batch(
        accepted.document.document_id, block.block_id, context.activity_id
    ).items[0]
    if invalid_kind == "document":
        item = item.model_copy(
            update={
                "primary_citation": item.primary_citation.model_copy(
                    update={"document_id": "another-document"}
                )
            }
        )
    elif invalid_kind == "offset":
        item = item.model_copy(
            update={
                "primary_citation": item.primary_citation.model_copy(
                    update={
                        "block_character_start": 1,
                        "block_character_end_exclusive": 1 + len(block.extracted_text),
                    }
                )
            }
        )
    else:
        item = item.model_copy(update={"suggested_activity_ids": ("not-approved",)})
    provider = ScriptedSupportingEvidenceProvider(
        (
            RawSupportingEvidenceBatch(
                schema_version=SUPPORTING_EVIDENCE_PROVIDER_SCHEMA,
                items=(item,),
            ),
        )
    )
    service = SupportingEvidenceExtractionService(
        context.repository, provider, clock=lambda: NOW, id_factory=ids
    )
    with pytest.raises(SupportingEvidenceCitationError) as failure:
        service.extract(
            lineage=context.lineage,
            document_id=accepted.document.document_id,
            ingestion_attempt_id=ingested.attempt.attempt_id,
            request_token=f"invalid-{invalid_kind}",
        )
    assert failure.value.result.proposals == ()
    assert failure.value.result.attempt.status is AttemptStatus.FAILED


def test_provider_failure_is_safe_and_terminal(tmp_path: Path) -> None:
    context, ids, accepted, _, ingested = _prepared_document(tmp_path)
    provider = ScriptedSupportingEvidenceProvider(
        (ExtractionProviderTimeout("secret provider detail"),)
    )
    service = SupportingEvidenceExtractionService(
        context.repository, provider, clock=lambda: NOW, id_factory=ids
    )
    with pytest.raises(SupportingEvidenceProviderFailure) as failure:
        service.extract(
            lineage=context.lineage,
            document_id=accepted.document.document_id,
            ingestion_attempt_id=ingested.attempt.attempt_id,
            request_token="timeout",
        )
    assert "secret" not in str(failure.value)
    assert failure.value.provider_code == "provider-timeout"
    assert failure.value.result.attempt.status is AttemptStatus.FAILED


def test_interruption_requires_abandonment_then_exact_retry(tmp_path: Path) -> None:
    context, ids, accepted, _, ingested = _prepared_document(tmp_path)
    block = ingested.ingested_document.blocks[0]
    interrupted = ScriptedSupportingEvidenceProvider(
        (SupportingEvidenceProviderInterrupted("stopped"),)
    )
    service = SupportingEvidenceExtractionService(
        context.repository, interrupted, clock=lambda: NOW, id_factory=ids
    )
    with pytest.raises(SupportingEvidenceInterruptedError) as failure:
        service.extract(
            lineage=context.lineage,
            document_id=accepted.document.document_id,
            ingestion_attempt_id=ingested.attempt.attempt_id,
            request_token="interrupted",
        )
    pending = failure.value.pending
    with pytest.raises(SupportingEvidenceInterruptedError):
        service.extract(
            lineage=context.lineage,
            document_id=accepted.document.document_id,
            ingestion_attempt_id=ingested.attempt.attempt_id,
            request_token="interrupted",
        )
    abandoned = service.abandon(pending, abandonment_token="abandon")
    assert abandoned.attempt.status is AttemptStatus.ABANDONED

    retry_provider = ScriptedSupportingEvidenceProvider(
        (_batch(accepted.document.document_id, block.block_id, context.activity_id),)
    )
    retry = SupportingEvidenceExtractionService(
        context.repository, retry_provider, clock=lambda: NOW, id_factory=ids
    ).extract(
        lineage=context.lineage,
        document_id=accepted.document.document_id,
        ingestion_attempt_id=ingested.attempt.attempt_id,
        request_token="retry",
        predecessor_attempt_id=abandoned.attempt.attempt_id,
    )
    assert retry.attempt.attempt_number == 2
    assert retry.attempt.predecessor_attempt_id == abandoned.attempt.attempt_id
    with pytest.raises(SupportingEvidenceConcurrentAttemptError):
        SupportingEvidenceExtractionService(
            context.repository,
            ScriptedSupportingEvidenceProvider(()),
            clock=lambda: NOW,
            id_factory=ids,
        ).extract(
            lineage=context.lineage,
            document_id=accepted.document.document_id,
            ingestion_attempt_id=ingested.attempt.attempt_id,
            request_token="silent-reopen",
        )


def test_atomic_finalization_failure_leaves_start_but_no_bundle(tmp_path: Path) -> None:
    context, ids, accepted, _, ingested = _prepared_document(tmp_path)
    block = ingested.ingested_document.blocks[0]

    def fail(operation: str) -> None:
        if operation == "STORE_EXTRACTION_BUNDLE":
            raise RuntimeError("injected")

    repository = SQLiteFormalEvidenceRepository(
        context.path,
        clock=lambda: NOW,
        failure_injector=fail,
    )
    provider = ScriptedSupportingEvidenceProvider(
        (_batch(accepted.document.document_id, block.block_id, context.activity_id),)
    )
    service = SupportingEvidenceExtractionService(
        repository, provider, clock=lambda: NOW, id_factory=ids
    )
    with pytest.raises(SupportingEvidenceFinalizationError):
        service.extract(
            lineage=context.lineage,
            document_id=accepted.document.document_id,
            ingestion_attempt_id=ingested.attempt.attempt_id,
            request_token="finalization-failure",
        )
    connection = sqlite3.connect(context.path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM preliminary_supporting_extraction_attempts"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM preliminary_supporting_evidence_proposals"
        ).fetchone()[0] == 0
        assert connection.execute(
            """SELECT COUNT(*) FROM preliminary_supporting_formal_evidence_workflow_events
               WHERE subject_id LIKE 'slice3-supporting-extraction-%'"""
        ).fetchone()[0] == 1
    finally:
        connection.close()


def test_frozen_workspace_rejects_services_before_provider_and_preserves_files(
    tmp_path: Path,
) -> None:
    context, ids, accepted, _, ingested = _prepared_document(tmp_path / "writable")
    block = ingested.ingested_document.blocks[0]
    pending_provider = ScriptedSupportingEvidenceProvider(
        (SupportingEvidenceProviderInterrupted("stop"),)
    )
    writable_extraction = SupportingEvidenceExtractionService(
        context.repository, pending_provider, clock=lambda: NOW, id_factory=ids
    )
    with pytest.raises(SupportingEvidenceInterruptedError) as interrupted:
        writable_extraction.extract(
            lineage=context.lineage,
            document_id=accepted.document.document_id,
            ingestion_attempt_id=ingested.attempt.attempt_id,
            request_token="pending-before-freeze",
        )

    frozen_directory = tmp_path / "evaluation" / "portfolio" / "slice3-case"
    frozen_directory.mkdir(parents=True)
    frozen_path = frozen_directory / "workspace.db"
    shutil.copy2(context.path, frozen_path)

    def snapshot() -> dict[str, bytes]:
        return {
            item.name: item.read_bytes()
            for item in sorted(frozen_directory.iterdir())
            if item.is_file()
        }

    before = snapshot()
    original_path = context.repository.path
    context.repository.path = frozen_path
    provider = ScriptedSupportingEvidenceProvider(
        (_batch(accepted.document.document_id, block.block_id, context.activity_id),)
    )
    extraction = SupportingEvidenceExtractionService(
        context.repository, provider, clock=lambda: NOW, id_factory=ids
    )
    try:
        with pytest.raises(FrozenEvaluationWorkspaceError):
            SupportingDocumentIntakeService(
                context.repository, clock=lambda: NOW, id_factory=ids
            ).accept(
                lineage=context.lineage,
                request_token="frozen-intake",
                filename="frozen.txt",
                raw_bytes=b"must not persist",
                description="Frozen",
                primary_category=DocumentCategory.OTHER_ORGANISATIONAL_EVIDENCE,
                submitter=_reviewer(),
            )
        with pytest.raises(FrozenEvaluationWorkspaceError):
            SupportingDocumentIngestionService(
                context.repository, clock=lambda: NOW, id_factory=ids
            ).ingest(
                lineage=context.lineage,
                document_id=accepted.document.document_id,
                request_token="frozen-ingestion",
            )
        with pytest.raises(FrozenEvaluationWorkspaceError):
            extraction.extract(
                lineage=context.lineage,
                document_id=accepted.document.document_id,
                ingestion_attempt_id=ingested.attempt.attempt_id,
                request_token="frozen-extraction",
            )
        with pytest.raises(FrozenEvaluationWorkspaceError):
            extraction.abandon(
                interrupted.value.pending,
                abandonment_token="frozen-abandon",
            )
    finally:
        context.repository.path = original_path
    assert provider.calls == []
    assert snapshot() == before
