from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai_adoption_engine.decision.four_gate_engine import FourGateAssessmentEngine
from ai_adoption_engine.decision.four_gate_policy import load_four_gate_policy
from ai_adoption_engine.formal.input_adapter import FormalFourGateInputAdapter
from ai_adoption_engine.models.formal_assessment import (
    FORMAL_ASSESSMENT_AUTHORIZATION_SCHEMA,
    FORMAL_ASSESSMENT_INPUT_CHOICE_SCHEMA,
    FORMAL_ASSESSMENT_RESULT_SUPERSESSION_SCHEMA,
    FORMAL_ASSESSMENT_RUN_EVENT_SCHEMA,
    FORMAL_ASSESSMENT_RUN_MANIFEST_SCHEMA,
    FORMAL_ASSESSMENT_RUN_REQUEST_SCHEMA,
    FORMAL_ASSESSMENT_RUN_STATE_SCHEMA,
    FORMAL_ASSESSMENT_RUN_STORE_ID,
    FORMAL_EVIDENCE_GUIDANCE_CATALOGUE,
    FORMAL_EVIDENCE_GUIDANCE_SCHEMA,
    FORMAL_GUIDANCE_CATALOGUE_FINGERPRINT,
    FORMAL_GUIDANCE_CATALOGUE_ID,
    ApprovedProcessAuthorizationPin,
    FormalAssessmentAuthorization,
    FormalAssessmentInputChoice,
    FormalAssessmentInputMode,
    FormalAssessmentResult,
    FormalAssessmentResultSupersession,
    FormalAssessmentRunEvent,
    FormalAssessmentRunManifest,
    FormalAssessmentRunRequest,
    FormalAssessmentRunState,
    FormalAssessmentTerminalFailure,
    FormalEvidenceGuidance,
    FormalEvidenceGuidanceItem,
    FormalResultActivityTrace,
    FormalRunFailureDetails,
    FormalRunLineage,
    FormalRunOperation,
    FormalRunRecoveryLineage,
    FormalRunStatus,
    SupportingEvidenceCandidatePin,
    SupportingEvidenceDisposition,
)
from ai_adoption_engine.models.formal_assessment_adapter import (
    FormalInputAdapterSuccess,
)
from ai_adoption_engine.models.formal_evidence import (
    FORMAL_EVIDENCE_FAMILY,
    FORMAL_EVIDENCE_READINESS_SCHEMA,
    FormalEvidenceReadiness,
    FormalEvidenceLineage,
    ReadinessStatus,
    RequestIdentity,
)
from ai_adoption_engine.persistence.base import ArtifactCorruptionError
from ai_adoption_engine.persistence.formal_assessment import (
    FormalAssessmentIdempotencyError,
    FormalAssessmentIntegrityError,
    FormalAssessmentPersistenceError,
    SQLiteFormalAssessmentRepository,
)
from ai_adoption_engine.persistence.formal_evidence import (
    SQLiteFormalEvidenceRepository,
)
from ai_adoption_engine.persistence.formal_evidence_serialization import (
    serialize_formal_evidence_record,
)
from ai_adoption_engine.persistence.preliminary_migrations import (
    PRELIMINARY_JOURNEY_STORE_MIGRATIONS,
    SUPPORTING_EVIDENCE_MIGRATION,
)
from ai_adoption_engine.persistence.sqlite import SQLiteAssessmentRepository
from ai_adoption_engine.persistence.workspace_protection import (
    FrozenEvaluationWorkspaceError,
)
from tests.unit.test_formal_assessment_models import compatibility
from tests.integration.test_formal_evidence_persistence import (
    EvidenceContext,
    _candidate,
    _extraction,
    _ingestion,
    _mapping,
    _review,
    _store_document,
)
from tests.unit.test_preliminary_formal_start_service import (
    _formal_service,
    _select_formal,
    _start,
)
from tests.unit.test_preliminary_journey_service import _context


NOW = datetime(2026, 10, 5, 16, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[2]


def sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()


def request(token: str) -> RequestIdentity:
    return RequestIdentity(
        request_token=token,
        canonical_request_sha256=sha({"token": token}),
    )


@dataclass(frozen=True)
class FormalContext:
    path: Path
    repository: SQLiteFormalAssessmentRepository
    approved: object
    lineage: FormalEvidenceLineage


def prepare(tmp_path: Path, **repository_kwargs: object) -> FormalContext:
    preliminary = _context(tmp_path)
    route = _select_formal(preliminary)
    formal = _start(_formal_service(preliminary), preliminary, route).lifecycle
    connection = sqlite3.connect(preliminary.path)
    connection.row_factory = sqlite3.Row
    try:
        artifact = connection.execute(
            """SELECT artifact_revision, artifact_schema_version
               FROM assessment_artifacts WHERE artifact_id = ?""",
            (formal.source.approved_review_artifact_id,),
        ).fetchone()
    finally:
        connection.close()
    assert artifact is not None
    lineage = FormalEvidenceLineage(
        formal_lifecycle_schema=formal.schema_version,
        formal_lifecycle_id=formal.formal_lifecycle_id,
        journey_id=formal.journey_id,
        source_assessment_id=formal.source.source_assessment_id,
        approved_review_artifact_id=formal.source.approved_review_artifact_id,
        approved_review_schema_version=artifact["artifact_schema_version"],
        approved_review_revision=artifact["artifact_revision"],
        approved_review_payload_sha256=formal.source.approved_review_payload_sha256,
        source_document_id=formal.source.source_document_id,
        source_document_sha256=formal.source.source_document_id.removeprefix("doc-"),
        validated_process_id=formal.source.validated_process_id,
        validated_process_fingerprint=formal.source.validated_process_fingerprint,
    )
    return FormalContext(
        path=preliminary.path,
        repository=SQLiteFormalAssessmentRepository(
            preliminary.path, clock=lambda: NOW, **repository_kwargs
        ),
        approved=preliminary.approved,
        lineage=lineage,
    )


def projection(
    context: FormalContext,
    *,
    run_id: str = "formal-run-1",
    authorization_id: str = "formal-authorization-1",
    projection_id: str = "formal-projection-1",
    token_suffix: str = "1",
):
    approved = context.approved
    rl = FormalRunLineage(
        formal_lifecycle_id=context.lineage.formal_lifecycle_id,
        authorization_id=authorization_id,
        projection_id=projection_id,
        run_id=run_id,
    )
    choice = FormalAssessmentInputChoice(
        schema_version=FORMAL_ASSESSMENT_INPUT_CHOICE_SCHEMA,
        store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
        lineage=context.lineage,
        mode=FormalAssessmentInputMode.APPROVED_PROCESS_ONLY,
        supporting_evidence_disposition=SupportingEvidenceDisposition.NO_SUPPORTING_HISTORY,
        explicit_user_confirmation=True,
        selected_at=NOW,
        request=request(f"choice-{token_suffix}"),
    )
    approval_event = next(
        item for item in approved.review.events if item.action.value == "approve"
    )
    authorization = FormalAssessmentAuthorization(
        schema_version=FORMAL_ASSESSMENT_AUTHORIZATION_SCHEMA,
        store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
        authorization_id=authorization_id,
        run_lineage=rl,
        approved_process=ApprovedProcessAuthorizationPin(
            lineage=context.lineage,
            source_extraction_run_id=approved.review.original_candidate.extraction_run_id,
            approval_event_id=approval_event.event_id,
            approved_at=approved.approval.approved_at,
        ),
        input_choice=choice,
        compatibility=compatibility(),
        explicit_run_confirmation="ATTEMPT ORGANISATIONAL ASSESSMENT",
        authorization_scope="ASSESSMENT_RUN_ATTEMPT_ONLY_NOT_APPROVAL_OR_IMPLEMENTATION_AUTHORITY",
        request=request(f"authorize-{token_suffix}"),
        authorized_at=NOW,
    )
    result = FormalFourGateInputAdapter().project(
        authorization=authorization,
        approved_review=approved,
    )
    assert isinstance(result, FormalInputAdapterSuccess)
    return result.projection


def run_request(
    item,
    operation: FormalRunOperation,
    *,
    token: str,
) -> FormalAssessmentRunRequest:
    return FormalAssessmentRunRequest(
        schema_version=FORMAL_ASSESSMENT_RUN_REQUEST_SCHEMA,
        store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
        request=request(token),
        operation=operation,
        run_lineage=item.run_lineage,
        canonical_operation_payload_sha256=sha(
            {"operation": operation.value, "run": item.run_lineage.run_id, "token": token}
        ),
        requested_at=NOW,
    )


def manifest(item, *, token: str = "manifest-1", attempt: int = 1):
    recovery = None
    if attempt > 1:
        recovery = FormalRunRecoveryLineage(
            run_id=item.run_lineage.run_id,
            predecessor_attempt_number=attempt - 1,
            authorization_id=item.authorization.authorization_id,
            projection_id=item.projection_id,
            projection_fingerprint=item.projection_fingerprint,
            input_mode=item.authorization.input_choice.mode,
        )
    return FormalAssessmentRunManifest(
        schema_version=FORMAL_ASSESSMENT_RUN_MANIFEST_SCHEMA,
        store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
        run_lineage=item.run_lineage,
        attempt_number=attempt,
        authorization=item.authorization,
        projection=item,
        recovery=recovery,
        request=run_request(item, FormalRunOperation.AUTHORIZE, token=token),
        created_at=NOW,
    )


def event(
    item,
    sequence: int,
    operation: FormalRunOperation,
    before: FormalRunStatus,
    after: FormalRunStatus,
    *,
    token: str,
):
    return FormalAssessmentRunEvent(
        schema_version=FORMAL_ASSESSMENT_RUN_EVENT_SCHEMA,
        store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
        event_id=f"{item.run_lineage.run_id}-event-{sequence}-{token}",
        sequence=sequence,
        run_lineage=item.run_lineage,
        operation=operation,
        from_status=before,
        to_status=after,
        authorization_id=item.authorization.authorization_id,
        projection_id=item.projection_id,
        projection_fingerprint=item.projection_fingerprint,
        failure=(
            FormalRunFailureDetails(
                code="ENGINE_ERROR", message="The engine failed.", retryable=True
            )
            if operation is FormalRunOperation.FAIL
            else None
        ),
        request=run_request(item, operation, token=token),
        occurred_at=NOW + timedelta(minutes=sequence),
    )


def state(item_manifest, events, status):
    return FormalAssessmentRunState(
        schema_version=FORMAL_ASSESSMENT_RUN_STATE_SCHEMA,
        store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
        manifest=item_manifest,
        events=events,
        current_status=status,
        projected_at=NOW + timedelta(minutes=len(events) + 1),
    )


def successful_result(item_manifest, *, result_id: str):
    item = item_manifest.projection
    policy = load_four_gate_policy(ROOT / "config/decision_policy.v0.3.json")
    assessment = FourGateAssessmentEngine(policy).assess(item.engine_input)
    traces = tuple(
        FormalResultActivityTrace(
            activity_id=activity.activity_id,
            projected_activity_path=f"activities[{index}]",
            assessment_activity_path=f"assessment.step_assessments[{index}]",
            projection_fingerprint=item.projection_fingerprint,
            evidence_ids=tuple(activity.engine_input.evidence_ids),
        )
        for index, activity in enumerate(item.activities)
    )
    return FormalAssessmentResult(
        schema_version="formal-assessment-result.v0.1",
        store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
        result_id=result_id,
        manifest=item_manifest,
        assessment=assessment,
        activity_traces=traces,
        completed_at=NOW + timedelta(minutes=5),
    )


def guidance(result: FormalAssessmentResult, guidance_id: str = "guidance-1"):
    pairs = tuple(
        (step.step_id, gap)
        for step in result.assessment.step_assessments
        for gap in step.blocking_gaps
    )
    return FormalEvidenceGuidance(
        schema_version=FORMAL_EVIDENCE_GUIDANCE_SCHEMA,
        store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
        guidance_id=guidance_id,
        source_result=result,
        catalogue_id=FORMAL_GUIDANCE_CATALOGUE_ID,
        catalogue_fingerprint=FORMAL_GUIDANCE_CATALOGUE_FINGERPRINT,
        source_gaps=tuple(gap for _, gap in pairs),
        items=tuple(
            FormalEvidenceGuidanceItem(
                activity_id=activity_id,
                gate=gap.gate,
                field_name=gap.field_name,
                problem_code=gap.problem_code.value,
                blocking_question=gap.blocking_question,
                evidence_ids=tuple(gap.evidence_ids),
                requested_information=FORMAL_EVIDENCE_GUIDANCE_CATALOGUE[gap.problem_code],
                boundary_notice="Requested information is not evidence; uploading a document does not guarantee a successful outcome.",
            )
            for activity_id, gap in pairs
        ),
        generated_at=NOW,
        derivation="DETERMINISTIC_CATALOGUE_ONLY_NO_LLM",
    )


def persist_success(context: FormalContext, item, *, result_id: str, token: str):
    item_manifest = manifest(item, token=f"manifest-{token}")
    context.repository.create_manifest(item_manifest)
    started = event(
        item,
        1,
        FormalRunOperation.START,
        FormalRunStatus.AUTHORIZED,
        FormalRunStatus.RUNNING,
        token=f"start-{token}",
    )
    context.repository.append_event(
        started,
        state(item_manifest, (started,), FormalRunStatus.RUNNING),
        attempt_number=1,
    )
    completed = event(
        item,
        2,
        FormalRunOperation.COMPLETE,
        FormalRunStatus.RUNNING,
        FormalRunStatus.COMPLETED_PENDING_REVIEW,
        token=f"complete-{token}",
    )
    result = successful_result(item_manifest, result_id=result_id)
    context.repository.append_terminal_record(
        completed,
        state(
            item_manifest,
            (started, completed),
            FormalRunStatus.COMPLETED_PENDING_REVIEW,
        ),
        result,
        attempt_number=1,
    )
    return result


def test_migration_eight_is_explicit_idempotent_and_preserves_migration_seven(
    tmp_path: Path,
) -> None:
    preliminary = _context(tmp_path)
    SQLiteFormalEvidenceRepository(preliminary.path, clock=lambda: NOW)
    before = sqlite3.connect(preliminary.path)
    try:
        before_versions = tuple(
            row[0]
            for row in before.execute(
                "SELECT version FROM preliminary_journey_schema_migrations ORDER BY version"
            )
        )
        supporting_schema = tuple(
            before.execute(
                """SELECT type, name, sql FROM sqlite_master
                   WHERE name LIKE 'preliminary_supporting_%'
                   ORDER BY type, name"""
            )
        )
        supporting_rows = {
            row[0]: before.execute(
                f"SELECT * FROM {row[0]} ORDER BY rowid"
            ).fetchall()
            for row in before.execute(
                """SELECT name FROM sqlite_master
                   WHERE type = 'table'
                     AND name LIKE 'preliminary_supporting_%'"""
            )
        }
    finally:
        before.close()
    assert before_versions == (1, 2, 3, 4, 5, 6, 7)
    first = SQLiteFormalAssessmentRepository(preliminary.path, clock=lambda: NOW)
    assert first.migration_versions() == tuple(range(1, 9))
    second = SQLiteFormalAssessmentRepository(preliminary.path, clock=lambda: NOW)
    assert second.migration_versions() == tuple(range(1, 9))

    connection = sqlite3.connect(preliminary.path)
    try:
        assert tuple(
            connection.execute(
                """SELECT type, name, sql FROM sqlite_master
                   WHERE name LIKE 'preliminary_supporting_%'
                   ORDER BY type, name"""
            )
        ) == supporting_schema
        for table, rows in supporting_rows.items():
            assert connection.execute(
                f"SELECT * FROM {table} ORDER BY rowid"
            ).fetchall() == rows
        assert connection.execute(
            "SELECT COUNT(*) FROM preliminary_journey_schema_migrations WHERE version = 7"
        ).fetchone()[0] == 1
    finally:
        connection.close()


def test_migration_eight_injected_failure_is_atomic(tmp_path: Path) -> None:
    preliminary = _context(tmp_path)
    SQLiteFormalEvidenceRepository(preliminary.path, clock=lambda: NOW)

    def inject(stage: str) -> None:
        if stage == "MIGRATION_8_BEFORE_HISTORY":
            raise RuntimeError("injected migration failure")

    with pytest.raises(FormalAssessmentPersistenceError, match="failed safely"):
        SQLiteFormalAssessmentRepository(
            preliminary.path,
            clock=lambda: NOW,
            failure_injector=inject,
        )

    connection = sqlite3.connect(preliminary.path)
    try:
        assert tuple(
            row[0]
            for row in connection.execute(
                "SELECT version FROM preliminary_journey_schema_migrations ORDER BY version"
            )
        ) == tuple(range(1, 8))
        assert connection.execute(
            """SELECT 1 FROM sqlite_master
               WHERE type = 'table'
                 AND name = 'preliminary_formal_assessment_lineages'"""
        ).fetchone() is None
    finally:
        connection.close()


@pytest.mark.parametrize("existing_version", range(0, 8))
def test_migration_eight_accepts_each_valid_existing_prefix(
    tmp_path: Path, existing_version: int
) -> None:
    path = tmp_path / f"prefix-{existing_version}.db"
    SQLiteAssessmentRepository(path)
    connection = sqlite3.connect(path)
    try:
        for version, script in PRELIMINARY_JOURNEY_STORE_MIGRATIONS:
            if version > existing_version:
                break
            connection.executescript(script)
            connection.execute(
                """INSERT INTO preliminary_journey_schema_migrations
                   VALUES (?, 'preliminary-journey-store.v0.1', '0.1.0', ?)""",
                (version, NOW.isoformat()),
            )
            connection.commit()
        if existing_version == 7:
            version, script = SUPPORTING_EVIDENCE_MIGRATION
            connection.executescript(script)
            connection.execute(
                """INSERT INTO preliminary_journey_schema_migrations
                   VALUES (?, 'preliminary-journey-store.v0.1', '0.1.0', ?)""",
                (version, NOW.isoformat()),
            )
            connection.commit()
    finally:
        connection.close()
    repository = SQLiteFormalAssessmentRepository(path, clock=lambda: NOW)
    assert repository.migration_versions() == tuple(range(1, 9))


def test_process_only_bundle_manifest_events_result_and_guidance_round_trip(
    tmp_path: Path,
) -> None:
    context = prepare(tmp_path)
    item = projection(context)
    result = persist_success(context, item, result_id="result-1", token="one")
    assert context.repository.load_input_choice(
        item.authorization.input_choice.request.request_token
    ) == item.authorization.input_choice
    assert context.repository.load_authorization(
        item.authorization.authorization_id
    ) == item.authorization
    assert context.repository.load_projection(item.projection_id) == item
    assert context.repository.load_manifest(item.run_lineage.run_id) == result.manifest
    assert len(context.repository.load_run_events(item.run_lineage.run_id)) == 2
    assert (
        context.repository.load_run_state(item.run_lineage.run_id).current_status
        is FormalRunStatus.COMPLETED_PENDING_REVIEW
    )
    assert context.repository.load_terminal_record(result.result_id) == result
    assert context.repository.current_successful_result(
        context.lineage.formal_lifecycle_id
    ) == result

    item_guidance = guidance(result)
    context.repository.append_evidence_guidance(
        item_guidance, request=request("guidance-1")
    )
    assert context.repository.load_evidence_guidance("guidance-1") == item_guidance
    history = context.repository.run_history(item.run_lineage.run_id)
    assert len(history.manifests) == 1
    assert len(history.events) == 2
    assert len(history.states) == 3
    assert history.terminal_records == (result,)


def test_supporting_mode_requires_exact_persisted_candidate_and_readiness_pins(
    tmp_path: Path,
) -> None:
    context = prepare(tmp_path)
    evidence_repository = SQLiteFormalEvidenceRepository(
        context.path,
        clock=lambda: NOW,
    )
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
    candidate = _candidate(
        evidence_context,
        document,
        extraction,
        review,
        mapping,
    )
    readiness = FormalEvidenceReadiness(
        schema_version=FORMAL_EVIDENCE_READINESS_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        readiness_id="readiness-1",
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
    evidence_repository.append_readiness(
        readiness,
        request=request("readiness-1"),
    )
    candidate_hash = serialize_formal_evidence_record(candidate)[1]
    readiness_hash = serialize_formal_evidence_record(readiness)[1]
    pin = SupportingEvidenceCandidatePin(
        lineage=context.lineage,
        supporting_history_head_id="supporting-head-1",
        supporting_history_head_sha256="a" * 64,
        candidate_set_id=candidate.candidate_set_id,
        candidate_set_payload_sha256=candidate_hash,
        readiness_id=readiness.readiness_id,
        readiness_payload_sha256=readiness_hash,
        readiness_candidate_set_id=candidate.candidate_set_id,
        readiness_candidate_set_payload_sha256=candidate_hash,
        readiness_status="READY_TO_ATTEMPT",
    )
    choice = FormalAssessmentInputChoice(
        schema_version=FORMAL_ASSESSMENT_INPUT_CHOICE_SCHEMA,
        store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
        lineage=context.lineage,
        mode=FormalAssessmentInputMode.APPROVED_PROCESS_WITH_SUPPORTING_EVIDENCE,
        supporting_evidence_disposition=(
            SupportingEvidenceDisposition.CURRENT_SUPPORTING_EVIDENCE_INCLUDED
        ),
        supporting_candidate=pin,
        explicit_user_confirmation=True,
        selected_at=NOW,
        request=request("supporting-choice"),
    )
    context.repository.append_input_choice(choice)
    assert context.repository.load_input_choice("supporting-choice") == choice

    drifted_pin = pin.model_copy(
        update={
            "candidate_set_payload_sha256": "f" * 64,
            "readiness_candidate_set_payload_sha256": "f" * 64,
        }
    )
    drifted = choice.model_copy(
        update={
            "supporting_candidate": drifted_pin,
            "request": request("supporting-choice-drift"),
        }
    )
    with pytest.raises(FormalAssessmentIntegrityError, match="integrity"):
        context.repository.append_input_choice(drifted)


def test_request_replay_survives_restart_and_conflicting_reuse_fails(
    tmp_path: Path,
) -> None:
    context = prepare(tmp_path)
    item = projection(context)
    item_manifest = manifest(item)
    first = context.repository.create_manifest(item_manifest)
    assert not first.replayed
    restarted = SQLiteFormalAssessmentRepository(context.path, clock=lambda: NOW)
    second = restarted.create_manifest(item_manifest)
    assert second.replayed

    conflicting = item_manifest.model_copy(
        update={"created_at": NOW + timedelta(minutes=1)}
    )
    with pytest.raises(FormalAssessmentIdempotencyError):
        restarted.create_manifest(conflicting)


def test_event_failure_rolls_back_request_event_and_state(tmp_path: Path) -> None:
    def inject(stage: str) -> None:
        if stage == "APPEND_RUN_EVENT":
            raise RuntimeError("injected")

    context = prepare(tmp_path, failure_injector=inject)
    item = projection(context)
    item_manifest = manifest(item)
    context.repository.create_manifest(item_manifest)
    started = event(
        item,
        1,
        FormalRunOperation.START,
        FormalRunStatus.AUTHORIZED,
        FormalRunStatus.RUNNING,
        token="start-rollback",
    )
    with pytest.raises(RuntimeError, match="injected"):
        context.repository.append_event(
            started,
            state(item_manifest, (started,), FormalRunStatus.RUNNING),
            attempt_number=1,
        )
    assert context.repository.load_run_events(item.run_lineage.run_id) == ()
    assert (
        context.repository.load_run_state(item.run_lineage.run_id).current_status
        is FormalRunStatus.AUTHORIZED
    )
    connection = sqlite3.connect(context.path)
    try:
        assert connection.execute(
            """SELECT COUNT(*) FROM preliminary_formal_assessment_run_requests
               WHERE request_token = 'start-rollback'"""
        ).fetchone()[0] == 0
    finally:
        connection.close()


def test_terminal_failure_is_exclusive_and_retry_preserves_projection(
    tmp_path: Path,
) -> None:
    context = prepare(tmp_path)
    item = projection(context)
    first_manifest = manifest(item)
    context.repository.create_manifest(first_manifest)
    started = event(
        item,
        1,
        FormalRunOperation.START,
        FormalRunStatus.AUTHORIZED,
        FormalRunStatus.RUNNING,
        token="start-failure",
    )
    context.repository.append_event(
        started,
        state(first_manifest, (started,), FormalRunStatus.RUNNING),
        attempt_number=1,
    )
    failed = event(
        item,
        2,
        FormalRunOperation.FAIL,
        FormalRunStatus.RUNNING,
        FormalRunStatus.FAILED,
        token="fail-one",
    )
    failure = FormalAssessmentTerminalFailure(
        schema_version="formal-assessment-result.v0.1",
        store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
        terminal_record_id="failure-1",
        manifest=first_manifest,
        status=FormalRunStatus.FAILED,
        failure=failed.failure,
        occurred_at=NOW + timedelta(minutes=3),
    )
    context.repository.append_terminal_record(
        failed,
        state(first_manifest, (started, failed), FormalRunStatus.FAILED),
        failure,
        attempt_number=1,
    )
    assert context.repository.load_terminal_record("failure-1") == failure

    retry = manifest(item, token="manifest-retry", attempt=2)
    context.repository.create_manifest(retry)
    assert retry.projection == first_manifest.projection
    assert retry.authorization.input_choice.mode is first_manifest.authorization.input_choice.mode


def test_supersession_selects_one_current_successful_result_and_rejects_cross_lifecycle(
    tmp_path: Path,
) -> None:
    context = prepare(tmp_path)
    first_projection = projection(context)
    first = persist_success(
        context, first_projection, result_id="result-1", token="first"
    )
    second_projection = projection(
        context,
        run_id="formal-run-2",
        authorization_id="formal-authorization-2",
        projection_id="formal-projection-2",
        token_suffix="2",
    )
    second = persist_success(
        context, second_projection, result_id="result-2", token="second"
    )
    with pytest.raises(FormalAssessmentIntegrityError, match="ambiguous"):
        context.repository.current_successful_result(context.lineage.formal_lifecycle_id)

    link = FormalAssessmentResultSupersession(
        schema_version=FORMAL_ASSESSMENT_RESULT_SUPERSESSION_SCHEMA,
        store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
        supersession_id="supersession-1",
        formal_lifecycle_id=context.lineage.formal_lifecycle_id,
        superseded_result_id=first.result_id,
        successor_result_id=second.result_id,
        superseded_run_id=first.manifest.run_lineage.run_id,
        successor_run_id=second.manifest.run_lineage.run_id,
        predecessor_status=FormalRunStatus.COMPLETED_PENDING_REVIEW,
        successor_status=FormalRunStatus.COMPLETED_PENDING_REVIEW,
        rationale="A later explicit run completed successfully.",
        request=request("supersession-1"),
        superseded_at=NOW,
    )
    context.repository.append_result_supersession(link)
    assert context.repository.current_successful_result(
        context.lineage.formal_lifecycle_id
    ) == second
    assert context.repository.load_result_supersession("supersession-1") == link

    cross = link.model_copy(
        update={
            "supersession_id": "supersession-cross",
            "formal_lifecycle_id": "another-lifecycle",
            "request": request("supersession-cross"),
        }
    )
    with pytest.raises(FormalAssessmentIntegrityError):
        context.repository.append_result_supersession(cross)

    invalid_status = link.model_copy(
        update={
            "supersession_id": "supersession-invalid-status",
            "predecessor_status": FormalRunStatus.FAILED,
            "request": request("supersession-invalid-status"),
        }
    )
    with pytest.raises(ArtifactCorruptionError):
        context.repository.append_result_supersession(invalid_status)

    cycle = FormalAssessmentResultSupersession(
        schema_version=FORMAL_ASSESSMENT_RESULT_SUPERSESSION_SCHEMA,
        store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
        supersession_id="supersession-cycle",
        formal_lifecycle_id=context.lineage.formal_lifecycle_id,
        superseded_result_id=second.result_id,
        successor_result_id=first.result_id,
        superseded_run_id=second.manifest.run_lineage.run_id,
        successor_run_id=first.manifest.run_lineage.run_id,
        predecessor_status=FormalRunStatus.COMPLETED_PENDING_REVIEW,
        successor_status=FormalRunStatus.COMPLETED_PENDING_REVIEW,
        rationale="A cycle is never valid immutable history.",
        request=request("supersession-cycle"),
        superseded_at=NOW,
    )
    with pytest.raises(FormalAssessmentIntegrityError, match="integrity"):
        context.repository.append_result_supersession(cycle)


def test_concurrent_same_event_replays_without_gap(tmp_path: Path) -> None:
    context = prepare(tmp_path)
    item = projection(context)
    item_manifest = manifest(item)
    context.repository.create_manifest(item_manifest)
    started = event(
        item,
        1,
        FormalRunOperation.START,
        FormalRunStatus.AUTHORIZED,
        FormalRunStatus.RUNNING,
        token="start-concurrent",
    )
    item_state = state(item_manifest, (started,), FormalRunStatus.RUNNING)

    def append():
        repo = SQLiteFormalAssessmentRepository(context.path, clock=lambda: NOW)
        return repo.append_event(started, item_state, attempt_number=1)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(lambda _: append(), range(2)))
    assert sorted(item.replayed for item in results) == [False, True]
    assert len(context.repository.load_run_events(item.run_lineage.run_id)) == 1


def test_corruption_and_update_delete_attempts_fail_closed(tmp_path: Path) -> None:
    context = prepare(tmp_path)
    item = projection(context)
    context.repository.append_projection(item, request=request("projection-store"))
    connection = sqlite3.connect(context.path)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                """UPDATE preliminary_formal_assessment_projections
                   SET payload_sha256 = ? WHERE projection_id = ?""",
                ("f" * 64, item.projection_id),
            )
        connection.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                """DELETE FROM preliminary_formal_assessment_projections
                   WHERE projection_id = ?""",
                (item.projection_id,),
            )
        connection.rollback()
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("PRAGMA recursive_triggers = OFF")
        connection.execute("DROP TRIGGER formal_assessment_projections_immutable_update")
        connection.execute(
            """UPDATE preliminary_formal_assessment_projections
               SET payload_sha256 = ? WHERE projection_id = ?""",
            ("f" * 64, item.projection_id),
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(ArtifactCorruptionError, match="integrity"):
        context.repository.load_projection(item.projection_id)


def test_frozen_workspace_refusal_preserves_bytes_and_sidecars(tmp_path: Path) -> None:
    context = prepare(tmp_path / "source")
    frozen_dir = tmp_path / "evaluation" / "portfolio" / "frozen-case"
    frozen_dir.mkdir(parents=True)
    frozen_path = frozen_dir / "workspace.db"
    shutil.copy2(context.path, frozen_path)
    before = frozen_path.read_bytes()
    with pytest.raises(FrozenEvaluationWorkspaceError):
        SQLiteFormalAssessmentRepository(frozen_path)
    assert frozen_path.read_bytes() == before
    assert not Path(f"{frozen_path}-wal").exists()
    assert not Path(f"{frozen_path}-shm").exists()
    assert not Path(f"{frozen_path}-journal").exists()

    readonly = SQLiteFormalAssessmentRepository(frozen_path, read_only=True)
    assert readonly.migration_versions() == tuple(range(1, 9))
    assert frozen_path.read_bytes() == before


def test_unsupported_migration_history_is_rejected_before_schema_changes(
    tmp_path: Path,
) -> None:
    context = prepare(tmp_path)
    connection = sqlite3.connect(context.path)
    try:
        connection.execute(
            """INSERT INTO preliminary_journey_schema_migrations
               VALUES (99, 'preliminary-journey-store.v0.1', '0.1.0', ?)""",
            (NOW.isoformat(),),
        )
        connection.commit()
    finally:
        connection.close()
    before = context.path.read_bytes()
    with pytest.raises(FormalAssessmentPersistenceError, match="unsupported"):
        SQLiteFormalAssessmentRepository(context.path)
    assert context.path.read_bytes() == before
