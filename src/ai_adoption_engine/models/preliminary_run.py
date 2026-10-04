"""Typed command result for persisted Preliminary evaluator runs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

from ai_adoption_engine.models.preliminary_persistence import (
    PersistedPreliminaryResult,
    PreliminaryJourneyEvent,
    PreliminaryJourneyEventType,
    PreliminaryRecoveryAction,
    PreliminaryResultSupersession,
    PreliminaryRunEventType,
    PreliminaryRunLifecycleEvent,
    PreliminaryRunManifest,
    PreliminaryRunProjectedStatus,
    PreliminaryRunRecoveryV2Payload,
)


class PreliminaryRunOperationResult(BaseModel):
    """Persisted state returned for a new run or transport replay."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest: PreliminaryRunManifest
    started_event: PreliminaryRunLifecycleEvent
    status: PreliminaryRunProjectedStatus
    terminal_event: PreliminaryRunLifecycleEvent | None = None
    result: PersistedPreliminaryResult | None = None
    supersession: PreliminaryResultSupersession | None = None
    terminal_code: str | None = None
    replayed: bool = False

    @model_validator(mode="after")
    def validate_persisted_outcome(self) -> "PreliminaryRunOperationResult":
        if (
            self.started_event.preliminary_run_id != self.manifest.preliminary_run_id
            or self.started_event.journey_id != self.manifest.journey_id
            or self.started_event.event_type is not PreliminaryRunEventType.RUN_STARTED
        ):
            raise ValueError("Started event must identify the returned run")
        if self.status is PreliminaryRunProjectedStatus.STARTED:
            if any(
                item is not None
                for item in (
                    self.terminal_event,
                    self.result,
                    self.supersession,
                    self.terminal_code,
                )
            ):
                raise ValueError("A started operation cannot carry terminal state")
            return self
        if self.terminal_event is None:
            raise ValueError("A terminal operation requires its immutable event")
        if (
            self.terminal_event.preliminary_run_id
            != self.manifest.preliminary_run_id
            or self.terminal_event.journey_id != self.manifest.journey_id
            or self.terminal_event.event_type.value != f"RUN_{self.status.value}"
        ):
            raise ValueError("Terminal event must match the returned status")
        if self.status is PreliminaryRunProjectedStatus.COMPLETED:
            if self.result is None or self.terminal_code is not None:
                raise ValueError("A completed operation requires one result only")
            if (
                self.result.preliminary_run_id != self.manifest.preliminary_run_id
                or self.result.journey_id != self.manifest.journey_id
                or self.result.completed_run_event_id
                != self.terminal_event.run_event_id
            ):
                raise ValueError("Completed result must match its run and event")
            if (
                self.supersession is not None
                and self.supersession.superseding_result_id
                != self.result.preliminary_result_id
            ):
                raise ValueError("Supersession must point to the returned result")
        elif self.result is not None or self.supersession is not None:
            raise ValueError("Failed or abandoned operations cannot carry a result")
        elif not self.terminal_code:
            raise ValueError("Failed or abandoned operations require a terminal code")
        return self


class PreliminaryRecoveryOperationResult(BaseModel):
    """Result of an explicit abandonment or retry recovery request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: PreliminaryRecoveryAction
    recovery_event: PreliminaryJourneyEvent
    operation: PreliminaryRunOperationResult
    replayed: bool = False

    @model_validator(mode="after")
    def validate_recovery_result(self) -> "PreliminaryRecoveryOperationResult":
        if (
            self.recovery_event.event_type
            is not PreliminaryJourneyEventType.RUN_RECOVERY_RECORDED
            or not isinstance(
                self.recovery_event.payload, PreliminaryRunRecoveryV2Payload
            )
            or self.recovery_event.payload.action is not self.action
            or self.recovery_event.journey_id
            != self.operation.manifest.journey_id
        ):
            raise ValueError("Recovery result must carry its closed journey event")
        payload = self.recovery_event.payload
        if self.action is PreliminaryRecoveryAction.ABANDON:
            if (
                self.operation.status
                is not PreliminaryRunProjectedStatus.ABANDONED
                or payload.predecessor_run_id
                != self.operation.manifest.preliminary_run_id
                or self.operation.terminal_event is None
                or payload.terminal_run_event_id
                != self.operation.terminal_event.run_event_id
            ):
                raise ValueError("Abandonment result does not match its operation")
        elif (
            payload.retry_run_id != self.operation.manifest.preliminary_run_id
            or self.operation.manifest.retry_of_run_id
            != payload.predecessor_run_id
        ):
            raise ValueError("Retry result does not match its retry lineage")
        return self
