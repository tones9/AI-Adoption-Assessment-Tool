"""Explicit, non-default orchestration for one frozen formal assessment run."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from ai_adoption_engine.decision.four_gate_engine import FourGateAssessmentEngine
from ai_adoption_engine.decision.four_gate_policy import (
    FourGateDecisionPolicy,
    load_four_gate_policy,
)
from ai_adoption_engine.formal.input_adapter import FormalFourGateInputAdapter
from ai_adoption_engine.models.formal_assessment import (
    FORMAL_ASSESSMENT_RESULT_SCHEMA,
    FORMAL_ASSESSMENT_RUN_EVENT_SCHEMA,
    FORMAL_ASSESSMENT_RUN_MANIFEST_SCHEMA,
    FORMAL_ASSESSMENT_RUN_REQUEST_SCHEMA,
    FORMAL_ASSESSMENT_RUN_STORE_ID,
    FORMAL_ASSESSMENT_RUN_STATE_SCHEMA,
    FORMAL_GUIDANCE_CATALOGUE_FINGERPRINT,
    FORMAL_GUIDANCE_CATALOGUE_ID,
    FORMAL_INPUT_ADAPTER_ID,
    FORMAL_INPUT_ADAPTER_RULES_FINGERPRINT,
    FORMAL_INPUT_ADAPTER_RULES_ID,
    FORMAL_INPUT_ADAPTER_VERSION,
    FOUR_GATE_POLICY_FINGERPRINT,
    FormalAssessmentAuthorization,
    FormalAssessmentInputProjection,
    FormalAssessmentResult,
    FormalAssessmentResultSupersession,
    FormalAssessmentRunEvent,
    FormalAssessmentRunManifest,
    FormalAssessmentRunRequest,
    FormalAssessmentRunState,
    FormalAssessmentTerminalFailure,
    FormalResultActivityTrace,
    FormalRunFailureDetails,
    FormalRunOperation,
    FormalRunRecoveryLineage,
    FormalRunStatus,
)
from ai_adoption_engine.models.formal_assessment_adapter import (
    FORMAL_FOUR_GATE_INPUT_ADAPTER_RULES,
    FormalFourGateInputAdapterRules,
    FormalInputAdapterFailure,
    FormalInputAdapterSuccess,
)
from ai_adoption_engine.models.formal_evidence import RequestIdentity
from ai_adoption_engine.models.four_gate_assessment import FourGateProcessAssessment
from ai_adoption_engine.models.review import ApprovedProcessReview
from ai_adoption_engine.persistence.base import ArtifactNotFoundError, PersistenceError
from ai_adoption_engine.persistence.formal_assessment import (
    FormalAssessmentConcurrencyError,
    FormalAssessmentIdempotencyError,
    FormalAssessmentIntegrityError,
    FormalAssessmentPersistenceError,
    SQLiteFormalAssessmentRepository,
)


Clock = Callable[[], datetime]
IdFactory = Callable[[str], str]
PolicyLoader = Callable[[str | Path], FourGateDecisionPolicy]
EngineFactory = Callable[[FourGateDecisionPolicy], FourGateAssessmentEngine]


class FormalRunFailureCode(StrEnum):
    INVALID_AUTHORIZATION = "INVALID_AUTHORIZATION"
    INVALID_APPROVED_REVIEW = "INVALID_APPROVED_REVIEW"
    ADAPTER_PROJECTION_REJECTED = "ADAPTER_PROJECTION_REJECTED"
    COMPATIBILITY_OR_POLICY_DRIFT = "COMPATIBILITY_OR_POLICY_DRIFT"
    MANIFEST_PERSISTENCE_FAILED = "MANIFEST_PERSISTENCE_FAILED"
    START_PERSISTENCE_FAILED = "START_PERSISTENCE_FAILED"
    STRICT_ENGINE_FAILED = "STRICT_ENGINE_FAILED"
    INVALID_ENGINE_OUTPUT = "INVALID_ENGINE_OUTPUT"
    TERMINAL_PERSISTENCE_FAILED = "TERMINAL_PERSISTENCE_FAILED"
    INTERRUPTED = "INTERRUPTED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    STALE_OR_CONFLICTING_REQUEST = "STALE_OR_CONFLICTING_REQUEST"
    REPOSITORY_INTEGRITY_FAILED = "REPOSITORY_INTEGRITY_FAILED"


@dataclass(frozen=True)
class FormalRunCompleted:
    result: FormalAssessmentResult
    replayed: bool


@dataclass(frozen=True)
class FormalRunTerminalFailure:
    terminal_failure: FormalAssessmentTerminalFailure
    replayed: bool


@dataclass(frozen=True)
class FormalRunPreRunRejection:
    code: FormalRunFailureCode
    message: str
    adapter_failure: FormalInputAdapterFailure | None = None


@dataclass(frozen=True)
class FormalRunRecoveryRequired:
    code: FormalRunFailureCode
    message: str
    manifest: FormalAssessmentRunManifest
    state: FormalAssessmentRunState
    replayed: bool


FormalRunOutcome = (
    FormalRunCompleted
    | FormalRunTerminalFailure
    | FormalRunPreRunRejection
    | FormalRunRecoveryRequired
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def _canonical_hash(value: object) -> str:
    def jsonable(item: object):
        if isinstance(item, BaseModel):
            return jsonable(item.model_dump(mode="json"))
        if isinstance(item, dict):
            return {str(key): jsonable(value) for key, value in item.items()}
        if isinstance(item, tuple | list):
            return [jsonable(value) for value in item]
        return item

    encoded = json.dumps(
        jsonable(value),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class FormalAssessmentRunService:
    """Run only the explicitly supplied D-037 contracts through the strict engine."""

    def __init__(
        self,
        repository: SQLiteFormalAssessmentRepository,
        *,
        policy_path: str | Path,
        adapter: FormalFourGateInputAdapter | None = None,
        policy_loader: PolicyLoader = load_four_gate_policy,
        engine_factory: EngineFactory = FourGateAssessmentEngine,
        clock: Clock | None = None,
        id_factory: IdFactory | None = None,
    ) -> None:
        self.repository = repository
        self.policy_path = Path(policy_path)
        self.adapter = adapter or FormalFourGateInputAdapter()
        self.policy_loader = policy_loader
        self.engine_factory = engine_factory
        self.clock = clock or _utc_now
        self.id_factory = id_factory or _new_id
        self._validate_adapter_dependency()

    def execute(
        self,
        authorization: object,
        *,
        approved_review: object,
        request: object,
        candidate_set: object | None = None,
        readiness: object | None = None,
        supporting_reviews: tuple[object, ...] = (),
    ) -> FormalRunOutcome:
        """Explicitly project, persist, and assess one newly authorized attempt."""

        validated_authorization = self._authorization_or_rejection(authorization)
        if isinstance(validated_authorization, FormalRunPreRunRejection):
            return validated_authorization
        validated_request = self._request_or_rejection(request)
        if isinstance(validated_request, FormalRunPreRunRejection):
            return validated_request

        replay = self._existing_attempt(
            validated_authorization,
            validated_request,
            attempt_number=1,
        )
        if replay is not None:
            return replay
        writable = self._require_writable()
        if writable is not None:
            return writable
        policy = self._policy_or_rejection(validated_authorization)
        if isinstance(policy, FormalRunPreRunRejection):
            return policy
        review = self._review_or_rejection(approved_review)
        if isinstance(review, FormalRunPreRunRejection):
            return review

        try:
            adapted = self.adapter.project(
                authorization=validated_authorization,
                approved_review=review,
                candidate_set=candidate_set,
                readiness=readiness,
                supporting_reviews=supporting_reviews,
            )
        except Exception as exc:
            return FormalRunPreRunRejection(
                FormalRunFailureCode.ADAPTER_PROJECTION_REJECTED,
                f"The formal input adapter raised before a run was created: {exc}",
            )
        if isinstance(adapted, FormalInputAdapterFailure):
            return FormalRunPreRunRejection(
                FormalRunFailureCode.ADAPTER_PROJECTION_REJECTED,
                "The formal input adapter rejected the requested run.",
                adapted,
            )
        if not isinstance(adapted, FormalInputAdapterSuccess):
            return FormalRunPreRunRejection(
                FormalRunFailureCode.ADAPTER_PROJECTION_REJECTED,
                "The formal input adapter returned an unsupported outcome.",
            )
        return self._start_and_assess(
            authorization=validated_authorization,
            projection=adapted.projection,
            request=validated_request,
            policy=policy,
            attempt_number=1,
            recovery=None,
        )

    def interrupt_running(
        self,
        authorization: object,
        *,
        request: object,
    ) -> FormalRunOutcome:
        """Record an explicit recovery-required interruption without rerunning work."""

        return self._recover_event(
            authorization,
            request=request,
            operation=FormalRunOperation.INTERRUPT,
            allowed={FormalRunStatus.RUNNING},
            target=FormalRunStatus.INTERRUPTED,
            code=FormalRunFailureCode.INTERRUPTED,
            message="The running formal assessment was explicitly marked interrupted.",
        )

    def mark_retry_available(
        self,
        authorization: object,
        *,
        request: object,
    ) -> FormalRunOutcome:
        """Expose retry only after a failed or explicitly interrupted attempt."""

        return self._recover_event(
            authorization,
            request=request,
            operation=FormalRunOperation.MARK_RETRY_AVAILABLE,
            allowed={FormalRunStatus.FAILED, FormalRunStatus.INTERRUPTED},
            target=FormalRunStatus.RETRY_AVAILABLE,
            code=FormalRunFailureCode.RECOVERY_REQUIRED,
            message="A retry is explicitly available for this immutable attempt.",
        )

    def abandon(
        self,
        authorization: object,
        *,
        request: object,
        rationale: str,
    ) -> FormalRunOutcome:
        """Explicitly abandon an authorized or recovery-only attempt."""

        if not rationale.strip():
            return FormalRunPreRunRejection(
                FormalRunFailureCode.REPOSITORY_INTEGRITY_FAILED,
                "An explicit abandonment rationale is required.",
            )
        validated_authorization = self._authorization_or_rejection(authorization)
        if isinstance(validated_authorization, FormalRunPreRunRejection):
            return validated_authorization
        validated_request = self._request_or_rejection(request)
        if isinstance(validated_request, FormalRunPreRunRejection):
            return validated_request
        manifest_state = self._latest_manifest_state(validated_authorization)
        if isinstance(manifest_state, FormalRunPreRunRejection):
            return manifest_state
        manifest, state = manifest_state
        replay = self._recovery_replay(validated_request, manifest, state)
        if replay is not None:
            return replay
        writable = self._require_writable()
        if writable is not None:
            return writable
        if state.current_status not in {
            FormalRunStatus.AUTHORIZED,
            FormalRunStatus.INTERRUPTED,
            FormalRunStatus.RETRY_AVAILABLE,
        }:
            return self._recovery_rejection(manifest, state, "This attempt cannot be abandoned.")
        event = self._event(
            manifest,
            sequence=len(state.events) + 1,
            operation=FormalRunOperation.ABANDON,
            from_status=state.current_status,
            to_status=FormalRunStatus.ABANDONED,
            request=validated_request,
            attempt_number=manifest.attempt_number,
            payload={"rationale": rationale},
            use_external_identity=True,
        )
        abandoned_state = self._state(manifest, (*state.events, event), FormalRunStatus.ABANDONED)
        history = self.repository.run_history(manifest.run_lineage.run_id)
        existing_terminal = next(
            (
                item
                for item in history.terminal_records
                if item.manifest.attempt_number == manifest.attempt_number
            ),
            None,
        )
        terminal: FormalAssessmentTerminalFailure | None = None
        if existing_terminal is None:
            terminal = FormalAssessmentTerminalFailure(
                schema_version=FORMAL_ASSESSMENT_RESULT_SCHEMA,
                store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
                terminal_record_id=self._id("formal-terminal"),
                manifest=manifest,
                status=FormalRunStatus.ABANDONED,
                failure=FormalRunFailureDetails(
                    code="EXPLICIT_ABANDONMENT",
                    message=rationale,
                    retryable=False,
                ),
                occurred_at=self._now(),
            )
        try:
            self.repository.append_event(
                event,
                abandoned_state,
                attempt_number=manifest.attempt_number,
                terminal_record=terminal,
            )
        except PersistenceError as exc:
            return self._recovery_rejection(
                manifest,
                state,
                f"The abandonment transition could not be persisted: {exc}",
            )
        except Exception as exc:
            return self._recovery_rejection(
                manifest,
                state,
                f"The abandonment transition could not be persisted: {exc}",
            )
        if terminal is not None:
            return FormalRunTerminalFailure(terminal, replayed=False)
        return FormalRunRecoveryRequired(
            FormalRunFailureCode.RECOVERY_REQUIRED,
            "The attempt was abandoned after its immutable terminal failure.",
            manifest,
            abandoned_state,
            replayed=False,
        )

    def retry(
        self,
        authorization: object,
        *,
        request: object,
    ) -> FormalRunOutcome:
        """Create the next attempt from the original immutable projection only."""

        validated_authorization = self._authorization_or_rejection(authorization)
        if isinstance(validated_authorization, FormalRunPreRunRejection):
            return validated_authorization
        validated_request = self._request_or_rejection(request)
        if isinstance(validated_request, FormalRunPreRunRejection):
            return validated_request
        manifest_state = self._latest_manifest_state(validated_authorization)
        if isinstance(manifest_state, FormalRunPreRunRejection):
            return manifest_state
        predecessor, predecessor_state = manifest_state
        if (
            predecessor.attempt_number > 1
            and predecessor.request.request == validated_request
        ):
            try:
                return self._outcome_for_attempt(predecessor, replayed=True)
            except Exception as exc:
                return FormalRunPreRunRejection(
                    FormalRunFailureCode.REPOSITORY_INTEGRITY_FAILED,
                    f"The replayed retry outcome cannot be read safely: {exc}",
                )
        next_attempt = predecessor.attempt_number + 1
        replay = self._existing_attempt(
            validated_authorization,
            validated_request,
            attempt_number=next_attempt,
        )
        if replay is not None:
            return replay
        if predecessor_state.current_status is not FormalRunStatus.RETRY_AVAILABLE:
            return self._recovery_rejection(
                predecessor,
                predecessor_state,
                "Only an explicitly retry-available attempt can be retried.",
            )
        writable = self._require_writable()
        if writable is not None:
            return writable
        policy = self._policy_or_rejection(validated_authorization)
        if isinstance(policy, FormalRunPreRunRejection):
            return policy
        recovery = FormalRunRecoveryLineage(
            run_id=predecessor.run_lineage.run_id,
            predecessor_attempt_number=predecessor.attempt_number,
            authorization_id=predecessor.authorization.authorization_id,
            projection_id=predecessor.projection.projection_id,
            projection_fingerprint=predecessor.projection.projection_fingerprint,
            input_mode=predecessor.authorization.input_choice.mode,
        )
        return self._start_and_assess(
            authorization=predecessor.authorization,
            projection=predecessor.projection,
            request=validated_request,
            policy=policy,
            attempt_number=next_attempt,
            recovery=recovery,
        )

    def supersede_result(
        self,
        *,
        predecessor_result_id: str,
        successor_result_id: str,
        request: object,
        rationale: str,
    ) -> FormalRunOutcome:
        """Explicitly supersede one current successful result with another."""

        validated_request = self._request_or_rejection(request)
        if isinstance(validated_request, FormalRunPreRunRejection):
            return validated_request
        if not rationale.strip():
            return FormalRunPreRunRejection(
                FormalRunFailureCode.REPOSITORY_INTEGRITY_FAILED,
                "A supersession rationale is required.",
            )
        supersession_id = self._stable_id("formal-supersession", validated_request)
        try:
            persisted = self.repository.load_result_supersession(supersession_id)
        except ArtifactNotFoundError:
            persisted = None
        except Exception as exc:
            return FormalRunPreRunRejection(
                FormalRunFailureCode.REPOSITORY_INTEGRITY_FAILED,
                f"The result supersession cannot be read safely: {exc}",
            )
        if persisted is not None:
            if (
                persisted.request != validated_request
                or persisted.superseded_result_id != predecessor_result_id
                or persisted.successor_result_id != successor_result_id
                or persisted.rationale != rationale
            ):
                return FormalRunPreRunRejection(
                    FormalRunFailureCode.STALE_OR_CONFLICTING_REQUEST,
                    "The supersession request token is bound to different immutable content.",
                )
            try:
                successor = self.repository.load_terminal_record(successor_result_id)
            except Exception as exc:
                return FormalRunPreRunRejection(
                    FormalRunFailureCode.REPOSITORY_INTEGRITY_FAILED,
                    f"The persisted supersession successor cannot be read safely: {exc}",
                )
            if not isinstance(successor, FormalAssessmentResult):
                return FormalRunPreRunRejection(
                    FormalRunFailureCode.REPOSITORY_INTEGRITY_FAILED,
                    "The persisted supersession does not point to a successful result.",
                )
            return FormalRunCompleted(successor, replayed=True)
        writable = self._require_writable()
        if writable is not None:
            return writable
        try:
            predecessor = self.repository.load_terminal_record(predecessor_result_id)
            successor = self.repository.load_terminal_record(successor_result_id)
            if not isinstance(predecessor, FormalAssessmentResult) or not isinstance(
                successor, FormalAssessmentResult
            ):
                raise FormalAssessmentIntegrityError(
                    "Only completed formal results may participate in supersession"
                )
            lifecycle_id = predecessor.manifest.run_lineage.formal_lifecycle_id
            if successor.manifest.run_lineage.formal_lifecycle_id != lifecycle_id:
                raise FormalAssessmentIntegrityError(
                    "Supersession must remain within one formal lifecycle"
                )
            heads = self.repository.successful_result_heads(lifecycle_id)
            if predecessor not in heads or successor not in heads:
                raise FormalAssessmentIntegrityError(
                    "Supersession must use current immutable successful-result heads"
                )
            supersession = FormalAssessmentResultSupersession(
                schema_version="formal-assessment-result-supersession.v0.1",
                store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
                supersession_id=supersession_id,
                formal_lifecycle_id=lifecycle_id,
                superseded_result_id=predecessor.result_id,
                successor_result_id=successor.result_id,
                superseded_run_id=predecessor.manifest.run_lineage.run_id,
                successor_run_id=successor.manifest.run_lineage.run_id,
                predecessor_status=FormalRunStatus.COMPLETED_PENDING_REVIEW,
                successor_status=FormalRunStatus.COMPLETED_PENDING_REVIEW,
                rationale=rationale,
                request=validated_request,
                superseded_at=self._now(),
            )
            written = self.repository.append_result_supersession(supersession)
            return FormalRunCompleted(successor, replayed=written.replayed)
        except (PersistenceError, ValidationError, ValueError) as exc:
            return FormalRunPreRunRejection(
                FormalRunFailureCode.REPOSITORY_INTEGRITY_FAILED,
                f"The result supersession was rejected: {exc}",
            )
        except Exception as exc:
            return FormalRunPreRunRejection(
                FormalRunFailureCode.REPOSITORY_INTEGRITY_FAILED,
                f"The result supersession could not be persisted: {exc}",
            )

    def _start_and_assess(
        self,
        *,
        authorization: FormalAssessmentAuthorization,
        projection: FormalAssessmentInputProjection,
        request: RequestIdentity,
        policy: FourGateDecisionPolicy,
        attempt_number: int,
        recovery: FormalRunRecoveryLineage | None,
    ) -> FormalRunOutcome:
        manifest_request = self._run_request(
            request,
            operation=FormalRunOperation.AUTHORIZE,
            lineage=authorization.run_lineage,
            attempt_number=attempt_number,
            payload={
                "authorization": authorization,
                "projection_fingerprint": projection.projection_fingerprint,
                "recovery": recovery,
            },
            use_external_identity=True,
        )
        manifest = FormalAssessmentRunManifest(
            schema_version=FORMAL_ASSESSMENT_RUN_MANIFEST_SCHEMA,
            store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
            run_lineage=authorization.run_lineage,
            attempt_number=attempt_number,
            authorization=authorization,
            projection=projection,
            recovery=recovery,
            request=manifest_request,
            created_at=self._now(),
        )
        start_event = self._event(
            manifest,
            sequence=1,
            operation=FormalRunOperation.START,
            from_status=FormalRunStatus.AUTHORIZED,
            to_status=FormalRunStatus.RUNNING,
            request=request,
            attempt_number=attempt_number,
            payload={"projection_fingerprint": projection.projection_fingerprint},
        )
        running_state = self._state(manifest, (start_event,), FormalRunStatus.RUNNING)
        try:
            written = self.repository.create_manifest_and_start(
                manifest,
                start_event,
                running_state,
            )
        except FormalAssessmentIdempotencyError:
            replay = self._existing_attempt(authorization, request, attempt_number)
            if replay is not None:
                return replay
            return FormalRunPreRunRejection(
                FormalRunFailureCode.STALE_OR_CONFLICTING_REQUEST,
                "The run request token was reused with different immutable content.",
            )
        except FormalAssessmentConcurrencyError:
            replay = self._existing_attempt(authorization, request, attempt_number)
            if replay is not None:
                return replay
            return FormalRunPreRunRejection(
                FormalRunFailureCode.STALE_OR_CONFLICTING_REQUEST,
                "Another caller owns this formal run attempt.",
            )
        except PersistenceError as exc:
            return FormalRunPreRunRejection(
                FormalRunFailureCode.START_PERSISTENCE_FAILED,
                f"The manifest/start boundary was not persisted: {exc}",
            )
        except Exception as exc:
            return FormalRunPreRunRejection(
                FormalRunFailureCode.START_PERSISTENCE_FAILED,
                f"The manifest/start boundary was not persisted: {exc}",
            )
        if written.replayed:
            try:
                return self._outcome_for_attempt(manifest, replayed=True)
            except Exception as exc:
                return FormalRunPreRunRejection(
                    FormalRunFailureCode.REPOSITORY_INTEGRITY_FAILED,
                    f"The replayed run outcome cannot be read safely: {exc}",
                )
        return self._invoke_started_attempt(manifest, running_state, request, policy)

    def _invoke_started_attempt(
        self,
        manifest: FormalAssessmentRunManifest,
        running_state: FormalAssessmentRunState,
        root_request: RequestIdentity,
        policy: FourGateDecisionPolicy,
    ) -> FormalRunOutcome:
        try:
            engine = self.engine_factory(policy)
            if not isinstance(engine, FourGateAssessmentEngine) or engine.policy != policy:
                raise TypeError(
                    "The run service requires the exact strict four-gate engine and policy"
                )
            assessment = engine.assess(manifest.projection.engine_input)
        except Exception as exc:
            return self._persist_failure(
                manifest,
                running_state,
                root_request,
                FormalRunFailureCode.STRICT_ENGINE_FAILED,
                f"The strict four-gate engine failed: {exc}",
                retryable=True,
            )
        try:
            validated_assessment = FourGateProcessAssessment.model_validate(
                assessment.model_dump(mode="json")
                if isinstance(assessment, BaseModel)
                else assessment
            )
            result = FormalAssessmentResult(
                schema_version=FORMAL_ASSESSMENT_RESULT_SCHEMA,
                store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
                result_id=self._id("formal-result"),
                manifest=manifest,
                assessment=validated_assessment,
                activity_traces=tuple(
                    FormalResultActivityTrace(
                        activity_id=item.activity_id,
                        projected_activity_path=f"activities[{index}]",
                        assessment_activity_path=(
                            f"assessment.step_assessments[{index}]"
                        ),
                        projection_fingerprint=manifest.projection.projection_fingerprint,
                        evidence_ids=tuple(item.engine_input.evidence_ids),
                    )
                    for index, item in enumerate(manifest.projection.activities)
                ),
                completed_at=self._now(),
            )
        except (AttributeError, TypeError, ValidationError, ValueError) as exc:
            return self._persist_failure(
                manifest,
                running_state,
                root_request,
                FormalRunFailureCode.INVALID_ENGINE_OUTPUT,
                f"The strict engine output diverged from the immutable projection: {exc}",
                retryable=False,
            )
        event = self._event(
            manifest,
            sequence=len(running_state.events) + 1,
            operation=FormalRunOperation.COMPLETE,
            from_status=FormalRunStatus.RUNNING,
            to_status=FormalRunStatus.COMPLETED_PENDING_REVIEW,
            request=root_request,
            attempt_number=manifest.attempt_number,
            payload={"result_id": result.result_id},
        )
        completed_state = self._state(
            manifest,
            (*running_state.events, event),
            FormalRunStatus.COMPLETED_PENDING_REVIEW,
        )
        try:
            self.repository.append_terminal_record(
                event,
                completed_state,
                result,
                attempt_number=manifest.attempt_number,
            )
        except PersistenceError as exc:
            return FormalRunRecoveryRequired(
                FormalRunFailureCode.TERMINAL_PERSISTENCE_FAILED,
                f"The engine ran once, but final result persistence failed: {exc}",
                manifest,
                running_state,
                replayed=False,
            )
        except Exception as exc:
            return FormalRunRecoveryRequired(
                FormalRunFailureCode.TERMINAL_PERSISTENCE_FAILED,
                f"The engine ran once, but final result persistence failed: {exc}",
                manifest,
                running_state,
                replayed=False,
            )
        return FormalRunCompleted(result, replayed=False)

    def _persist_failure(
        self,
        manifest: FormalAssessmentRunManifest,
        running_state: FormalAssessmentRunState,
        root_request: RequestIdentity,
        code: FormalRunFailureCode,
        message: str,
        *,
        retryable: bool,
    ) -> FormalRunOutcome:
        failure = FormalRunFailureDetails(
            code=code.value,
            message=message,
            retryable=retryable,
        )
        event = self._event(
            manifest,
            sequence=len(running_state.events) + 1,
            operation=FormalRunOperation.FAIL,
            from_status=FormalRunStatus.RUNNING,
            to_status=FormalRunStatus.FAILED,
            request=root_request,
            attempt_number=manifest.attempt_number,
            payload={"code": code.value, "message": message},
            failure=failure,
        )
        failed_state = self._state(
            manifest,
            (*running_state.events, event),
            FormalRunStatus.FAILED,
        )
        terminal = FormalAssessmentTerminalFailure(
            schema_version=FORMAL_ASSESSMENT_RESULT_SCHEMA,
            store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
            terminal_record_id=self._id("formal-terminal"),
            manifest=manifest,
            status=FormalRunStatus.FAILED,
            failure=failure,
            occurred_at=self._now(),
        )
        try:
            self.repository.append_terminal_record(
                event,
                failed_state,
                terminal,
                attempt_number=manifest.attempt_number,
            )
        except PersistenceError as exc:
            return FormalRunRecoveryRequired(
                FormalRunFailureCode.TERMINAL_PERSISTENCE_FAILED,
                f"The engine ran once, but failure persistence failed: {exc}",
                manifest,
                running_state,
                replayed=False,
            )
        except Exception as exc:
            return FormalRunRecoveryRequired(
                FormalRunFailureCode.TERMINAL_PERSISTENCE_FAILED,
                f"The engine ran once, but failure persistence failed: {exc}",
                manifest,
                running_state,
                replayed=False,
            )
        return FormalRunTerminalFailure(terminal, replayed=False)

    def _recover_event(
        self,
        authorization: object,
        *,
        request: object,
        operation: FormalRunOperation,
        allowed: set[FormalRunStatus],
        target: FormalRunStatus,
        code: FormalRunFailureCode,
        message: str,
    ) -> FormalRunOutcome:
        validated_authorization = self._authorization_or_rejection(authorization)
        if isinstance(validated_authorization, FormalRunPreRunRejection):
            return validated_authorization
        validated_request = self._request_or_rejection(request)
        if isinstance(validated_request, FormalRunPreRunRejection):
            return validated_request
        manifest_state = self._latest_manifest_state(validated_authorization)
        if isinstance(manifest_state, FormalRunPreRunRejection):
            return manifest_state
        manifest, state = manifest_state
        replay = self._recovery_replay(validated_request, manifest, state)
        if replay is not None:
            return replay
        writable = self._require_writable()
        if writable is not None:
            return writable
        if state.current_status not in allowed:
            return self._recovery_rejection(
                manifest,
                state,
                "This recovery transition is not permitted.",
            )
        event = self._event(
            manifest,
            sequence=len(state.events) + 1,
            operation=operation,
            from_status=state.current_status,
            to_status=target,
            request=validated_request,
            attempt_number=manifest.attempt_number,
            payload={"recovery": operation.value},
            use_external_identity=True,
        )
        next_state = self._state(manifest, (*state.events, event), target)
        try:
            self.repository.append_event(
                event,
                next_state,
                attempt_number=manifest.attempt_number,
            )
        except PersistenceError as exc:
            return self._recovery_rejection(
                manifest,
                state,
                f"The recovery transition could not be persisted: {exc}",
            )
        except Exception as exc:
            return self._recovery_rejection(
                manifest,
                state,
                f"The recovery transition could not be persisted: {exc}",
            )
        return FormalRunRecoveryRequired(code, message, manifest, next_state, replayed=False)

    def _existing_attempt(
        self,
        authorization: FormalAssessmentAuthorization,
        request: RequestIdentity,
        *,
        attempt_number: int,
    ) -> FormalRunOutcome | None:
        try:
            manifest = self.repository.load_manifest(
                authorization.run_lineage.run_id,
                attempt_number,
            )
        except ArtifactNotFoundError:
            try:
                used = self.repository.load_run_request(request.request_token)
            except ArtifactNotFoundError:
                return None
            except PersistenceError as exc:
                return FormalRunPreRunRejection(
                    FormalRunFailureCode.REPOSITORY_INTEGRITY_FAILED,
                    f"The request history cannot be read: {exc}",
                )
            return FormalRunPreRunRejection(
                FormalRunFailureCode.STALE_OR_CONFLICTING_REQUEST,
                "The request token is already bound to another immutable formal operation."
                if used.request != request
                else "The request token is already bound to another formal run attempt.",
            )
        except PersistenceError as exc:
            return FormalRunPreRunRejection(
                FormalRunFailureCode.REPOSITORY_INTEGRITY_FAILED,
                f"The existing run cannot be read safely: {exc}",
            )
        if manifest.authorization != authorization or manifest.request.request != request:
            return FormalRunPreRunRejection(
                FormalRunFailureCode.STALE_OR_CONFLICTING_REQUEST,
                "The run identity or request token is already bound to different "
                "immutable content.",
            )
        try:
            return self._outcome_for_attempt(manifest, replayed=True)
        except Exception as exc:
            return FormalRunPreRunRejection(
                FormalRunFailureCode.REPOSITORY_INTEGRITY_FAILED,
                f"The persisted run outcome cannot be read safely: {exc}",
            )

    def _outcome_for_attempt(
        self,
        manifest: FormalAssessmentRunManifest,
        *,
        replayed: bool,
    ) -> FormalRunOutcome:
        state = self.repository.load_run_state(
            manifest.run_lineage.run_id,
            manifest.attempt_number,
        )
        history = self.repository.run_history(manifest.run_lineage.run_id)
        terminal = next(
            (
                item
                for item in history.terminal_records
                if item.manifest.attempt_number == manifest.attempt_number
            ),
            None,
        )
        if state.current_status is FormalRunStatus.COMPLETED_PENDING_REVIEW:
            if not isinstance(terminal, FormalAssessmentResult):
                return FormalRunRecoveryRequired(
                    FormalRunFailureCode.REPOSITORY_INTEGRITY_FAILED,
                    "A completed run has no exact persisted successful result.",
                    manifest,
                    state,
                    replayed,
                )
            return FormalRunCompleted(terminal, replayed)
        if state.current_status is FormalRunStatus.FAILED and isinstance(
            terminal, FormalAssessmentTerminalFailure
        ):
            return FormalRunTerminalFailure(terminal, replayed)
        return FormalRunRecoveryRequired(
            FormalRunFailureCode.RECOVERY_REQUIRED,
            "This immutable attempt is incomplete or requires an explicit recovery action.",
            manifest,
            state,
            replayed,
        )

    def _latest_manifest_state(
        self, authorization: FormalAssessmentAuthorization
    ) -> tuple[FormalAssessmentRunManifest, FormalAssessmentRunState] | FormalRunPreRunRejection:
        try:
            history = self.repository.run_history(authorization.run_lineage.run_id)
        except PersistenceError as exc:
            return FormalRunPreRunRejection(
                FormalRunFailureCode.REPOSITORY_INTEGRITY_FAILED,
                f"The formal run history cannot be read: {exc}",
            )
        matching = [item for item in history.manifests if item.authorization == authorization]
        if not matching:
            return FormalRunPreRunRejection(
                FormalRunFailureCode.REPOSITORY_INTEGRITY_FAILED,
                "No persisted formal run belongs to the supplied authorization.",
            )
        manifest = matching[-1]
        try:
            return manifest, self.repository.load_run_state(
                manifest.run_lineage.run_id,
                manifest.attempt_number,
            )
        except PersistenceError as exc:
            return FormalRunPreRunRejection(
                FormalRunFailureCode.REPOSITORY_INTEGRITY_FAILED,
                f"The persisted formal run state is invalid: {exc}",
            )

    def _recovery_replay(
        self,
        request: RequestIdentity,
        manifest: FormalAssessmentRunManifest,
        state: FormalAssessmentRunState,
    ) -> FormalRunOutcome | None:
        try:
            persisted = self.repository.load_run_request(request.request_token)
        except ArtifactNotFoundError:
            return None
        except Exception as exc:
            return FormalRunPreRunRejection(
                FormalRunFailureCode.REPOSITORY_INTEGRITY_FAILED,
                f"The recovery request cannot be read safely: {exc}",
            )
        if persisted.request != request or persisted.run_lineage != manifest.run_lineage:
            return FormalRunPreRunRejection(
                FormalRunFailureCode.STALE_OR_CONFLICTING_REQUEST,
                "The recovery request token belongs to different immutable content.",
            )
        try:
            return self._outcome_for_attempt(manifest, replayed=True)
        except Exception as exc:
            return FormalRunPreRunRejection(
                FormalRunFailureCode.REPOSITORY_INTEGRITY_FAILED,
                f"The recovered run outcome cannot be read safely: {exc}",
            )

    def _recovery_rejection(
        self,
        manifest: FormalAssessmentRunManifest,
        state: FormalAssessmentRunState,
        message: str,
    ) -> FormalRunRecoveryRequired:
        return FormalRunRecoveryRequired(
            FormalRunFailureCode.RECOVERY_REQUIRED,
            message,
            manifest,
            state,
            replayed=False,
        )

    def _authorization_or_rejection(
        self, value: object
    ) -> FormalAssessmentAuthorization | FormalRunPreRunRejection:
        try:
            candidate = (
                value.model_dump(mode="json")
                if isinstance(value, BaseModel)
                else value
            )
            return FormalAssessmentAuthorization.model_validate(candidate)
        except (TypeError, ValueError, ValidationError) as exc:
            return FormalRunPreRunRejection(
                FormalRunFailureCode.INVALID_AUTHORIZATION,
                f"The formal authorization is invalid: {exc}",
            )

    def _review_or_rejection(
        self, value: object
    ) -> ApprovedProcessReview | FormalRunPreRunRejection:
        try:
            candidate = (
                value.model_dump(mode="json")
                if isinstance(value, BaseModel)
                else value
            )
            return ApprovedProcessReview.model_validate(candidate)
        except (TypeError, ValueError, ValidationError) as exc:
            return FormalRunPreRunRejection(
                FormalRunFailureCode.INVALID_APPROVED_REVIEW,
                f"The approved review is invalid: {exc}",
            )

    def _request_or_rejection(
        self, value: object
    ) -> RequestIdentity | FormalRunPreRunRejection:
        try:
            candidate = (
                value.model_dump(mode="json")
                if isinstance(value, BaseModel)
                else value
            )
            return RequestIdentity.model_validate(candidate)
        except (TypeError, ValueError, ValidationError) as exc:
            return FormalRunPreRunRejection(
                FormalRunFailureCode.STALE_OR_CONFLICTING_REQUEST,
                f"The request identity is invalid: {exc}",
            )

    def _require_writable(self) -> FormalRunPreRunRejection | None:
        try:
            self.repository.assert_writable()
        except Exception as exc:
            return FormalRunPreRunRejection(
                FormalRunFailureCode.REPOSITORY_INTEGRITY_FAILED,
                f"The formal-assessment repository is not writable: {exc}",
            )
        return None

    def _policy_or_rejection(
        self, authorization: FormalAssessmentAuthorization
    ) -> FourGateDecisionPolicy | FormalRunPreRunRejection:
        try:
            policy = self.policy_loader(self.policy_path)
            compatibility = authorization.compatibility
            if (
                _canonical_hash(policy) != FOUR_GATE_POLICY_FINGERPRINT
                or policy.policy_id != compatibility.policy_id
                or policy.version != compatibility.policy_version
                or policy.framework_id != compatibility.framework_id
                or policy.framework_version != compatibility.framework_version
                or policy.decision_contract_version != compatibility.output_contract
            ):
                raise ValueError("policy identity or fingerprint drift")
            return policy
        except Exception as exc:
            return FormalRunPreRunRejection(
                FormalRunFailureCode.COMPATIBILITY_OR_POLICY_DRIFT,
                f"The exact v0.3 strict policy is unavailable: {exc}",
            )

    def _validate_adapter_dependency(self) -> None:
        if not isinstance(self.adapter, FormalFourGateInputAdapter):
            raise TypeError("Formal Assessment requires FormalFourGateInputAdapter")
        try:
            rules = FormalFourGateInputAdapterRules.model_validate(
                self.adapter.rules.model_dump(mode="json")
                if isinstance(self.adapter.rules, BaseModel)
                else self.adapter.rules
            )
        except (TypeError, ValueError, ValidationError) as exc:
            raise ValueError("Formal Assessment adapter rules are invalid") from exc
        if rules != FORMAL_FOUR_GATE_INPUT_ADAPTER_RULES or (
            rules.adapter_id != FORMAL_INPUT_ADAPTER_ID
            or rules.adapter_version != FORMAL_INPUT_ADAPTER_VERSION
            or rules.rules_id != FORMAL_INPUT_ADAPTER_RULES_ID
            or rules.rules_fingerprint != FORMAL_INPUT_ADAPTER_RULES_FINGERPRINT
        ):
            raise ValueError("Formal Assessment adapter rules drift from D-037")

    def _run_request(
        self,
        root: RequestIdentity,
        *,
        operation: FormalRunOperation,
        lineage,
        attempt_number: int,
        payload: object,
        use_external_identity: bool = False,
    ) -> FormalAssessmentRunRequest:
        identity = root if use_external_identity else self._derived_request(
            root,
            operation,
            attempt_number,
        )
        return FormalAssessmentRunRequest(
            schema_version=FORMAL_ASSESSMENT_RUN_REQUEST_SCHEMA,
            store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
            request=identity,
            operation=operation,
            run_lineage=lineage,
            canonical_operation_payload_sha256=_canonical_hash(
                {
                    "root_request": root,
                    "operation": operation.value,
                    "attempt_number": attempt_number,
                    "lineage": lineage,
                    "payload": payload,
                }
            ),
            requested_at=self._now(),
        )

    def _event(
        self,
        manifest: FormalAssessmentRunManifest,
        *,
        sequence: int,
        operation: FormalRunOperation,
        from_status: FormalRunStatus,
        to_status: FormalRunStatus,
        request: RequestIdentity,
        attempt_number: int,
        payload: object,
        failure: FormalRunFailureDetails | None = None,
        use_external_identity: bool = False,
    ) -> FormalAssessmentRunEvent:
        run_request = self._run_request(
            request,
            operation=operation,
            lineage=manifest.run_lineage,
            attempt_number=attempt_number,
            payload=payload,
            use_external_identity=use_external_identity,
        )
        return FormalAssessmentRunEvent(
            schema_version=FORMAL_ASSESSMENT_RUN_EVENT_SCHEMA,
            store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
            event_id=self._stable_id(
                f"formal-{operation.value.lower()}-event",
                run_request.request,
            ),
            sequence=sequence,
            run_lineage=manifest.run_lineage,
            operation=operation,
            from_status=from_status,
            to_status=to_status,
            authorization_id=manifest.authorization.authorization_id,
            projection_id=manifest.projection.projection_id,
            projection_fingerprint=manifest.projection.projection_fingerprint,
            failure=failure,
            request=run_request,
            occurred_at=self._now(),
        )

    def _state(
        self,
        manifest: FormalAssessmentRunManifest,
        events: tuple[FormalAssessmentRunEvent, ...],
        status: FormalRunStatus,
    ) -> FormalAssessmentRunState:
        return FormalAssessmentRunState(
            schema_version=FORMAL_ASSESSMENT_RUN_STATE_SCHEMA,
            store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
            manifest=manifest,
            events=events,
            current_status=status,
            projected_at=self._now(),
        )

    def _derived_request(
        self,
        root: RequestIdentity,
        operation: FormalRunOperation,
        attempt_number: int,
    ) -> RequestIdentity:
        return RequestIdentity(
            request_token=(
                f"{root.request_token}:{operation.value.lower()}:{attempt_number}"
            ),
            canonical_request_sha256=_canonical_hash(
                {
                    "root_request": root,
                    "operation": operation.value,
                    "attempt_number": attempt_number,
                }
            ),
        )

    def _stable_id(self, prefix: str, request: RequestIdentity) -> str:
        return f"{prefix}-{_canonical_hash(request)[:24]}"

    def _id(self, prefix: str) -> str:
        value = self.id_factory(prefix)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Formal Assessment ID factory returned an invalid identifier")
        return value

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("Formal Assessment clock must return explicit UTC time")
        return value
