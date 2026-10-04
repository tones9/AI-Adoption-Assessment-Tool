from __future__ import annotations

import shutil
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from ai_adoption_engine.models.enums import CriterionName, KnowledgeState
from ai_adoption_engine.models.formal_evidence import (
    CriterionFormalTarget,
    DocumentCategory,
    EvidenceClassification,
    FormalTargetKind,
    ReadinessStatus,
    ReviewAction,
)
from ai_adoption_engine.persistence.formal_evidence import (
    SQLiteFormalEvidenceRepository,
)
from ai_adoption_engine.persistence.workspace_protection import (
    FrozenEvaluationWorkspaceError,
)
from ai_adoption_engine.supporting_evidence.conversion import (
    MappingQueueStatus,
    SupportingEvidenceFormalInputService,
)
from ai_adoption_engine.supporting_evidence.errors import (
    SupportingEvidenceConcurrentPreparationError,
    SupportingEvidenceFinalizationError,
    SupportingEvidenceIncompletePreparationError,
    SupportingEvidenceInvalidMappingError,
    SupportingEvidenceInvalidReferenceError,
    SupportingEvidenceLineageError,
    SupportingEvidenceRequestConflictError,
    SupportingEvidenceStaleCandidateSetError,
    SupportingEvidenceStaleMappingError,
)
from ai_adoption_engine.supporting_evidence.review import (
    SupportingEvidenceReviewService,
)
from tests.integration.test_supporting_evidence_slice3_services import (
    NOW,
    PrefixedIds,
    StableIds,
    _reviewer,
)
from tests.integration.test_supporting_evidence_slice4_review import (
    _extract,
    _fact,
    _setup,
)


def _target() -> CriterionFormalTarget:
    return CriterionFormalTarget(
        kind=FormalTargetKind.CRITERION,
        criterion=CriterionName.REPETITION,
    )


def _conversion(context, ids) -> SupportingEvidenceFormalInputService:
    return SupportingEvidenceFormalInputService(
        context.repository,
        clock=lambda: NOW,
        id_factory=ids,
    )


def _map_fact(service, context, revision, token: str, *, expected=None, value=4):
    return service.map_reviewed_evidence(
        context.lineage.formal_lifecycle_id,
        revision.revision_id,
        request_token=token,
        expected_prior_mapping_id=expected,
        activity_id=context.activity_id,
        target=_target(),
        value=value,
        knowledge_state=KnowledgeState.KNOWN,
        approved_evidence_classification=EvidenceClassification.DOCUMENTED_FACT,
        reviewer=_reviewer(),
        rationale="The reviewer explicitly approves this typed formal value.",
    )


def test_mapping_queue_and_explicit_fact_mapping(tmp_path: Path) -> None:
    context, ids, review, _, _, extraction = _setup(tmp_path, claims=1)
    conversion = _conversion(context, ids)
    assert conversion.get_mapping_queue(
        context.lineage.formal_lifecycle_id
    ).items[0].status is MappingQueueStatus.AWAITING_REVIEW
    fact = _fact(review, context, extraction.proposals[0], "fact-review")
    assert conversion.get_mapping_queue(
        context.lineage.formal_lifecycle_id
    ).items[0].status is MappingQueueStatus.AWAITING_MAPPING
    mapped = _map_fact(conversion, context, fact.revision, "map-fact")
    assert mapped.mapping.value == 4
    assert mapped.mapping.target == _target()
    assert mapped.mapping.knowledge_state is KnowledgeState.KNOWN
    assert conversion.get_mapping_queue(
        context.lineage.formal_lifecycle_id
    ).items[0].status is MappingQueueStatus.MAPPED
    assert conversion.get_mapping_history(
        context.lineage.formal_lifecycle_id
    ) == (mapped.mapping,)


def test_inference_mapping_requires_exact_current_fact_links(tmp_path: Path) -> None:
    context, ids, review, _, _, extraction = _setup(tmp_path, claims=2)
    fact = _fact(review, context, extraction.proposals[0], "fact")
    inference = review.review_proposal(
        context.lineage.formal_lifecycle_id,
        extraction.proposals[1].proposal_id,
        request_token="inference",
        expected_prior_revision_id=None,
        action=ReviewAction.ACCEPT,
        reviewer=_reviewer(),
        selected_category=DocumentCategory.OTHER_ORGANISATIONAL_EVIDENCE,
        approved_classification=EvidenceClassification.REVIEWED_INFERENCE,
        claim_directly_supported_by_excerpt=False,
        inference_confidence=0.7,
        documented_fact_review_ids=(fact.revision.revision_id,),
        rationale="Explicit human inference from the current fact.",
    )
    conversion = _conversion(context, ids)
    with pytest.raises(SupportingEvidenceInvalidMappingError):
        conversion.map_reviewed_evidence(
            context.lineage.formal_lifecycle_id,
            inference.revision.revision_id,
            request_token="bad-inference-map",
            expected_prior_mapping_id=None,
            activity_id=context.activity_id,
            target=_target(),
            value=3,
            knowledge_state=KnowledgeState.INFERRED,
            approved_evidence_classification=EvidenceClassification.REVIEWED_INFERENCE,
            inference_confidence=0.6,
            reviewer=_reviewer(),
            rationale="Missing explicit fact approval.",
        )
    mapped = conversion.map_reviewed_evidence(
        context.lineage.formal_lifecycle_id,
        inference.revision.revision_id,
        request_token="inference-map",
        expected_prior_mapping_id=None,
        activity_id=context.activity_id,
        target=_target(),
        value=3,
        knowledge_state=KnowledgeState.INFERRED,
        approved_evidence_classification=EvidenceClassification.REVIEWED_INFERENCE,
        inference_confidence=0.6,
        supporting_documented_fact_review_ids=(fact.revision.revision_id,),
        reviewer=_reviewer(),
        rationale="Explicit mapping approval retains the exact fact link.",
    )
    assert mapped.mapping.inference_confidence == 0.6


def test_context_only_is_explicit_and_context_notes_cannot_be_mapped(
    tmp_path: Path,
) -> None:
    context, ids, review, _, _, extraction = _setup(tmp_path, claims=1)
    fact = _fact(review, context, extraction.proposals[0], "fact")
    note = review.add_context_note(
        context.lineage.formal_lifecycle_id,
        request_token="note",
        statement="Human context only.",
        reviewer=_reviewer(),
    )
    conversion = _conversion(context, ids)
    decision = conversion.mark_reviewed_evidence_context_only(
        context.lineage.formal_lifecycle_id,
        fact.revision.revision_id,
        request_token="context-only",
        expected_prior_mapping_id=None,
        activity_id=context.activity_id,
        reviewer=_reviewer(),
        rationale="Useful context, but not an approved formal input.",
    )
    assert decision.mapping.target is None
    assert decision.mapping.value is None
    assert conversion.get_mapping_queue(
        context.lineage.formal_lifecycle_id
    ).items[0].status is MappingQueueStatus.CONTEXT_ONLY
    with pytest.raises(SupportingEvidenceInvalidReferenceError):
        conversion.map_reviewed_evidence(
            context.lineage.formal_lifecycle_id,
            note.note.context_note_id,
            request_token="map-note",
            expected_prior_mapping_id=None,
            activity_id=context.activity_id,
            target=_target(),
            value=3,
            knowledge_state=KnowledgeState.KNOWN,
            approved_evidence_classification=EvidenceClassification.DOCUMENTED_FACT,
            reviewer=_reviewer(),
            rationale="Context notes are not reviewed evidence.",
        )


def test_rejected_unknown_and_conflict_remain_non_positive(tmp_path: Path) -> None:
    context, ids, review, _, _, extraction = _setup(tmp_path, claims=5)
    first = _fact(review, context, extraction.proposals[0], "first")
    second = _fact(review, context, extraction.proposals[1], "second")
    rejected = review.review_proposal(
        context.lineage.formal_lifecycle_id,
        extraction.proposals[2].proposal_id,
        request_token="reject",
        expected_prior_revision_id=None,
        action=ReviewAction.REJECT,
        reviewer=_reviewer(),
        rationale="Audit only.",
    )
    unknown = review.review_proposal(
        context.lineage.formal_lifecycle_id,
        extraction.proposals[3].proposal_id,
        request_token="unknown",
        expected_prior_revision_id=None,
        action=ReviewAction.MARK_UNRESOLVED,
        reviewer=_reviewer(),
        approved_claim="The value remains unknown.",
        selected_category=DocumentCategory.OTHER_ORGANISATIONAL_EVIDENCE,
        approved_classification=EvidenceClassification.UNKNOWN,
        rationale="No value is established.",
    )
    conflict = review.review_proposal(
        context.lineage.formal_lifecycle_id,
        extraction.proposals[4].proposal_id,
        request_token="conflict",
        expected_prior_revision_id=None,
        action=ReviewAction.MARK_UNRESOLVED,
        reviewer=_reviewer(),
        approved_claim="The current facts conflict.",
        selected_category=DocumentCategory.OTHER_ORGANISATIONAL_EVIDENCE,
        approved_classification=EvidenceClassification.CONFLICT,
        competing_review_ids=(
            first.revision.revision_id,
            second.revision.revision_id,
        ),
        rationale="Both sides remain unresolved.",
    )
    conversion = _conversion(context, ids)
    for entry in conversion.get_mapping_queue(context.lineage.formal_lifecycle_id).items:
        if entry.review_revision is not None and entry.review_revision.action is ReviewAction.REJECT:
            assert entry.status is MappingQueueStatus.REJECTED_AUDIT_ONLY
        elif entry.review_revision is not None and entry.review_revision.approved_classification in {
            EvidenceClassification.UNKNOWN,
            EvidenceClassification.CONFLICT,
        }:
            assert entry.status is MappingQueueStatus.UNRESOLVED
    _map_fact(conversion, context, first.revision, "map-first")
    _map_fact(conversion, context, second.revision, "map-second")
    candidate = conversion.prepare_candidate_set(
        context.lineage.formal_lifecycle_id,
        request_token="partitioned-candidate",
    ).candidate_set
    assert candidate.retained_unknown_review_revision_ids == (
        unknown.revision.revision_id,
    )
    assert candidate.retained_conflict_review_revision_ids == (
        conflict.revision.revision_id,
    )
    assert tuple(
        item.proposal_id for item in candidate.rejected_or_excluded_proposals
    ) == (rejected.revision.proposal_id,)


def test_mapping_replay_conflict_predecessor_and_revision_staleness(
    tmp_path: Path,
) -> None:
    context, ids, review, _, _, extraction = _setup(tmp_path, claims=1)
    fact = _fact(review, context, extraction.proposals[0], "fact")
    conversion = _conversion(context, ids)
    first = _map_fact(conversion, context, fact.revision, "map")
    replay = _map_fact(conversion, context, fact.revision, "map")
    assert replay.replayed is True
    assert replay.mapping == first.mapping
    with pytest.raises(SupportingEvidenceRequestConflictError):
        _map_fact(conversion, context, fact.revision, "map", value=2)
    with pytest.raises(SupportingEvidenceStaleMappingError):
        _map_fact(conversion, context, fact.revision, "new-map")
    replaced = _map_fact(
        conversion,
        context,
        fact.revision,
        "replacement-map",
        expected=first.mapping.mapping_id,
        value=2,
    )
    assert replaced.mapping.mapping_id != first.mapping.mapping_id
    revised = _fact(
        review,
        context,
        extraction.proposals[0],
        "revised-review",
        expected=fact.revision.revision_id,
        action=ReviewAction.CORRECT,
        claim="Revised current fact wording.",
    )
    historical_replay = _map_fact(
        conversion,
        context,
        fact.revision,
        "map",
    )
    assert historical_replay.replayed is True
    assert historical_replay.mapping == first.mapping
    queue = conversion.get_mapping_queue(context.lineage.formal_lifecycle_id)
    assert queue.items[0].review_revision == revised.revision
    assert queue.items[0].status is MappingQueueStatus.AWAITING_MAPPING
    assert any(
        item.current_mapping == replaced.mapping for item in queue.audit_history
    )


def test_candidate_set_and_ready_to_attempt_snapshot(tmp_path: Path) -> None:
    context, ids, review, _, _, extraction = _setup(tmp_path, claims=1)
    fact = _fact(review, context, extraction.proposals[0], "fact")
    conversion = _conversion(context, ids)
    mapping = _map_fact(conversion, context, fact.revision, "map")
    candidate = conversion.prepare_candidate_set(
        context.lineage.formal_lifecycle_id,
        request_token="candidate",
    )
    assert candidate.candidate_set.ordered_formal_mappings == (mapping.mapping,)
    readiness = conversion.evaluate_and_persist_readiness(
        context.lineage.formal_lifecycle_id,
        candidate.candidate_set.candidate_set_id,
        request_token="readiness",
    )
    assert readiness.readiness.status is ReadinessStatus.READY_TO_ATTEMPT
    assert readiness.readiness.reasons == ()
    state = conversion.get_current_preparation_state(
        context.lineage.formal_lifecycle_id
    )
    assert state.candidate_set_current is True
    assert state.effective_status is ReadinessStatus.READY_TO_ATTEMPT
    assert state.warnings


def test_candidate_requires_complete_review_and_mapping_without_partial_write(
    tmp_path: Path,
) -> None:
    context, ids, review, _, _, extraction = _setup(tmp_path, claims=2)
    fact = _fact(review, context, extraction.proposals[0], "fact")
    conversion = _conversion(context, ids)
    with pytest.raises(SupportingEvidenceIncompletePreparationError) as error:
        conversion.prepare_candidate_set(
            context.lineage.formal_lifecycle_id,
            request_token="incomplete",
        )
    assert error.value.blockers == (
        f"REVIEW_AWAITING_MAPPING:{fact.revision.revision_id}",
        f"PROPOSAL_UNREVIEWED:{extraction.proposals[1].proposal_id}",
    )
    assert context.repository.candidate_sets_for_lifecycle(
        context.lineage.formal_lifecycle_id
    ) == ()


def test_explicit_document_exclusion_never_silently_omits(tmp_path: Path) -> None:
    context, ids, review, _, _, first_extraction = _setup(tmp_path, claims=1)
    fact = _fact(review, context, first_extraction.proposals[0], "fact")
    conversion = _conversion(context, ids)
    _map_fact(conversion, context, fact.revision, "map")
    second, _, _ = _extract(
        context,
        ids,
        intake_token="second-document",
        content=b"Second evidence.",
        claims=("Unreviewed excluded claim.",),
    )
    with pytest.raises(SupportingEvidenceIncompletePreparationError):
        conversion.prepare_candidate_set(
            context.lineage.formal_lifecycle_id,
            request_token="not-excluded",
        )
    candidate = conversion.prepare_candidate_set(
        context.lineage.formal_lifecycle_id,
        request_token="excluded",
        explicitly_excluded_document_ids=(second.document.document_id,),
    ).candidate_set
    assert second.document.document_id in {
        item.document_id for item in candidate.current_documents
    }
    assert candidate.explicitly_excluded_document_ids == (
        second.document.document_id,
    )
    assert second.document.document_id in {
        item.document_id for item in candidate.current_extractions
    }
    assert candidate.rejected_or_excluded_proposals


def test_context_only_complete_candidate_is_not_ready_without_positive_value(
    tmp_path: Path,
) -> None:
    context, ids, review, _, _, extraction = _setup(tmp_path, claims=1)
    fact = _fact(review, context, extraction.proposals[0], "fact")
    conversion = _conversion(context, ids)
    conversion.mark_reviewed_evidence_context_only(
        context.lineage.formal_lifecycle_id,
        fact.revision.revision_id,
        request_token="context",
        expected_prior_mapping_id=None,
        activity_id=context.activity_id,
        reviewer=_reviewer(),
        rationale="Explicitly retained as context only.",
    )
    candidate = conversion.prepare_candidate_set(
        context.lineage.formal_lifecycle_id,
        request_token="candidate",
    ).candidate_set
    readiness = conversion.evaluate_and_persist_readiness(
        context.lineage.formal_lifecycle_id,
        candidate.candidate_set_id,
        request_token="readiness",
    ).readiness
    assert readiness.status is ReadinessStatus.NOT_READY
    assert readiness.reasons == ("NO_POSITIVE_MAPPED_FORMAL_VALUE",)


def test_later_mapping_makes_candidate_and_readiness_stale(tmp_path: Path) -> None:
    context, ids, review, _, _, extraction = _setup(tmp_path, claims=1)
    fact = _fact(review, context, extraction.proposals[0], "fact")
    conversion = _conversion(context, ids)
    initial = _map_fact(conversion, context, fact.revision, "map")
    candidate = conversion.prepare_candidate_set(
        context.lineage.formal_lifecycle_id,
        request_token="candidate",
    ).candidate_set
    conversion.evaluate_and_persist_readiness(
        context.lineage.formal_lifecycle_id,
        candidate.candidate_set_id,
        request_token="readiness",
    )
    _map_fact(
        conversion,
        context,
        fact.revision,
        "remap",
        expected=initial.mapping.mapping_id,
        value=2,
    )
    state = conversion.get_current_preparation_state(
        context.lineage.formal_lifecycle_id
    )
    assert state.candidate_set_current is False
    assert state.effective_status is ReadinessStatus.NOT_READY
    with pytest.raises(SupportingEvidenceStaleCandidateSetError):
        conversion.evaluate_and_persist_readiness(
            context.lineage.formal_lifecycle_id,
            candidate.candidate_set_id,
            request_token="stale-readiness",
        )


def test_candidate_and_readiness_replay_survive_restart(tmp_path: Path) -> None:
    context, ids, review, _, _, extraction = _setup(tmp_path, claims=1)
    fact = _fact(review, context, extraction.proposals[0], "fact")
    service = _conversion(context, ids)
    _map_fact(service, context, fact.revision, "map")
    candidate = service.prepare_candidate_set(
        context.lineage.formal_lifecycle_id,
        request_token="candidate",
    )
    readiness = service.evaluate_and_persist_readiness(
        context.lineage.formal_lifecycle_id,
        candidate.candidate_set.candidate_set_id,
        request_token="readiness",
    )
    restarted = SupportingEvidenceFormalInputService(
        SQLiteFormalEvidenceRepository(context.path, clock=lambda: NOW),
        clock=lambda: NOW,
        id_factory=ids,
    )
    assert restarted.prepare_candidate_set(
        context.lineage.formal_lifecycle_id,
        request_token="candidate",
    ).replayed is True
    with pytest.raises(SupportingEvidenceRequestConflictError):
        restarted.prepare_candidate_set(
            context.lineage.formal_lifecycle_id,
            request_token="candidate",
            explicitly_excluded_document_ids=(
                candidate.candidate_set.current_documents[0].document_id,
            ),
        )
    assert restarted.evaluate_and_persist_readiness(
        context.lineage.formal_lifecycle_id,
        candidate.candidate_set.candidate_set_id,
        request_token="readiness",
    ).readiness == readiness.readiness
    with pytest.raises(SupportingEvidenceRequestConflictError):
        restarted.evaluate_and_persist_readiness(
            context.lineage.formal_lifecycle_id,
            "different-candidate-set",
            request_token="readiness",
        )


def test_concurrent_candidate_preparation_has_one_winner(tmp_path: Path) -> None:
    context, _, review, _, _, extraction = _setup(tmp_path, claims=1)
    fact = _fact(review, context, extraction.proposals[0], "fact")
    seed = SupportingEvidenceFormalInputService(context.repository, clock=lambda: NOW)
    _map_fact(seed, context, fact.revision, "map")
    barrier = threading.Barrier(2)

    def run(namespace: str):
        repository = SQLiteFormalEvidenceRepository(context.path, clock=lambda: NOW)
        original_append = repository.append_candidate_set

        def synchronized_append(candidate, *, terminal_event=None):
            barrier.wait()
            return original_append(candidate, terminal_event=terminal_event)

        repository.append_candidate_set = synchronized_append  # type: ignore[method-assign]
        service = SupportingEvidenceFormalInputService(
            repository,
            clock=lambda: NOW,
            id_factory=PrefixedIds(namespace),
        )
        try:
            return service.prepare_candidate_set(
                context.lineage.formal_lifecycle_id,
                request_token=f"candidate-{namespace}",
            )
        except Exception as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, ("one", "two")))
    assert sum(hasattr(item, "candidate_set") for item in results) == 1
    assert sum(
        isinstance(item, SupportingEvidenceConcurrentPreparationError)
        for item in results
    ) == 1


def test_concurrent_mapping_has_one_winner(tmp_path: Path) -> None:
    context, _, review, _, _, extraction = _setup(tmp_path, claims=1)
    fact = _fact(review, context, extraction.proposals[0], "fact")
    barrier = threading.Barrier(2)

    def run(namespace: str):
        repository = SQLiteFormalEvidenceRepository(context.path, clock=lambda: NOW)
        original_append = repository.append_formal_mapping

        def synchronized_append(
            mapping,
            *,
            expected_prior_mapping_id=None,
            terminal_event=None,
        ):
            barrier.wait()
            return original_append(
                mapping,
                expected_prior_mapping_id=expected_prior_mapping_id,
                terminal_event=terminal_event,
            )

        repository.append_formal_mapping = synchronized_append  # type: ignore[method-assign]
        service = SupportingEvidenceFormalInputService(
            repository,
            clock=lambda: NOW,
            id_factory=PrefixedIds(namespace),
        )
        try:
            return _map_fact(
                service,
                context,
                fact.revision,
                f"mapping-{namespace}",
            )
        except Exception as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, ("one", "two")))
    assert sum(hasattr(item, "mapping") for item in results) == 1
    assert sum(
        isinstance(item, SupportingEvidenceConcurrentPreparationError)
        for item in results
    ) == 1


def test_corrupt_mapping_history_fails_closed(tmp_path: Path, monkeypatch) -> None:
    context, ids, review, _, _, extraction = _setup(tmp_path, claims=1)
    fact = _fact(review, context, extraction.proposals[0], "fact")
    service = _conversion(context, ids)
    mapping = _map_fact(service, context, fact.revision, "map").mapping
    monkeypatch.setattr(
        context.repository,
        "formal_mappings_for_lifecycle",
        lambda formal_lifecycle_id: (
            mapping.model_copy(
                update={
                    "lineage": mapping.lineage.model_copy(
                        update={"journey_id": "corrupt-journey"}
                    )
                }
            ),
        ),
    )
    with pytest.raises(SupportingEvidenceLineageError) as error:
        service.get_mapping_queue(context.lineage.formal_lifecycle_id)
    assert "lineage" in str(error.value).lower()


@pytest.mark.parametrize(
    ("operation", "table"),
    [
        ("APPEND_FORMAL_MAPPING", "preliminary_supporting_formal_input_mappings"),
        ("APPEND_CANDIDATE_SET", "preliminary_supporting_formal_input_candidate_sets"),
        ("APPEND_READINESS", "preliminary_supporting_formal_evidence_readiness"),
    ],
)
def test_injected_failures_leave_no_partial_operation_history(
    tmp_path: Path,
    operation: str,
    table: str,
) -> None:
    context, ids, review, _, _, extraction = _setup(tmp_path, claims=1)
    fact = _fact(review, context, extraction.proposals[0], "fact")

    def fail(name: str) -> None:
        if name == operation:
            raise RuntimeError("injected")

    failing_repo = SQLiteFormalEvidenceRepository(
        context.path,
        clock=lambda: NOW,
        failure_injector=fail,
    )
    failing = SupportingEvidenceFormalInputService(
        failing_repo,
        clock=lambda: NOW,
        id_factory=ids,
    )
    if operation == "APPEND_FORMAL_MAPPING":
        before_events = len(
            context.repository.list_records(
                "formal-evidence-workflow-event.v0.1",
                formal_lifecycle_id=context.lineage.formal_lifecycle_id,
            )
        )
        with pytest.raises(SupportingEvidenceFinalizationError):
            _map_fact(failing, context, fact.revision, "failed-map")
    else:
        working = _conversion(context, ids)
        mapping = _map_fact(working, context, fact.revision, "map")
        if operation == "APPEND_CANDIDATE_SET":
            before_events = len(
                context.repository.list_records(
                    "formal-evidence-workflow-event.v0.1",
                    formal_lifecycle_id=context.lineage.formal_lifecycle_id,
                )
            )
            with pytest.raises(SupportingEvidenceFinalizationError):
                failing.prepare_candidate_set(
                    context.lineage.formal_lifecycle_id,
                    request_token="failed-candidate",
                )
        else:
            candidate = working.prepare_candidate_set(
                context.lineage.formal_lifecycle_id,
                request_token="candidate",
            ).candidate_set
            assert mapping.mapping
            before_events = len(
                context.repository.list_records(
                    "formal-evidence-workflow-event.v0.1",
                    formal_lifecycle_id=context.lineage.formal_lifecycle_id,
                )
            )
            with pytest.raises(SupportingEvidenceFinalizationError):
                failing.evaluate_and_persist_readiness(
                    context.lineage.formal_lifecycle_id,
                    candidate.candidate_set_id,
                    request_token="failed-readiness",
                )
    connection = sqlite3.connect(context.path)
    try:
        request_token = {
            "APPEND_FORMAL_MAPPING": "failed-map",
            "APPEND_CANDIDATE_SET": "failed-candidate",
            "APPEND_READINESS": "failed-readiness",
        }[operation]
        assert connection.execute(
            "SELECT COUNT(*) FROM preliminary_supporting_operation_requests WHERE request_token = ?",
            (request_token,),
        ).fetchone()[0] == 0
        if operation == "APPEND_FORMAL_MAPPING":
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        elif operation == "APPEND_CANDIDATE_SET":
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        else:
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    finally:
        connection.close()
    assert len(
        context.repository.list_records(
            "formal-evidence-workflow-event.v0.1",
            formal_lifecycle_id=context.lineage.formal_lifecycle_id,
        )
    ) == before_events


def test_frozen_inspection_and_mutation_invariance(tmp_path: Path) -> None:
    context, ids, review, _, _, extraction = _setup(tmp_path / "writable", claims=1)
    fact = _fact(review, context, extraction.proposals[0], "fact")
    service = _conversion(context, ids)
    _map_fact(service, context, fact.revision, "map")
    frozen_dir = tmp_path / "evaluation" / "portfolio" / "slice5-case"
    frozen_dir.mkdir(parents=True)
    frozen_path = frozen_dir / "workspace.db"
    shutil.copy2(context.path, frozen_path)

    def snapshot() -> dict[str, bytes]:
        return {
            item.name: item.read_bytes()
            for item in sorted(frozen_dir.iterdir())
            if item.is_file()
        }

    before = snapshot()
    original = context.repository.path
    context.repository.path = frozen_path
    try:
        state = service.get_current_preparation_state(
            context.lineage.formal_lifecycle_id
        )
        assert state.mapping_queue.items[0].status is MappingQueueStatus.MAPPED
        with pytest.raises(FrozenEvaluationWorkspaceError):
            service.prepare_candidate_set(
                context.lineage.formal_lifecycle_id,
                request_token="frozen-candidate",
            )
    finally:
        context.repository.path = original
    assert snapshot() == before
