from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from ai_adoption_engine.decision.four_gate_engine import FourGateAssessmentEngine
from ai_adoption_engine.formal.input_adapter import FormalFourGateInputAdapter
from ai_adoption_engine.formal.run_service import (
    FormalAssessmentRunService,
    FormalRunCompleted,
    FormalRunFailureCode,
    FormalRunPreRunRejection,
    FormalRunRecoveryRequired,
    FormalRunTerminalFailure,
)
from ai_adoption_engine.models.formal_assessment import FormalRunStatus
from ai_adoption_engine.models.formal_assessment import (
    FORMAL_ASSESSMENT_AUTHORIZATION_SCHEMA,
    FORMAL_ASSESSMENT_INPUT_CHOICE_SCHEMA,
    FORMAL_ASSESSMENT_RUN_STORE_ID,
    ApprovedProcessAuthorizationPin,
    FormalAssessmentAuthorization,
    FormalAssessmentInputChoice,
    FormalAssessmentInputMode,
    FormalRunLineage,
    SupportingEvidenceCandidatePin,
    SupportingEvidenceDisposition,
)
from ai_adoption_engine.models.formal_evidence import (
    FORMAL_EVIDENCE_FAMILY,
    FORMAL_EVIDENCE_READINESS_SCHEMA,
    FormalEvidenceReadiness,
    ReadinessStatus,
)
from ai_adoption_engine.persistence.formal_assessment import (
    SQLiteFormalAssessmentRepository,
)
from ai_adoption_engine.persistence.formal_assessment_serialization import (
    serialize_formal_assessment_record,
)
from ai_adoption_engine.persistence.formal_evidence import SQLiteFormalEvidenceRepository
from ai_adoption_engine.persistence.formal_evidence_serialization import (
    serialize_formal_evidence_record,
)
from tests.integration.test_formal_assessment_persistence import (
    NOW,
    prepare,
    projection,
    request,
)
from tests.integration.test_formal_evidence_persistence import (
    EvidenceContext,
    _candidate,
    _extraction,
    _ingestion,
    _mapping,
    _review,
    _store_document,
)
from tests.unit.test_formal_assessment_models import compatibility


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "config/decision_policy.v0.3.json"


class CountingAdapter(FormalFourGateInputAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def project(self, **kwargs):
        self.calls += 1
        return super().project(**kwargs)


@dataclass
class CountingEngine(FourGateAssessmentEngine):
    policy: object
    calls: int = 0
    received: object | None = None

    def assess(self, process):
        self.calls += 1
        self.received = process
        return super().assess(process)


class FailingEngine(FourGateAssessmentEngine):
    def assess(self, process):
        del process
        raise RuntimeError("engine unavailable")


class MutatingEngine(FourGateAssessmentEngine):
    def assess(self, process):
        result = super().assess(process)
        return result.model_copy(update={"process_name": "Mutated engine output"})


def ids(namespace: str = ""):
    counter = 0

    def factory(prefix: str) -> str:
        nonlocal counter
        counter += 1
        return f"{prefix}-{namespace}{counter}"

    return factory


def service(context, *, adapter=None, engine_factory=CountingEngine, id_namespace: str = ""):
    return FormalAssessmentRunService(
        context.repository,
        policy_path=POLICY_PATH,
        adapter=adapter,
        engine_factory=engine_factory,
        clock=lambda: NOW,
        id_factory=ids(id_namespace),
    )


def test_process_only_run_is_explicit_strict_and_replays_without_reinvocation(
    tmp_path: Path,
) -> None:
    context = prepare(tmp_path)
    expected = projection(context)
    adapter = CountingAdapter()
    engines: list[CountingEngine] = []

    def factory(policy):
        engine = CountingEngine(policy)
        engines.append(engine)
        return engine

    run_service = service(context, adapter=adapter, engine_factory=factory)
    first = run_service.execute(
        expected.authorization,
        approved_review=context.approved,
        request=request("run-process-only"),
    )
    assert isinstance(first, FormalRunCompleted)
    assert first.result.customer_status == "Organisational assessment completed — review required"
    assert first.result.implementation_approval_granted is False
    assert first.result.decision_package_generated is False
    assert adapter.calls == 1
    assert len(engines) == 1 and engines[0].calls == 1
    assert engines[0].received == expected.engine_input
    assert tuple(item.activity_id for item in first.result.activity_traces) == tuple(
        item.activity_id for item in expected.activities
    )
    assert len(context.repository.load_run_events(expected.run_lineage.run_id)) == 2
    assert context.repository.load_authorization(
        expected.authorization.authorization_id
    ) == expected.authorization
    assert context.repository.load_projection(expected.projection_id) == expected
    assert context.repository.load_manifest(expected.run_lineage.run_id).projection == expected
    assert context.repository.load_run_state(
        expected.run_lineage.run_id
    ).current_status is FormalRunStatus.COMPLETED_PENDING_REVIEW
    assert context.repository.load_terminal_record(first.result.result_id) == first.result
    connection = sqlite3.connect(context.path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM preliminary_supporting_documents"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM preliminary_supporting_formal_input_candidate_sets"
        ).fetchone()[0] == 0
    finally:
        connection.close()

    replay = run_service.execute(
        expected.authorization,
        approved_review=context.approved,
        request=request("run-process-only"),
    )
    assert isinstance(replay, FormalRunCompleted)
    assert replay.replayed and replay.result == first.result
    assert adapter.calls == 1
    assert engines[0].calls == 1

    restarted = FormalAssessmentRunService(
        SQLiteFormalAssessmentRepository(context.path, clock=lambda: NOW),
        policy_path=POLICY_PATH,
        adapter=CountingAdapter(),
        engine_factory=factory,
        clock=lambda: NOW,
        id_factory=ids(),
    )
    after_restart = restarted.execute(
        expected.authorization,
        approved_review=context.approved,
        request=request("run-process-only"),
    )
    assert isinstance(after_restart, FormalRunCompleted)
    assert after_restart.replayed and after_restart.result == first.result
    assert len(engines) == 1


def test_adapter_rejection_creates_no_manifest_or_engine_work(tmp_path: Path) -> None:
    context = prepare(tmp_path)
    expected = projection(context)
    adapter = CountingAdapter()
    engines: list[CountingEngine] = []

    def factory(policy):
        engine = CountingEngine(policy)
        engines.append(engine)
        return engine

    invalid_review = context.approved.model_copy(
        update={
            "business_process": context.approved.business_process.model_copy(
                update={"name": "Different process"}
            )
        }
    )
    outcome = service(context, adapter=adapter, engine_factory=factory).execute(
        expected.authorization,
        approved_review=invalid_review,
        request=request("adapter-rejected"),
    )
    assert isinstance(outcome, FormalRunPreRunRejection)
    assert outcome.code is FormalRunFailureCode.ADAPTER_PROJECTION_REJECTED
    assert adapter.calls == 1
    assert not engines
    assert context.repository.run_history(expected.run_lineage.run_id).manifests == ()


def test_policy_drift_rejects_before_adapter_or_engine(tmp_path: Path) -> None:
    context = prepare(tmp_path)
    expected = projection(context)
    adapter = CountingAdapter()
    engines: list[CountingEngine] = []

    def factory(policy):
        engine = CountingEngine(policy)
        engines.append(engine)
        return engine

    def drifted_loader(path):
        from ai_adoption_engine.decision.four_gate_policy import load_four_gate_policy

        return load_four_gate_policy(path).model_copy(
            update={"description": "same identity, different policy bytes"}
        )

    run_service = FormalAssessmentRunService(
        context.repository,
        policy_path=POLICY_PATH,
        adapter=adapter,
        policy_loader=drifted_loader,
        engine_factory=factory,
        clock=lambda: NOW,
        id_factory=ids(),
    )
    outcome = run_service.execute(
        expected.authorization,
        approved_review=context.approved,
        request=request("policy-drift"),
    )

    assert isinstance(outcome, FormalRunPreRunRejection)
    assert outcome.code is FormalRunFailureCode.COMPATIBILITY_OR_POLICY_DRIFT
    assert adapter.calls == 0
    assert not engines
    assert context.repository.run_history(expected.run_lineage.run_id).manifests == ()


def test_invalid_engine_output_is_persisted_as_terminal_failure(tmp_path: Path) -> None:
    context = prepare(tmp_path)
    expected = projection(context)
    outcome = service(
        context,
        engine_factory=lambda policy: MutatingEngine(policy),
    ).execute(
        expected.authorization,
        approved_review=context.approved,
        request=request("mutated-engine-output"),
    )

    assert isinstance(outcome, FormalRunTerminalFailure)
    assert outcome.terminal_failure.failure.code == "INVALID_ENGINE_OUTPUT"
    assert outcome.terminal_failure.assessment is None
    history = context.repository.run_history(expected.run_lineage.run_id)
    assert not [
        item
        for item in history.terminal_records
        if hasattr(item, "assessment") and item.assessment
    ]


def test_start_persistence_failure_rolls_back_before_engine_invocation(tmp_path: Path) -> None:
    def inject(stage: str) -> None:
        if stage == "CREATE_MANIFEST_AND_START":
            raise RuntimeError("injected start failure")

    context = prepare(tmp_path, failure_injector=inject)
    expected = projection(context)
    engines: list[CountingEngine] = []

    def factory(policy):
        engine = CountingEngine(policy)
        engines.append(engine)
        return engine

    outcome = service(context, engine_factory=factory).execute(
        expected.authorization,
        approved_review=context.approved,
        request=request("start-failure"),
    )

    assert isinstance(outcome, FormalRunPreRunRejection)
    assert outcome.code is FormalRunFailureCode.START_PERSISTENCE_FAILED
    assert not engines
    assert context.repository.run_history(expected.run_lineage.run_id).manifests == ()


def test_conflicting_root_request_token_never_reinvokes_adapter_or_engine(
    tmp_path: Path,
) -> None:
    context = prepare(tmp_path)
    first_projection = projection(context)
    adapter = CountingAdapter()
    engines: list[CountingEngine] = []

    def factory(policy):
        engine = CountingEngine(policy)
        engines.append(engine)
        return engine

    run_service = service(context, adapter=adapter, engine_factory=factory)
    root_request = request("conflicting-root-request")
    first = run_service.execute(
        first_projection.authorization,
        approved_review=context.approved,
        request=root_request,
    )
    assert isinstance(first, FormalRunCompleted)
    later_projection = projection(
        context,
        run_id="conflict-run",
        authorization_id="conflict-authorization",
        projection_id="conflict-projection",
        token_suffix="conflict",
    )
    conflicting = run_service.execute(
        later_projection.authorization,
        approved_review=context.approved,
        request=root_request,
    )

    assert isinstance(conflicting, FormalRunPreRunRejection)
    assert conflicting.code is FormalRunFailureCode.STALE_OR_CONFLICTING_REQUEST
    assert adapter.calls == 1
    assert len(engines) == 1 and engines[0].calls == 1


def test_frozen_workspace_refuses_before_adapter_or_engine(tmp_path: Path) -> None:
    source = prepare(tmp_path / "source")
    expected = projection(source)
    frozen_path = tmp_path / "evaluation" / "portfolio" / "frozen" / "workspace.db"
    frozen_path.parent.mkdir(parents=True)
    shutil.copy2(source.path, frozen_path)
    frozen_repository = SQLiteFormalAssessmentRepository(frozen_path, read_only=True)
    adapter = CountingAdapter()
    engines: list[CountingEngine] = []

    def factory(policy):
        engine = CountingEngine(policy)
        engines.append(engine)
        return engine

    outcome = FormalAssessmentRunService(
        frozen_repository,
        policy_path=POLICY_PATH,
        adapter=adapter,
        engine_factory=factory,
        clock=lambda: NOW,
        id_factory=ids(),
    ).execute(
        expected.authorization,
        approved_review=source.approved,
        request=request("frozen-run"),
    )

    assert isinstance(outcome, FormalRunPreRunRejection)
    assert outcome.code is FormalRunFailureCode.REPOSITORY_INTEGRITY_FAILED
    assert adapter.calls == 0
    assert not engines


def test_engine_failure_is_immutable_terminal_then_retry_reuses_projection(
    tmp_path: Path,
) -> None:
    context = prepare(tmp_path)
    expected = projection(context)
    adapter = CountingAdapter()
    run_service = service(
        context,
        adapter=adapter,
        engine_factory=lambda policy: FailingEngine(policy),
    )
    failed = run_service.execute(
        expected.authorization,
        approved_review=context.approved,
        request=request("engine-failure"),
    )
    assert isinstance(failed, FormalRunTerminalFailure)
    assert failed.terminal_failure.status is FormalRunStatus.FAILED
    assert failed.terminal_failure.assessment is None
    assert adapter.calls == 1

    retry_available = run_service.mark_retry_available(
        expected.authorization,
        request=request("retry-available"),
    )
    assert isinstance(retry_available, FormalRunRecoveryRequired)
    assert retry_available.state.current_status is FormalRunStatus.RETRY_AVAILABLE

    retry_engines: list[CountingEngine] = []

    def retry_factory(policy):
        engine = CountingEngine(policy)
        retry_engines.append(engine)
        return engine

    retry_service = service(context, adapter=adapter, engine_factory=retry_factory)
    retried = retry_service.retry(
        expected.authorization,
        request=request("retry-run"),
    )
    assert isinstance(retried, FormalRunCompleted)
    assert adapter.calls == 1
    assert retry_engines[0].calls == 1
    retry_replay = retry_service.retry(
        expected.authorization,
        request=request("retry-run"),
    )
    assert isinstance(retry_replay, FormalRunCompleted)
    assert retry_replay.replayed
    assert retry_engines[0].calls == 1
    history = context.repository.run_history(expected.run_lineage.run_id)
    assert len(history.manifests) == 2
    assert history.manifests[1].projection == history.manifests[0].projection
    assert (
        history.manifests[1].authorization.input_choice.mode
        is history.manifests[0].authorization.input_choice.mode
    )


def test_final_write_failure_requires_explicit_recovery_without_engine_retry(
    tmp_path: Path,
) -> None:
    def inject(stage: str) -> None:
        if stage == "APPEND_RUN_EVENT":
            raise RuntimeError("final write failure")

    context = prepare(tmp_path, failure_injector=inject)
    expected = projection(context)
    adapter = CountingAdapter()
    engines: list[CountingEngine] = []

    def factory(policy):
        engine = CountingEngine(policy)
        engines.append(engine)
        return engine

    run_service = service(context, adapter=adapter, engine_factory=factory)
    outcome = run_service.execute(
        expected.authorization,
        approved_review=context.approved,
        request=request("terminal-write-failure"),
    )
    assert isinstance(outcome, FormalRunRecoveryRequired)
    assert outcome.code is FormalRunFailureCode.TERMINAL_PERSISTENCE_FAILED
    assert engines[0].calls == 1
    assert context.repository.load_run_state(
        expected.run_lineage.run_id
    ).current_status is FormalRunStatus.RUNNING

    replay = run_service.execute(
        expected.authorization,
        approved_review=context.approved,
        request=request("terminal-write-failure"),
    )
    assert isinstance(replay, FormalRunRecoveryRequired)
    assert engines[0].calls == 1


def test_interruption_is_recoverable_then_abandonment_is_terminal(tmp_path: Path) -> None:
    def inject(stage: str) -> None:
        if stage == "APPEND_RUN_EVENT":
            raise RuntimeError("final write failure")

    context = prepare(tmp_path, failure_injector=inject)
    expected = projection(context)
    first = service(context).execute(
        expected.authorization,
        approved_review=context.approved,
        request=request("interrupt-root"),
    )
    assert isinstance(first, FormalRunRecoveryRequired)

    repository = SQLiteFormalAssessmentRepository(context.path, clock=lambda: NOW)
    recovered = FormalAssessmentRunService(
        repository,
        policy_path=POLICY_PATH,
        clock=lambda: NOW,
        id_factory=ids(),
    )
    interrupted = recovered.interrupt_running(
        expected.authorization,
        request=request("interrupt"),
    )
    assert isinstance(interrupted, FormalRunRecoveryRequired)
    assert interrupted.state.current_status is FormalRunStatus.INTERRUPTED
    assert context.repository.run_history(
        expected.run_lineage.run_id
    ).terminal_records == ()

    abandoned = recovered.abandon(
        expected.authorization,
        request=request("abandon"),
        rationale="The interrupted attempt is deliberately closed.",
    )
    assert isinstance(abandoned, FormalRunTerminalFailure)
    assert abandoned.terminal_failure.status is FormalRunStatus.ABANDONED


def test_later_success_requires_explicit_immutable_supersession(tmp_path: Path) -> None:
    context = prepare(tmp_path)
    first_projection = projection(context)
    first = service(context).execute(
        first_projection.authorization,
        approved_review=context.approved,
        request=request("first-success"),
    )
    assert isinstance(first, FormalRunCompleted)
    later_projection = projection(
        context,
        run_id="later-run",
        authorization_id="later-authorization",
        projection_id="later-projection",
        token_suffix="later",
    )
    second_service = service(context, id_namespace="later-")
    second = second_service.execute(
        later_projection.authorization,
        approved_review=context.approved,
        request=request("later-success"),
    )
    assert isinstance(second, FormalRunCompleted)
    superseded = second_service.supersede_result(
        predecessor_result_id=first.result.result_id,
        successor_result_id=second.result.result_id,
        request=request("supersede-success"),
        rationale="A later explicit completed assessment replaces the current head.",
    )
    assert isinstance(superseded, FormalRunCompleted)
    supersession_replay = second_service.supersede_result(
        predecessor_result_id=first.result.result_id,
        successor_result_id=second.result.result_id,
        request=request("supersede-success"),
        rationale="A later explicit completed assessment replaces the current head.",
    )
    assert isinstance(supersession_replay, FormalRunCompleted)
    assert supersession_replay.replayed
    assert context.repository.current_successful_result(
        first_projection.run_lineage.formal_lifecycle_id
    ) == second.result


def test_supporting_evidence_run_uses_exact_current_persisted_pins(
    tmp_path: Path,
) -> None:
    context = prepare(tmp_path)
    evidence_repository = SQLiteFormalEvidenceRepository(context.path, clock=lambda: NOW)
    evidence_context = EvidenceContext(
        path=context.path,
        repository=evidence_repository,
        lineage=context.lineage,
        activity_id=context.approved.business_process.steps[0].step_id,
    )
    _, document = _store_document(evidence_context)
    ingestion = _ingestion(evidence_context, document)
    extraction, proposal = _extraction(evidence_context, document, ingestion)
    review = _review(evidence_context, proposal)
    mapping = _mapping(evidence_context, review)
    candidate = _candidate(evidence_context, document, extraction, review, mapping)
    readiness = FormalEvidenceReadiness(
        schema_version=FORMAL_EVIDENCE_READINESS_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        readiness_id="run-service-readiness",
        lineage=context.lineage,
        candidate_set=candidate,
        current_review_revision_ids=(review.revision_id,),
        processing_complete_or_explicitly_excluded=True,
        every_current_proposal_terminally_reviewed=True,
        every_accepted_or_corrected_item_mapped_or_context_only=True,
        candidate_set_includes_every_current_review_revision=True,
        lineage_and_integrity_valid=True,
        retained_unknown_count=0,
        retained_conflict_count=0,
        status=ReadinessStatus.READY_TO_ATTEMPT,
        evaluated_at=NOW,
    )
    evidence_repository.append_readiness(readiness, request=request("run-service-ready"))
    candidate_sha = serialize_formal_evidence_record(candidate)[1]
    readiness_sha = serialize_formal_evidence_record(readiness)[1]
    run_lineage = FormalRunLineage(
        formal_lifecycle_id=context.lineage.formal_lifecycle_id,
        authorization_id="supporting-authorization",
        projection_id="supporting-projection",
        run_id="supporting-run",
    )
    choice = FormalAssessmentInputChoice(
        schema_version=FORMAL_ASSESSMENT_INPUT_CHOICE_SCHEMA,
        store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
        lineage=context.lineage,
        mode=FormalAssessmentInputMode.APPROVED_PROCESS_WITH_SUPPORTING_EVIDENCE,
        supporting_evidence_disposition=(
            SupportingEvidenceDisposition.CURRENT_SUPPORTING_EVIDENCE_INCLUDED
        ),
        supporting_candidate=SupportingEvidenceCandidatePin(
            lineage=context.lineage,
            supporting_history_head_id="supporting-head-1",
            supporting_history_head_sha256="a" * 64,
            candidate_set_id=candidate.candidate_set_id,
            candidate_set_payload_sha256=candidate_sha,
            readiness_id=readiness.readiness_id,
            readiness_payload_sha256=readiness_sha,
            readiness_candidate_set_id=candidate.candidate_set_id,
            readiness_candidate_set_payload_sha256=candidate_sha,
            readiness_status="READY_TO_ATTEMPT",
        ),
        explicit_user_confirmation=True,
        selected_at=NOW,
        request=request("supporting-choice-run-service"),
    )
    approval_event = next(
        item for item in context.approved.review.events if item.action.value == "approve"
    )
    authorization = FormalAssessmentAuthorization(
        schema_version=FORMAL_ASSESSMENT_AUTHORIZATION_SCHEMA,
        store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
        authorization_id=run_lineage.authorization_id,
        run_lineage=run_lineage,
        approved_process=ApprovedProcessAuthorizationPin(
            lineage=context.lineage,
            source_extraction_run_id=(
                context.approved.review.original_candidate.extraction_run_id
            ),
            approval_event_id=approval_event.event_id,
            approved_at=context.approved.approval.approved_at,
        ),
        input_choice=choice,
        compatibility=compatibility(),
        explicit_run_confirmation="ATTEMPT ORGANISATIONAL ASSESSMENT",
        authorization_scope=(
            "ASSESSMENT_RUN_ATTEMPT_ONLY_NOT_APPROVAL_OR_IMPLEMENTATION_AUTHORITY"
        ),
        request=request("supporting-authorize-run-service"),
        authorized_at=NOW,
    )

    outcome = service(context, id_namespace="support-").execute(
        authorization,
        approved_review=context.approved,
        request=request("supporting-run-service"),
        candidate_set=candidate,
        readiness=readiness,
        supporting_reviews=(review,),
    )

    assert isinstance(outcome, FormalRunCompleted)
    assert outcome.result.manifest.authorization.input_choice == choice


def test_injected_clock_and_ids_produce_identical_result_and_event_bytes(
    tmp_path: Path,
) -> None:
    first_context = prepare(tmp_path / "first")
    second_context = prepare(tmp_path / "second")
    first_projection = projection(first_context)
    second_projection = projection(second_context)

    first = service(first_context).execute(
        first_projection.authorization,
        approved_review=first_context.approved,
        request=request("deterministic-run"),
    )
    second = service(second_context).execute(
        second_projection.authorization,
        approved_review=second_context.approved,
        request=request("deterministic-run"),
    )

    assert isinstance(first, FormalRunCompleted)
    assert isinstance(second, FormalRunCompleted)
    assert serialize_formal_assessment_record(first.result) == serialize_formal_assessment_record(
        second.result
    )
    assert tuple(
        serialize_formal_assessment_record(item)
        for item in first_context.repository.load_run_events(
            first_projection.run_lineage.run_id
        )
    ) == tuple(
        serialize_formal_assessment_record(item)
        for item in second_context.repository.load_run_events(
            second_projection.run_lineage.run_id
        )
    )
