from __future__ import annotations

import sqlite3
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_adoption_engine.models.formal_evidence import (
    FORMAL_EVIDENCE_FAMILY,
    SUPPORTING_EVIDENCE_EXTRACTION_ATTEMPT_SCHEMA,
    AttemptStatus,
    DocumentCategory,
    EvidenceClassification,
    ReviewAction,
    ReviewerDeclaration,
    SupportingEvidenceExtractionAttempt,
    SupportingEvidenceProposal,
)
from ai_adoption_engine.persistence.formal_evidence import (
    SQLiteFormalEvidenceRepository,
)
from ai_adoption_engine.persistence.workspace_protection import (
    FrozenEvaluationWorkspaceError,
)
from ai_adoption_engine.supporting_evidence.common import request_identity
from ai_adoption_engine.supporting_evidence.errors import (
    SupportingEvidenceConcurrentReviewError,
    SupportingEvidenceFinalizationError,
    SupportingEvidenceInsufficientConflictError,
    SupportingEvidenceInvalidReferenceError,
    SupportingEvidenceInvalidReviewError,
    SupportingEvidenceInvalidReviewerError,
    SupportingEvidenceLineageError,
    SupportingEvidenceRequestConflictError,
    SupportingEvidenceStaleProposalError,
    SupportingEvidenceStaleRevisionError,
)
from ai_adoption_engine.supporting_evidence.extraction import (
    SupportingEvidenceExtractionService,
)
from ai_adoption_engine.supporting_evidence.intake import (
    SupportingDocumentIntakeService,
)
from ai_adoption_engine.supporting_evidence.provider import (
    SUPPORTING_EVIDENCE_PROVIDER_SCHEMA,
    RawSupportingEvidenceBatch,
    ScriptedSupportingEvidenceProvider,
)
from ai_adoption_engine.supporting_evidence.review import (
    ReviewQueueScope,
    ReviewQueueStatus,
    SupportingEvidenceReviewService,
)
from tests.integration.test_formal_evidence_persistence import _prepare
from tests.integration.test_supporting_evidence_slice3_services import (
    NOW,
    PrefixedIds,
    StableIds,
    _accept,
    _batch,
    _create_second_lineage,
    _ingest,
    _reviewer,
)


def _extract(
    context,
    ids,
    *,
    intake_token: str,
    content: bytes,
    claims: tuple[str, ...],
):
    accepted = _accept(context, ids, token=intake_token, content=content)
    _, ingested = _ingest(
        context,
        ids,
        accepted.document.document_id,
        token=f"{intake_token}-ingest",
    )
    assert ingested.ingested_document is not None
    block = ingested.ingested_document.blocks[0]
    base = _batch(
        accepted.document.document_id,
        block.block_id,
        context.activity_id,
        excerpt=block.extracted_text,
    ).items[0]
    items = tuple(
        base.model_copy(update={"proposed_claim": claim}) for claim in claims
    )
    provider = ScriptedSupportingEvidenceProvider(
        (
            RawSupportingEvidenceBatch(
                schema_version=SUPPORTING_EVIDENCE_PROVIDER_SCHEMA,
                items=items,
            ),
        )
    )
    extraction = SupportingEvidenceExtractionService(
        context.repository,
        provider,
        clock=lambda: NOW,
        id_factory=ids,
    ).extract(
        lineage=context.lineage,
        document_id=accepted.document.document_id,
        ingestion_attempt_id=ingested.attempt.attempt_id,
        request_token=f"{intake_token}-extract",
    )
    return accepted, ingested, extraction


def _setup(tmp_path: Path, *, claims: int = 6):
    context = _prepare(tmp_path)
    ids = StableIds()
    values = tuple(f"Reviewed claim {index}." for index in range(1, claims + 1))
    accepted, ingested, extraction = _extract(
        context,
        ids,
        intake_token="review-source",
        content=b"Monthly volume is 100.",
        claims=values,
    )
    service = SupportingEvidenceReviewService(
        context.repository,
        clock=lambda: NOW,
        id_factory=ids,
    )
    return context, ids, service, accepted, ingested, extraction


def _fact(service, context, proposal, token: str, *, expected=None, action=ReviewAction.ACCEPT, claim=None):
    return service.review_proposal(
        context.lineage.formal_lifecycle_id,
        proposal.proposal_id,
        request_token=token,
        expected_prior_revision_id=expected,
        action=action,
        reviewer=_reviewer(),
        approved_claim=claim,
        selected_category=DocumentCategory.PROCESS_VOLUMES_AND_FREQUENCY,
        approved_classification=EvidenceClassification.DOCUMENTED_FACT,
        claim_directly_supported_by_excerpt=True,
        rationale="The unchanged excerpt directly supports this claim.",
    )


def test_queue_is_deterministic_current_only_and_progress_is_review_only(
    tmp_path: Path,
) -> None:
    context = _prepare(tmp_path)
    ids = StableIds()
    first, _, first_extraction = _extract(
        context,
        ids,
        intake_token="first",
        content=b"First current evidence.",
        claims=("First claim.", "Second claim."),
    )
    second, _, second_extraction = _extract(
        context,
        ids,
        intake_token="second",
        content=b"Second current evidence.",
        claims=("Third claim.",),
    )
    service = SupportingEvidenceReviewService(context.repository, id_factory=ids)
    queue = service.get_review_queue(context.lineage.formal_lifecycle_id)
    assert tuple(item.proposal.proposal_id for item in queue.items) == (
        *(item.proposal_id for item in first_extraction.proposals),
        *(item.proposal_id for item in second_extraction.proposals),
    )
    assert {item.scope for item in queue.items} == {ReviewQueueScope.CURRENT}
    assert queue.progress.total_current_proposals == 3
    assert queue.progress.unreviewed_proposals == 3
    assert queue.progress.review_complete is False

    for index, item in enumerate(queue.items, start=1):
        _fact(service, context, item.proposal, f"fact-{index}")
    completed = service.get_review_queue(context.lineage.formal_lifecycle_id)
    assert completed.progress.accepted_proposals == 3
    assert completed.progress.review_complete is True
    connection = sqlite3.connect(context.path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM preliminary_supporting_formal_evidence_readiness"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM preliminary_supporting_formal_input_mappings"
        ).fetchone()[0] == 0
    finally:
        connection.close()
    assert first.document.document_id != second.document.document_id


def test_accept_correct_reject_unknown_and_conflict_actions(tmp_path: Path) -> None:
    context, _, service, _, _, extraction = _setup(tmp_path)
    proposals = extraction.proposals
    accepted = _fact(service, context, proposals[0], "accept-fact")
    assert accepted.revision.action is ReviewAction.ACCEPT
    assert accepted.revision.approved_claim == proposals[0].proposed_claim
    assert accepted.revision.source_spans == (
        proposals[0].primary_source_span,
        *proposals[0].related_source_spans,
    )
    assert accepted.revision.candidate_eligible is True

    corrected = _fact(
        service,
        context,
        proposals[1],
        "correct-fact",
        action=ReviewAction.CORRECT,
        claim="Corrected wording grounded in the same excerpt.",
    )
    assert corrected.revision.original_proposal == proposals[1]
    assert corrected.revision.approved_claim != proposals[1].proposed_claim

    inference = service.review_proposal(
        context.lineage.formal_lifecycle_id,
        proposals[2].proposal_id,
        request_token="accept-inference",
        expected_prior_revision_id=None,
        action=ReviewAction.ACCEPT,
        reviewer=_reviewer(),
        selected_category=DocumentCategory.PROCESS_VOLUMES_AND_FREQUENCY,
        approved_classification=EvidenceClassification.REVIEWED_INFERENCE,
        claim_directly_supported_by_excerpt=False,
        inference_confidence=0.7,
        documented_fact_review_ids=(accepted.revision.revision_id,),
        rationale="This is an explicit human inference from the reviewed fact.",
    )
    assert inference.revision.inference_documented_facts[0].review_revision_id == accepted.revision.revision_id

    rejected = service.review_proposal(
        context.lineage.formal_lifecycle_id,
        proposals[3].proposal_id,
        request_token="reject",
        expected_prior_revision_id=None,
        action=ReviewAction.REJECT,
        reviewer=_reviewer(),
        rationale="The provider suggestion is not reliable evidence.",
    )
    assert rejected.revision.approved_claim is None
    assert rejected.revision.approved_classification is None
    assert rejected.revision.source_spans == ()
    assert rejected.revision.candidate_eligible is False

    unknown = service.review_proposal(
        context.lineage.formal_lifecycle_id,
        proposals[4].proposal_id,
        request_token="unknown",
        expected_prior_revision_id=None,
        action=ReviewAction.MARK_UNRESOLVED,
        reviewer=_reviewer(),
        approved_claim="The current volume remains unknown.",
        selected_category=DocumentCategory.PROCESS_VOLUMES_AND_FREQUENCY,
        approved_classification=EvidenceClassification.UNKNOWN,
        rationale="The supplied excerpt does not establish a current value.",
    )
    assert unknown.revision.candidate_eligible is False
    assert unknown.revision.inference_confidence is None

    conflict = service.review_proposal(
        context.lineage.formal_lifecycle_id,
        proposals[5].proposal_id,
        request_token="conflict",
        expected_prior_revision_id=None,
        action=ReviewAction.MARK_UNRESOLVED,
        reviewer=_reviewer(),
        approved_claim="The reviewed records conflict and remain unresolved.",
        selected_category=DocumentCategory.PROCESS_VOLUMES_AND_FREQUENCY,
        approved_classification=EvidenceClassification.CONFLICT,
        competing_review_ids=(
            accepted.revision.revision_id,
            corrected.revision.revision_id,
        ),
        rationale="Both current reviewed records must remain visible.",
    )
    assert len(conflict.revision.competing_evidence) == 2
    assert conflict.revision.candidate_eligible is False
    progress = service.get_review_queue(context.lineage.formal_lifecycle_id).progress
    assert progress.accepted_proposals == 2
    assert progress.corrected_proposals == 1
    assert progress.rejected_proposals == 1
    assert progress.unresolved_unknowns == 1
    assert progress.unresolved_conflicts == 1
    assert progress.review_complete is True


def test_correct_into_inference_and_later_deliberate_revision(tmp_path: Path) -> None:
    context, _, service, _, _, extraction = _setup(tmp_path, claims=2)
    fact = _fact(service, context, extraction.proposals[0], "fact")
    initial = _fact(service, context, extraction.proposals[1], "initial")
    changed = service.review_proposal(
        context.lineage.formal_lifecycle_id,
        extraction.proposals[1].proposal_id,
        request_token="change-to-inference",
        expected_prior_revision_id=initial.revision.revision_id,
        action=ReviewAction.CORRECT,
        reviewer=_reviewer(),
        approved_claim="A revised human inference from the documented volume.",
        selected_category=DocumentCategory.PROCESS_VOLUMES_AND_FREQUENCY,
        approved_classification=EvidenceClassification.REVIEWED_INFERENCE,
        claim_directly_supported_by_excerpt=False,
        inference_confidence=0.6,
        documented_fact_review_ids=(fact.revision.revision_id,),
        rationale="The revised wording is inferential rather than directly quoted.",
    )
    assert changed.revision.revision_number == 2
    assert changed.revision.prior_revision_id == initial.revision.revision_id
    history = service.get_review_history(
        context.lineage.formal_lifecycle_id,
        extraction.proposals[1].proposal_id,
    )
    assert history == (initial.revision, changed.revision)


def test_deliberate_terminal_disposition_changes_append_new_revisions(
    tmp_path: Path,
) -> None:
    context, _, service, _, _, extraction = _setup(tmp_path, claims=3)
    accepted = _fact(service, context, extraction.proposals[0], "accepted")
    accepted_to_rejected = service.review_proposal(
        context.lineage.formal_lifecycle_id,
        extraction.proposals[0].proposal_id,
        request_token="accepted-to-rejected",
        expected_prior_revision_id=accepted.revision.revision_id,
        action=ReviewAction.REJECT,
        reviewer=_reviewer(),
        rationale="Later review determined this proposal must remain audit-only.",
    )
    assert accepted_to_rejected.revision.revision_number == 2
    assert accepted_to_rejected.revision.action is ReviewAction.REJECT

    rejected = service.review_proposal(
        context.lineage.formal_lifecycle_id,
        extraction.proposals[1].proposal_id,
        request_token="initial-reject",
        expected_prior_revision_id=None,
        action=ReviewAction.REJECT,
        reviewer=_reviewer(),
        rationale="Initially rejected pending a deliberate re-review.",
    )
    rejected_to_accepted = _fact(
        service,
        context,
        extraction.proposals[1],
        "rejected-to-accepted",
        expected=rejected.revision.revision_id,
    )
    assert rejected_to_accepted.revision.revision_number == 2
    assert rejected_to_accepted.revision.action is ReviewAction.ACCEPT

    unresolved = service.review_proposal(
        context.lineage.formal_lifecycle_id,
        extraction.proposals[2].proposal_id,
        request_token="initial-unknown",
        expected_prior_revision_id=None,
        action=ReviewAction.MARK_UNRESOLVED,
        reviewer=_reviewer(),
        approved_claim="This proposal is unresolved.",
        selected_category=DocumentCategory.OTHER_ORGANISATIONAL_EVIDENCE,
        approved_classification=EvidenceClassification.UNKNOWN,
        rationale="The initial review could not establish the claim.",
    )
    unresolved_to_fact = _fact(
        service,
        context,
        extraction.proposals[2],
        "unknown-to-fact",
        expected=unresolved.revision.revision_id,
        action=ReviewAction.CORRECT,
        claim="Later review established a directly supported corrected fact.",
    )
    assert unresolved_to_fact.revision.revision_number == 2
    assert (
        unresolved_to_fact.revision.approved_classification
        is EvidenceClassification.DOCUMENTED_FACT
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "action": ReviewAction.ACCEPT,
            "approved_classification": EvidenceClassification.UNKNOWN,
            "approved_claim": None,
            "claim_directly_supported_by_excerpt": None,
        },
        {
            "action": ReviewAction.CORRECT,
            "approved_classification": EvidenceClassification.DOCUMENTED_FACT,
            "approved_claim": "Reviewed claim 1.",
            "claim_directly_supported_by_excerpt": True,
        },
        {
            "action": ReviewAction.MARK_UNRESOLVED,
            "approved_classification": EvidenceClassification.REVIEWED_INFERENCE,
            "approved_claim": "Still unresolved.",
            "claim_directly_supported_by_excerpt": False,
        },
    ],
)
def test_invalid_action_classification_combinations_fail_without_writes(
    tmp_path: Path, kwargs: dict
) -> None:
    context, _, service, _, _, extraction = _setup(tmp_path, claims=1)
    with pytest.raises(SupportingEvidenceInvalidReviewError):
        service.review_proposal(
            context.lineage.formal_lifecycle_id,
            extraction.proposals[0].proposal_id,
            request_token="invalid",
            expected_prior_revision_id=None,
            reviewer=_reviewer(),
            selected_category=DocumentCategory.PROCESS_VOLUMES_AND_FREQUENCY,
            rationale="This combination is invalid.",
            **kwargs,
        )
    assert service.get_review_history(
        context.lineage.formal_lifecycle_id,
        extraction.proposals[0].proposal_id,
    ) == ()


def test_provider_classification_is_not_automatically_approved(tmp_path: Path) -> None:
    context, _, service, _, _, extraction = _setup(tmp_path, claims=1)
    proposal = extraction.proposals[0]
    assert proposal.proposed_classification is EvidenceClassification.DOCUMENTED_FACT
    with pytest.raises(SupportingEvidenceInvalidReviewError):
        service.review_proposal(
            context.lineage.formal_lifecycle_id,
            proposal.proposal_id,
            request_token="missing-human-classification",
            expected_prior_revision_id=None,
            action=ReviewAction.ACCEPT,
            reviewer=_reviewer(),
            selected_category=proposal.proposed_category,
            claim_directly_supported_by_excerpt=True,
            rationale="No explicit classification was supplied.",
        )


def test_fact_links_must_be_current_fact_reviews_and_become_stale(tmp_path: Path) -> None:
    context, _, service, _, _, extraction = _setup(tmp_path, claims=3)
    fact = _fact(service, context, extraction.proposals[0], "fact")
    inference = service.review_proposal(
        context.lineage.formal_lifecycle_id,
        extraction.proposals[1].proposal_id,
        request_token="inference",
        expected_prior_revision_id=None,
        action=ReviewAction.ACCEPT,
        reviewer=_reviewer(),
        selected_category=DocumentCategory.OTHER_ORGANISATIONAL_EVIDENCE,
        approved_classification=EvidenceClassification.REVIEWED_INFERENCE,
        claim_directly_supported_by_excerpt=False,
        inference_confidence=0.5,
        documented_fact_review_ids=(fact.revision.revision_id,),
        rationale="Inference linked to the current documented fact.",
    )
    revised_fact = _fact(
        service,
        context,
        extraction.proposals[0],
        "revised-fact",
        expected=fact.revision.revision_id,
        action=ReviewAction.CORRECT,
        claim="Updated fact wording from the same excerpt.",
    )
    assert revised_fact.revision.revision_number == 2
    queue = service.get_review_queue(context.lineage.formal_lifecycle_id)
    inference_item = next(
        item for item in queue.items if item.proposal.proposal_id == inference.revision.proposal_id
    )
    assert inference_item.references_current is False
    with pytest.raises(SupportingEvidenceInvalidReferenceError):
        service.review_proposal(
            context.lineage.formal_lifecycle_id,
            extraction.proposals[2].proposal_id,
            request_token="stale-fact-link",
            expected_prior_revision_id=None,
            action=ReviewAction.ACCEPT,
            reviewer=_reviewer(),
            selected_category=DocumentCategory.OTHER_ORGANISATIONAL_EVIDENCE,
            approved_classification=EvidenceClassification.REVIEWED_INFERENCE,
            claim_directly_supported_by_excerpt=False,
            inference_confidence=0.5,
            documented_fact_review_ids=(fact.revision.revision_id,),
            rationale="The old fact revision is no longer current.",
        )
    with pytest.raises(SupportingEvidenceInvalidReferenceError):
        service.review_proposal(
            context.lineage.formal_lifecycle_id,
            extraction.proposals[2].proposal_id,
            request_token="missing-fact-link",
            expected_prior_revision_id=None,
            action=ReviewAction.ACCEPT,
            reviewer=_reviewer(),
            selected_category=DocumentCategory.OTHER_ORGANISATIONAL_EVIDENCE,
            approved_classification=EvidenceClassification.REVIEWED_INFERENCE,
            claim_directly_supported_by_excerpt=False,
            inference_confidence=0.5,
            documented_fact_review_ids=("missing-review-revision",),
            rationale="Missing references must fail safely.",
        )


def test_rejected_wrong_classification_and_superseded_fact_links_fail(
    tmp_path: Path,
) -> None:
    context, ids, service, accepted, _, extraction = _setup(tmp_path, claims=3)
    rejected = service.review_proposal(
        context.lineage.formal_lifecycle_id,
        extraction.proposals[0].proposal_id,
        request_token="reject-fact",
        expected_prior_revision_id=None,
        action=ReviewAction.REJECT,
        reviewer=_reviewer(),
        rationale="Rejected for reference testing.",
    )
    fact = _fact(service, context, extraction.proposals[1], "fact")
    inference = service.review_proposal(
        context.lineage.formal_lifecycle_id,
        extraction.proposals[2].proposal_id,
        request_token="inference-review",
        expected_prior_revision_id=None,
        action=ReviewAction.ACCEPT,
        reviewer=_reviewer(),
        selected_category=DocumentCategory.OTHER_ORGANISATIONAL_EVIDENCE,
        approved_classification=EvidenceClassification.REVIEWED_INFERENCE,
        claim_directly_supported_by_excerpt=False,
        inference_confidence=0.5,
        documented_fact_review_ids=(fact.revision.revision_id,),
        rationale="Valid inference for wrong-classification testing.",
    )
    new_document, _, new_extraction = _extract(
        context,
        ids,
        intake_token="new-current",
        content=b"New current source.",
        claims=("New inference candidate.",),
    )
    for revision_id in (
        rejected.revision.revision_id,
        inference.revision.revision_id,
    ):
        with pytest.raises(SupportingEvidenceInvalidReferenceError):
            service.review_proposal(
                context.lineage.formal_lifecycle_id,
                new_extraction.proposals[0].proposal_id,
                request_token=f"bad-link-{revision_id}",
                expected_prior_revision_id=None,
                action=ReviewAction.ACCEPT,
                reviewer=_reviewer(),
                selected_category=DocumentCategory.OTHER_ORGANISATIONAL_EVIDENCE,
                approved_classification=EvidenceClassification.REVIEWED_INFERENCE,
                claim_directly_supported_by_excerpt=False,
                inference_confidence=0.5,
                documented_fact_review_ids=(revision_id,),
                rationale="Invalid reviewed-fact reference.",
            )

    SupportingDocumentIntakeService(
        context.repository, clock=lambda: NOW, id_factory=ids
    ).accept(
        lineage=context.lineage,
        request_token="supersede-source",
        filename="replacement.txt",
        raw_bytes=b"Replacement source.",
        description="Replacement",
        primary_category=DocumentCategory.OTHER_ORGANISATIONAL_EVIDENCE,
        submitter=_reviewer(),
        supersedes_document_id=accepted.document.document_id,
    )
    with pytest.raises(SupportingEvidenceInvalidReferenceError):
        service.review_proposal(
            context.lineage.formal_lifecycle_id,
            new_extraction.proposals[0].proposal_id,
            request_token="superseded-link",
            expected_prior_revision_id=None,
            action=ReviewAction.ACCEPT,
            reviewer=_reviewer(),
            selected_category=DocumentCategory.OTHER_ORGANISATIONAL_EVIDENCE,
            approved_classification=EvidenceClassification.REVIEWED_INFERENCE,
            claim_directly_supported_by_excerpt=False,
            inference_confidence=0.5,
            documented_fact_review_ids=(fact.revision.revision_id,),
            rationale="Superseded facts are historical.",
        )
    assert new_document.document.document_id != accepted.document.document_id


def test_conflict_requires_two_unique_valid_current_references(tmp_path: Path) -> None:
    context, _, service, _, _, extraction = _setup(tmp_path, claims=3)
    fact = _fact(service, context, extraction.proposals[0], "fact")
    for references in (
        (fact.revision.revision_id,),
        (fact.revision.revision_id, fact.revision.revision_id),
    ):
        with pytest.raises(SupportingEvidenceInsufficientConflictError):
            service.review_proposal(
                context.lineage.formal_lifecycle_id,
                extraction.proposals[2].proposal_id,
                request_token=f"invalid-conflict-{len(references)}-{len(set(references))}",
                expected_prior_revision_id=None,
                action=ReviewAction.MARK_UNRESOLVED,
                reviewer=_reviewer(),
                approved_claim="The evidence conflicts.",
                selected_category=DocumentCategory.OTHER_ORGANISATIONAL_EVIDENCE,
                approved_classification=EvidenceClassification.CONFLICT,
                competing_review_ids=references,
                rationale="Insufficient competing evidence.",
            )


def test_revision_replay_conflict_stale_and_restart_safe(tmp_path: Path) -> None:
    context, ids, service, _, _, extraction = _setup(tmp_path, claims=1)
    proposal = extraction.proposals[0]
    first = _fact(service, context, proposal, "review-token")
    replay = _fact(service, context, proposal, "review-token")
    assert replay.replayed is True
    assert replay.revision == first.revision
    with pytest.raises(SupportingEvidenceRequestConflictError):
        service.review_proposal(
            context.lineage.formal_lifecycle_id,
            proposal.proposal_id,
            request_token="review-token",
            expected_prior_revision_id=None,
            action=ReviewAction.REJECT,
            reviewer=_reviewer(),
            rationale="Conflicting token reuse.",
        )
    with pytest.raises(SupportingEvidenceStaleRevisionError):
        _fact(service, context, proposal, "stale-review", expected=None)

    restarted = SupportingEvidenceReviewService(
        SQLiteFormalEvidenceRepository(context.path, clock=lambda: NOW),
        clock=lambda: NOW,
        id_factory=ids,
    )
    restarted_replay = _fact(restarted, context, proposal, "review-token")
    assert restarted_replay.replayed is True
    assert restarted_replay.revision == first.revision


def test_concurrent_review_has_one_winner(tmp_path: Path) -> None:
    context, _, _, _, _, extraction = _setup(tmp_path, claims=1)
    proposal = extraction.proposals[0]

    def run(namespace: str):
        repository = SQLiteFormalEvidenceRepository(context.path, clock=lambda: NOW)
        service = SupportingEvidenceReviewService(
            repository,
            clock=lambda: NOW,
            id_factory=PrefixedIds(namespace),
        )
        try:
            return _fact(service, context, proposal, f"concurrent-{namespace}")
        except Exception as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, ("one", "two")))
    assert sum(hasattr(item, "revision") for item in results) == 1
    assert sum(
        isinstance(
            item,
            (SupportingEvidenceStaleRevisionError, SupportingEvidenceConcurrentReviewError),
        )
        for item in results
    ) == 1


def test_injected_review_failure_rolls_back_and_same_token_recovers(
    tmp_path: Path,
) -> None:
    context, ids, _, _, _, extraction = _setup(tmp_path, claims=1)

    def fail(operation: str) -> None:
        if operation == "APPEND_REVIEW_REVISION":
            raise RuntimeError("injected")

    repository = SQLiteFormalEvidenceRepository(
        context.path,
        clock=lambda: NOW,
        failure_injector=fail,
    )
    failing = SupportingEvidenceReviewService(
        repository, clock=lambda: NOW, id_factory=ids
    )
    with pytest.raises(SupportingEvidenceFinalizationError):
        _fact(failing, context, extraction.proposals[0], "recoverable-review")
    connection = sqlite3.connect(context.path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM preliminary_supporting_evidence_review_revisions"
        ).fetchone()[0] == 0
        assert connection.execute(
            """SELECT COUNT(*) FROM preliminary_supporting_operation_requests
               WHERE request_token = 'recoverable-review'"""
        ).fetchone()[0] == 0
    finally:
        connection.close()
    recovered = _fact(
        SupportingEvidenceReviewService(
            context.repository, clock=lambda: NOW, id_factory=ids
        ),
        context,
        extraction.proposals[0],
        "recoverable-review",
    )
    assert recovered.replayed is False


def test_later_extraction_and_supersession_make_old_proposals_audit_only(
    tmp_path: Path,
) -> None:
    context, ids, service, accepted, ingested, extraction = _setup(tmp_path, claims=1)
    old_proposal = extraction.proposals[0]
    _fact(service, context, old_proposal, "old-review")

    failed = SupportingEvidenceExtractionAttempt(
        schema_version=SUPPORTING_EVIDENCE_EXTRACTION_ATTEMPT_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        lineage=context.lineage,
        attempt_id="manual-extraction-2",
        attempt_number=2,
        document_id=accepted.document.document_id,
        document_content_sha256=accepted.document.source_blob_sha256,
        ingestion_attempt_id=ingested.attempt.attempt_id,
        predecessor_attempt_id=extraction.attempt.attempt_id,
        extractor=extraction.attempt.extractor,
        request=request_identity("manual-failed", {"attempt": 2}),
        status=AttemptStatus.FAILED,
        issue_codes=("manual-failure",),
        started_at=NOW,
        completed_at=NOW,
    )
    context.repository.store_extraction_bundle(failed, ())
    after_failure = service.get_review_queue(context.lineage.formal_lifecycle_id)
    assert after_failure.items[0].proposal == old_proposal

    proposal_payload = old_proposal.model_dump(mode="json")
    proposal_payload.update(
        {
            "proposal_id": None,
            "extraction_attempt_id": "manual-extraction-3",
            "proposed_claim": "A later independently extracted claim.",
        }
    )
    new_proposal = SupportingEvidenceProposal.model_validate(proposal_payload)
    later = SupportingEvidenceExtractionAttempt(
        schema_version=SUPPORTING_EVIDENCE_EXTRACTION_ATTEMPT_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        lineage=context.lineage,
        attempt_id="manual-extraction-3",
        attempt_number=3,
        document_id=accepted.document.document_id,
        document_content_sha256=accepted.document.source_blob_sha256,
        ingestion_attempt_id=ingested.attempt.attempt_id,
        predecessor_attempt_id=failed.attempt_id,
        extractor=extraction.attempt.extractor,
        request=request_identity("manual-success", {"attempt": 3}),
        status=AttemptStatus.PARTIAL,
        proposal_ids=(new_proposal.proposal_id,),
        issue_codes=("manual-partial",),
        started_at=NOW,
        completed_at=NOW,
    )
    context.repository.store_extraction_bundle(later, (new_proposal,))
    for number, status in enumerate(
        (AttemptStatus.INTERRUPTED, AttemptStatus.ABANDONED), start=4
    ):
        ignored = SupportingEvidenceExtractionAttempt(
            schema_version=SUPPORTING_EVIDENCE_EXTRACTION_ATTEMPT_SCHEMA,
            contract_family=FORMAL_EVIDENCE_FAMILY,
            lineage=context.lineage,
            attempt_id=f"manual-extraction-{number}",
            attempt_number=number,
            document_id=accepted.document.document_id,
            document_content_sha256=accepted.document.source_blob_sha256,
            ingestion_attempt_id=ingested.attempt.attempt_id,
            predecessor_attempt_id=f"manual-extraction-{number - 1}",
            extractor=extraction.attempt.extractor,
            request=request_identity(
                f"manual-{status.value.lower()}", {"attempt": number}
            ),
            status=status,
            issue_codes=(f"manual-{status.value.lower()}",),
            started_at=NOW,
            completed_at=NOW,
        )
        context.repository.store_extraction_bundle(ignored, ())
    queue = service.get_review_queue(context.lineage.formal_lifecycle_id)
    assert tuple(item.proposal for item in queue.items) == (new_proposal,)
    assert queue.items[0].review_status is ReviewQueueStatus.UNREVIEWED
    assert queue.audit_history[0].proposal == old_proposal
    assert queue.audit_history[0].scope is ReviewQueueScope.STALE
    with pytest.raises(SupportingEvidenceStaleProposalError):
        _fact(service, context, old_proposal, "review-stale-proposal")

    SupportingDocumentIntakeService(
        context.repository, clock=lambda: NOW, id_factory=ids
    ).accept(
        lineage=context.lineage,
        request_token="replacement",
        filename="replacement.txt",
        raw_bytes=b"Replacement evidence.",
        description="Replacement",
        primary_category=DocumentCategory.OTHER_ORGANISATIONAL_EVIDENCE,
        submitter=_reviewer(),
        supersedes_document_id=accepted.document.document_id,
    )
    superseded = service.get_review_queue(context.lineage.formal_lifecycle_id)
    assert superseded.items == ()
    assert all(
        item.scope is ReviewQueueScope.HISTORICAL
        for item in superseded.audit_history
    )


def test_cross_lineage_fact_reference_fails(tmp_path: Path) -> None:
    context, ids, service, _, _, extraction = _setup(tmp_path, claims=1)
    second_repository, second_lineage = _create_second_lineage(context.path)
    second_context = SimpleNamespace(
        repository=second_repository,
        lineage=second_lineage,
        activity_id=second_repository.approved_activity_catalog(second_lineage)[0][0],
    )
    _, _, second_extraction = _extract(
        second_context,
        PrefixedIds("second-review"),
        intake_token="second-source",
        content=b"Second lifecycle evidence.",
        claims=("Second lifecycle fact.",),
    )
    second_service = SupportingEvidenceReviewService(
        second_repository,
        clock=lambda: NOW,
        id_factory=PrefixedIds("second-review-service"),
    )
    second_fact = _fact(
        second_service,
        second_context,
        second_extraction.proposals[0],
        "second-fact",
    )
    with pytest.raises(SupportingEvidenceInvalidReferenceError):
        service.review_proposal(
            context.lineage.formal_lifecycle_id,
            extraction.proposals[0].proposal_id,
            request_token="cross-lineage",
            expected_prior_revision_id=None,
            action=ReviewAction.ACCEPT,
            reviewer=_reviewer(),
            selected_category=DocumentCategory.OTHER_ORGANISATIONAL_EVIDENCE,
            approved_classification=EvidenceClassification.REVIEWED_INFERENCE,
            claim_directly_supported_by_excerpt=False,
            inference_confidence=0.5,
            documented_fact_review_ids=(second_fact.revision.revision_id,),
            rationale="Cross-lineage references must fail.",
        )


def test_reviewer_declaration_is_mandatory_and_typed(tmp_path: Path) -> None:
    context, _, service, _, _, extraction = _setup(tmp_path, claims=1)
    invalid = {
        "schema_version": "reviewer-declaration.v0.1",
        "contract_family": FORMAL_EVIDENCE_FAMILY,
        "reviewer_display_name": " ",
        "declared_organisational_role": "Owner",
        "identity_and_authority_locally_declared_not_authenticated": True,
        "declared_at": datetime(2026, 10, 4, 15, 0, tzinfo=UTC),
    }
    with pytest.raises(SupportingEvidenceInvalidReviewerError):
        service.review_proposal(
            context.lineage.formal_lifecycle_id,
            extraction.proposals[0].proposal_id,
            request_token="invalid-reviewer",
            expected_prior_revision_id=None,
            action=ReviewAction.REJECT,
            reviewer=invalid,
            rationale="Invalid reviewer must fail.",
        )


def test_context_notes_are_context_only_scoped_replayable_and_conflict_safe(
    tmp_path: Path,
) -> None:
    context, ids, service, _, _, extraction = _setup(tmp_path, claims=1)
    process_note = service.add_context_note(
        context.lineage.formal_lifecycle_id,
        request_token="process-note",
        statement="The team expects seasonal variation.",
        reviewer=_reviewer(),
    )
    activity_note = service.add_context_note(
        context.lineage.formal_lifecycle_id,
        request_token="activity-note",
        activity_id=context.activity_id,
        statement="This activity is currently performed by one specialist.",
        reviewer=_reviewer(),
    )
    replay = service.add_context_note(
        context.lineage.formal_lifecycle_id,
        request_token="activity-note",
        activity_id=context.activity_id,
        statement="This activity is currently performed by one specialist.",
        reviewer=_reviewer(),
    )
    assert replay.replayed is True
    assert replay.note == activity_note.note
    assert process_note.note.source_spans == ()
    assert process_note.note.formal_value is None
    assert process_note.note.candidate_eligible is False
    assert service.get_review_queue(
        context.lineage.formal_lifecycle_id
    ).progress.review_complete is False
    assert service.get_context_notes(context.lineage.formal_lifecycle_id) == (
        process_note.note,
        activity_note.note,
    )
    assert service.get_context_notes(
        context.lineage.formal_lifecycle_id,
        activity_id=context.activity_id,
    ) == (activity_note.note,)
    with pytest.raises(SupportingEvidenceRequestConflictError):
        service.add_context_note(
            context.lineage.formal_lifecycle_id,
            request_token="activity-note",
            activity_id=context.activity_id,
            statement="Different statement.",
            reviewer=_reviewer(),
        )
    with pytest.raises(SupportingEvidenceLineageError):
        service.add_context_note(
            context.lineage.formal_lifecycle_id,
            request_token="invalid-activity-note",
            activity_id="not-an-approved-activity",
            statement="Invalid activity scope.",
            reviewer=_reviewer(),
        )
    with pytest.raises(SupportingEvidenceInvalidReferenceError):
        service.review_proposal(
            context.lineage.formal_lifecycle_id,
            extraction.proposals[0].proposal_id,
            request_token="note-cannot-support-inference",
            expected_prior_revision_id=None,
            action=ReviewAction.ACCEPT,
            reviewer=_reviewer(),
            selected_category=DocumentCategory.OTHER_ORGANISATIONAL_EVIDENCE,
            approved_classification=EvidenceClassification.REVIEWED_INFERENCE,
            claim_directly_supported_by_excerpt=False,
            inference_confidence=0.5,
            documented_fact_review_ids=(activity_note.note.context_note_id,),
            rationale="Context notes cannot support reviewed inferences.",
        )


def test_queue_fails_closed_for_mixed_proposal_lineage(tmp_path: Path, monkeypatch) -> None:
    context, _, service, _, _, extraction = _setup(tmp_path, claims=1)
    original = context.repository.proposals_for_attempt

    def corrupt(attempt_id: str):
        proposals = original(attempt_id)
        return (
            proposals[0].model_copy(
                update={
                    "lineage": proposals[0].lineage.model_copy(
                        update={"journey_id": "different-journey"}
                    )
                }
            ),
        )

    monkeypatch.setattr(context.repository, "proposals_for_attempt", corrupt)
    with pytest.raises(SupportingEvidenceLineageError):
        service.get_review_queue(context.lineage.formal_lifecycle_id)
    assert extraction.proposals


def test_context_note_failure_is_atomic_and_retryable(tmp_path: Path) -> None:
    context = _prepare(tmp_path)
    ids = StableIds()

    def fail(operation: str) -> None:
        if operation == "APPEND_CONTEXT_NOTE":
            raise RuntimeError("injected")

    repository = SQLiteFormalEvidenceRepository(
        context.path, clock=lambda: NOW, failure_injector=fail
    )
    failing = SupportingEvidenceReviewService(
        repository, clock=lambda: NOW, id_factory=ids
    )
    with pytest.raises(SupportingEvidenceFinalizationError):
        failing.add_context_note(
            context.lineage.formal_lifecycle_id,
            request_token="recoverable-note",
            statement="Context only.",
            reviewer=_reviewer(),
        )
    assert context.repository.context_notes_for_lifecycle(
        context.lineage.formal_lifecycle_id
    ) == ()
    recovered = SupportingEvidenceReviewService(
        context.repository, clock=lambda: NOW, id_factory=ids
    ).add_context_note(
        context.lineage.formal_lifecycle_id,
        request_token="recoverable-note",
        statement="Context only.",
        reviewer=_reviewer(),
    )
    assert recovered.replayed is False


def test_frozen_queue_is_read_only_and_mutations_create_no_sidecars(tmp_path: Path) -> None:
    context, ids, service, _, _, extraction = _setup(tmp_path / "writable", claims=1)
    frozen_directory = tmp_path / "evaluation" / "portfolio" / "slice4-case"
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
    try:
        queue = service.get_review_queue(context.lineage.formal_lifecycle_id)
        assert len(queue.items) == 1
        with pytest.raises(FrozenEvaluationWorkspaceError):
            _fact(service, context, extraction.proposals[0], "frozen-review")
        with pytest.raises(FrozenEvaluationWorkspaceError):
            service.add_context_note(
                context.lineage.formal_lifecycle_id,
                request_token="frozen-note",
                statement="Must not write.",
                reviewer=_reviewer(),
            )
    finally:
        context.repository.path = original_path
    assert snapshot() == before
