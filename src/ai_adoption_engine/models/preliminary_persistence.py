"""Versioned persistence contracts for the Preliminary Assessment journey.

The contracts in this module describe stored records only.  They do not expose
journey commands, derive journey state, run the evaluator, or bridge a
Preliminary Assessment into the formal assessment lifecycle.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_adoption_engine.models.preliminary_assessment import (
    AssessmentJourney,
    JourneySelection,
    PreliminaryAssessment,
)
from ai_adoption_engine.models.preliminary_assessment_v0_2 import (
    PreliminaryAssessmentV2,
)


PRELIMINARY_JOURNEY_STORE_ID = "preliminary-journey-store.v0.1"
PRELIMINARY_JOURNEY_STORE_VERSION = "0.1.0"
PRELIMINARY_EVALUATOR_ID = "preliminary-evaluator.v0.1"
PRELIMINARY_EVALUATOR_VERSION = "0.1.0"
PRELIMINARY_EVALUATOR_V0_2_ID = "preliminary-evaluator.v0.2"
PRELIMINARY_EVALUATOR_V0_2_VERSION = "0.2.0"
PRELIMINARY_RULE_SET_V0_1_ID = "preliminary-evaluator-rules.v0.1"
PRELIMINARY_RULE_SET_V0_1_VERSION = "0.1.0"
PRELIMINARY_RULE_SET_V0_1_STATUS = "PROVISIONAL CONTINUITY — NOT VALIDATED"
PRELIMINARY_RULE_SET_V0_1_FINGERPRINT = (
    "3db8a54561bcfe263a5483e5d4c49e203bfac40eafbc8bc778cf773ed6ad1790"
)
PRELIMINARY_RULE_SET_V0_2_ID = "preliminary-evaluator-rules.v0.2"
PRELIMINARY_RULE_SET_V0_2_VERSION = "0.2.0"
PRELIMINARY_RULE_SET_V0_2_STATUS = "PROVISIONAL EXPLORATION — NOT VALIDATED"
PRELIMINARY_RULE_SET_V0_2_FINGERPRINT = (
    "1c06b6a9ce1fe9ee3f68c9b16a452ca2c283e3423a39ae6ef43bd5ccecb855c6"
)

PRELIMINARY_JOURNEY_SCHEMA_VERSION = "preliminary-journey.v0.1"
PRELIMINARY_JOURNEY_EVENT_SCHEMA_VERSION = "preliminary-journey-event.v0.1"
PRELIMINARY_RUN_MANIFEST_SCHEMA_VERSION = "preliminary-run-manifest.v0.1"
PRELIMINARY_RUN_EVENT_SCHEMA_VERSION = "preliminary-run-event.v0.1"
PRELIMINARY_RUN_STATE_PROJECTION_SCHEMA_VERSION = (
    "preliminary-run-state-projection.v0.1"
)
PRELIMINARY_RESULT_SCHEMA_VERSION = "preliminary-result.v0.1"
PRELIMINARY_RESULT_SUPERSESSION_SCHEMA_VERSION = (
    "preliminary-result-supersession.v0.1"
)
PRELIMINARY_FORMAL_LIFECYCLE_SCHEMA_VERSION = (
    "preliminary-formal-lifecycle.v0.1"
)
PRELIMINARY_FORMAL_START_REQUEST_SCHEMA_VERSION = (
    "preliminary-formal-start-request.v0.1"
)
PRELIMINARY_ROUTE_REQUEST_SCHEMA_VERSION = "preliminary-route-request.v0.1"


class _FrozenPersistenceContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PreliminaryPersistenceRecordType(StrEnum):
    JOURNEY = "JOURNEY"
    JOURNEY_EVENT = "JOURNEY_EVENT"
    RUN_MANIFEST = "RUN_MANIFEST"
    RUN_EVENT = "RUN_EVENT"
    RUN_STATE_PROJECTION = "RUN_STATE_PROJECTION"
    PRELIMINARY_RESULT = "PRELIMINARY_RESULT"
    RESULT_SUPERSESSION = "RESULT_SUPERSESSION"
    FORMAL_LIFECYCLE = "FORMAL_LIFECYCLE"
    FORMAL_START_REQUEST = "FORMAL_START_REQUEST"
    ROUTE_REQUEST = "ROUTE_REQUEST"


class PreliminaryJourneyEventType(StrEnum):
    JOURNEY_CREATED = "JOURNEY_CREATED"
    ROUTE_SELECTED = "ROUTE_SELECTED"
    ROUTE_CHANGED = "ROUTE_CHANGED"
    RUN_LINKED = "RUN_LINKED"
    RUN_RECOVERY_RECORDED = "RUN_RECOVERY_RECORDED"
    RESULT_RECORDED = "RESULT_RECORDED"
    RESULT_SUPERSEDED = "RESULT_SUPERSEDED"
    FORMAL_LIFECYCLE_STARTED = "FORMAL_LIFECYCLE_STARTED"


class PreliminaryRunEventType(StrEnum):
    RUN_STARTED = "RUN_STARTED"
    RUN_COMPLETED = "RUN_COMPLETED"
    RUN_FAILED = "RUN_FAILED"
    RUN_ABANDONED = "RUN_ABANDONED"


class PreliminaryRunProjectedStatus(StrEnum):
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ABANDONED = "ABANDONED"


class PreliminaryRecoveryAction(StrEnum):
    ABANDON = "ABANDON"
    RETRY = "RETRY"


class PreliminaryFormalLifecycleStatus(StrEnum):
    AWAITING_FORMAL_INPUTS = "AWAITING_FORMAL_INPUTS"


class PreliminaryResultReferenceUse(StrEnum):
    CONTEXT_ONLY_NOT_FORMAL_EVIDENCE = "CONTEXT_ONLY_NOT_FORMAL_EVIDENCE"


class PreliminaryEvaluatorReference(_FrozenPersistenceContract):
    evaluator_id: Literal[
        "preliminary-evaluator.v0.1", "preliminary-evaluator.v0.2"
    ]
    evaluator_version: Literal["0.1.0", "0.2.0"]

    @model_validator(mode="after")
    def validate_exact_evaluator_identity(self) -> Self:
        if (self.evaluator_id, self.evaluator_version) not in {
            (PRELIMINARY_EVALUATOR_ID, PRELIMINARY_EVALUATOR_VERSION),
            (PRELIMINARY_EVALUATOR_V0_2_ID, PRELIMINARY_EVALUATOR_V0_2_VERSION),
        }:
            raise ValueError("Unsupported Preliminary evaluator identity")
        return self


class PersistedPreliminaryRuleSetReference(_FrozenPersistenceContract):
    rule_set_id: Literal[
        "preliminary-evaluator-rules.v0.1",
        "preliminary-evaluator-rules.v0.2",
    ]
    rule_set_version: Literal["0.1.0", "0.2.0"]
    rule_set_status: Literal[
        "PROVISIONAL CONTINUITY — NOT VALIDATED",
        "PROVISIONAL EXPLORATION — NOT VALIDATED",
    ]
    rule_set_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_exact_rule_identity(self) -> Self:
        identity = (
            self.rule_set_id,
            self.rule_set_version,
            self.rule_set_status,
            self.rule_set_fingerprint,
        )
        if identity not in {
            (
                PRELIMINARY_RULE_SET_V0_1_ID,
                PRELIMINARY_RULE_SET_V0_1_VERSION,
                PRELIMINARY_RULE_SET_V0_1_STATUS,
                PRELIMINARY_RULE_SET_V0_1_FINGERPRINT,
            ),
            (
                PRELIMINARY_RULE_SET_V0_2_ID,
                PRELIMINARY_RULE_SET_V0_2_VERSION,
                PRELIMINARY_RULE_SET_V0_2_STATUS,
                PRELIMINARY_RULE_SET_V0_2_FINGERPRINT,
            ),
        }:
            raise ValueError("Unsupported Preliminary rule identity")
        return self


def _validate_compatibility_identity(
    evaluator: PreliminaryEvaluatorReference,
    rule_set: PersistedPreliminaryRuleSetReference,
    output_schema_version: str,
) -> None:
    identity = (
        evaluator.evaluator_id,
        evaluator.evaluator_version,
        rule_set.rule_set_id,
        rule_set.rule_set_version,
        rule_set.rule_set_fingerprint,
        output_schema_version,
    )
    if identity not in {
        (
            PRELIMINARY_EVALUATOR_ID,
            PRELIMINARY_EVALUATOR_VERSION,
            PRELIMINARY_RULE_SET_V0_1_ID,
            PRELIMINARY_RULE_SET_V0_1_VERSION,
            PRELIMINARY_RULE_SET_V0_1_FINGERPRINT,
            "preliminary-assessment.v0.1",
        ),
        (
            PRELIMINARY_EVALUATOR_V0_2_ID,
            PRELIMINARY_EVALUATOR_V0_2_VERSION,
            PRELIMINARY_RULE_SET_V0_2_ID,
            PRELIMINARY_RULE_SET_V0_2_VERSION,
            PRELIMINARY_RULE_SET_V0_2_FINGERPRINT,
            "preliminary-assessment.v0.2",
        ),
    }:
        raise ValueError("Unsupported or mixed Preliminary compatibility identity")


class PreliminarySourceSnapshot(_FrozenPersistenceContract):
    """Immutable source and approval identity shared by all stored records."""

    source_assessment_id: str = Field(min_length=1)
    approved_review_artifact_id: str = Field(min_length=1)
    approved_review_schema_version: Literal["phase4-v0.1"]
    approved_review_payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_document_id: str = Field(pattern=r"^doc-[0-9a-f]{64}$")
    extraction_run_id: str = Field(min_length=1)
    review_id: str = Field(min_length=1)
    approval_event_id: str = Field(min_length=1)
    approved_at: datetime
    validated_process_id: str = Field(min_length=1)
    validated_process_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class PreliminaryJourney(_FrozenPersistenceContract):
    schema_version: Literal["preliminary-journey.v0.1"]
    store_id: Literal["preliminary-journey-store.v0.1"]
    store_version: Literal["0.1.0"]
    journey_id: str = Field(min_length=1)
    source: PreliminarySourceSnapshot
    created_at: datetime


class JourneyCreatedPayload(_FrozenPersistenceContract):
    schema_version: Literal["journey-created.v0.1"]
    journey_id: str = Field(min_length=1)
    source_assessment_id: str = Field(min_length=1)
    approved_review_artifact_id: str = Field(min_length=1)


class PreliminaryRunLinkedPayload(_FrozenPersistenceContract):
    schema_version: Literal["preliminary-run-link.v0.1"]
    preliminary_run_id: str = Field(min_length=1)
    route_choice_event_id: str = Field(min_length=1)
    route_choice_event_sequence: int = Field(ge=1)


class PreliminaryRunRecoveryPayload(_FrozenPersistenceContract):
    schema_version: Literal["preliminary-run-recovery.v0.1"]
    abandoned_run_id: str = Field(min_length=1)
    retry_run_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_distinct_runs(self) -> Self:
        if self.abandoned_run_id == self.retry_run_id:
            raise ValueError("A retry must use a new Preliminary run ID")
        return self


class PreliminaryRunRecoveryV2Payload(_FrozenPersistenceContract):
    """Closed audit payload for explicit abandonment or retry recovery."""

    schema_version: Literal["preliminary-run-recovery.v0.2"]
    action: PreliminaryRecoveryAction
    recovery_request_token: str = Field(min_length=1)
    predecessor_run_id: str = Field(min_length=1)
    retry_run_id: str | None = Field(default=None, min_length=1)
    terminal_run_event_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_action_shape(self) -> Self:
        if self.action is PreliminaryRecoveryAction.ABANDON:
            if self.retry_run_id is not None or self.terminal_run_event_id is None:
                raise ValueError(
                    "Abandonment recovery requires only its terminal run event"
                )
        elif (
            self.retry_run_id is None
            or self.retry_run_id == self.predecessor_run_id
            or self.terminal_run_event_id is not None
        ):
            raise ValueError(
                "Retry recovery requires one distinct retry run and no terminal event"
            )
        return self


class PreliminaryResultRecordedPayload(_FrozenPersistenceContract):
    schema_version: Literal["preliminary-result-recorded.v0.1"]
    preliminary_run_id: str = Field(min_length=1)
    preliminary_result_id: str = Field(min_length=1)


class PreliminaryResultSupersessionPayload(_FrozenPersistenceContract):
    schema_version: Literal["preliminary-result-supersession.v0.1"]
    superseded_result_id: str = Field(min_length=1)
    superseding_result_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_distinct_results(self) -> Self:
        if self.superseded_result_id == self.superseding_result_id:
            raise ValueError("A Preliminary result cannot supersede itself")
        return self


class PreliminaryFormalLifecycleStartedPayload(_FrozenPersistenceContract):
    schema_version: Literal["formal-lifecycle-start.v0.1"]
    formal_lifecycle_id: str = Field(min_length=1)
    route_choice_event_id: str = Field(min_length=1)
    route_choice_event_sequence: int = Field(ge=1)


PreliminaryJourneyEventPayload = Annotated[
    JourneyCreatedPayload
    | JourneySelection
    | PreliminaryRunLinkedPayload
    | PreliminaryRunRecoveryPayload
    | PreliminaryRunRecoveryV2Payload
    | PreliminaryResultRecordedPayload
    | PreliminaryResultSupersessionPayload
    | PreliminaryFormalLifecycleStartedPayload,
    Field(discriminator="schema_version"),
]


_JOURNEY_EVENT_PAYLOAD_SCHEMAS = {
    PreliminaryJourneyEventType.JOURNEY_CREATED: {"journey-created.v0.1"},
    PreliminaryJourneyEventType.ROUTE_SELECTED: {"journey-selection.v0.1"},
    PreliminaryJourneyEventType.ROUTE_CHANGED: {"journey-selection.v0.1"},
    PreliminaryJourneyEventType.RUN_LINKED: {"preliminary-run-link.v0.1"},
    PreliminaryJourneyEventType.RUN_RECOVERY_RECORDED: {
        "preliminary-run-recovery.v0.1",
        "preliminary-run-recovery.v0.2",
    },
    PreliminaryJourneyEventType.RESULT_RECORDED: {
        "preliminary-result-recorded.v0.1"
    },
    PreliminaryJourneyEventType.RESULT_SUPERSEDED: {
        "preliminary-result-supersession.v0.1"
    },
    PreliminaryJourneyEventType.FORMAL_LIFECYCLE_STARTED: {
        "formal-lifecycle-start.v0.1"
    },
}


class PreliminaryJourneyEvent(_FrozenPersistenceContract):
    schema_version: Literal["preliminary-journey-event.v0.1"]
    event_id: str = Field(min_length=1)
    journey_id: str = Field(min_length=1)
    event_sequence: int = Field(ge=1)
    event_type: PreliminaryJourneyEventType
    occurred_at: datetime
    payload: PreliminaryJourneyEventPayload

    @model_validator(mode="after")
    def validate_event_payload(self) -> Self:
        if (
            self.payload.schema_version
            not in _JOURNEY_EVENT_PAYLOAD_SCHEMAS[self.event_type]
        ):
            raise ValueError("Journey event type and payload schema must match")
        if isinstance(self.payload, JourneyCreatedPayload):
            if self.payload.journey_id != self.journey_id:
                raise ValueError("Journey-created payload must identify its journey")
            if self.event_sequence != 1:
                raise ValueError("JOURNEY_CREATED must be the first journey event")
        return self


class PreliminaryRouteRequest(_FrozenPersistenceContract):
    """Immutable idempotency record for one route-selection request."""

    schema_version: Literal["preliminary-route-request.v0.1"]
    route_request_id: str = Field(min_length=1)
    journey_id: str = Field(min_length=1)
    request_token: str = Field(min_length=1)
    requested_route: AssessmentJourney
    expected_latest_sequence: int = Field(ge=1)
    event_appended: bool
    resulting_event_id: str | None = Field(default=None, min_length=1)
    effective_route_event_id: str = Field(min_length=1)
    effective_route_event_sequence: int = Field(ge=1)
    latest_sequence_after_request: int = Field(ge=1)
    created_at: datetime

    @model_validator(mode="after")
    def validate_route_request_result(self) -> Self:
        if self.event_appended != (self.resulting_event_id is not None):
            raise ValueError(
                "Only a route request that appended an event may identify it"
            )
        if self.event_appended:
            if self.resulting_event_id != self.effective_route_event_id:
                raise ValueError("An appended route event must become effective")
            if self.latest_sequence_after_request != self.expected_latest_sequence + 1:
                raise ValueError("An appended route event must advance sequence once")
            if self.effective_route_event_sequence != self.latest_sequence_after_request:
                raise ValueError("The appended route event sequence must be effective")
        elif self.latest_sequence_after_request != self.expected_latest_sequence:
            raise ValueError("A no-op route request cannot advance journey sequence")
        return self


class PreliminaryRunManifest(_FrozenPersistenceContract):
    schema_version: Literal["preliminary-run-manifest.v0.1"]
    store_id: Literal["preliminary-journey-store.v0.1"]
    preliminary_run_id: str = Field(min_length=1)
    journey_id: str = Field(min_length=1)
    request_token: str = Field(min_length=1)
    retry_of_run_id: str | None = Field(default=None, min_length=1)
    route_choice_event_id: str = Field(min_length=1)
    route_choice_event_sequence: int = Field(ge=1)
    source: PreliminarySourceSnapshot
    evaluator: PreliminaryEvaluatorReference
    rule_set: PersistedPreliminaryRuleSetReference
    output_schema_version: Literal[
        "preliminary-assessment.v0.1", "preliminary-assessment.v0.2"
    ]
    created_at: datetime

    @field_validator("rule_set", mode="before")
    @classmethod
    def normalize_rule_reference(cls, value: object) -> object:
        return value.model_dump() if isinstance(value, BaseModel) else value

    @model_validator(mode="after")
    def require_new_retry_identity(self) -> Self:
        if self.retry_of_run_id == self.preliminary_run_id:
            raise ValueError("A retry cannot reuse its predecessor run ID")
        _validate_compatibility_identity(
            self.evaluator, self.rule_set, self.output_schema_version
        )
        return self


class PreliminaryRunStartedPayload(_FrozenPersistenceContract):
    schema_version: Literal["preliminary-run-started.v0.1"]
    preliminary_run_id: str = Field(min_length=1)


class PreliminaryRunCompletedPayload(_FrozenPersistenceContract):
    schema_version: Literal["preliminary-run-completed.v0.1"]
    preliminary_run_id: str = Field(min_length=1)
    preliminary_result_id: str = Field(min_length=1)


class PreliminaryRunFailedPayload(_FrozenPersistenceContract):
    schema_version: Literal["preliminary-run-failed.v0.1"]
    preliminary_run_id: str = Field(min_length=1)
    error_code: str = Field(min_length=1)


class PreliminaryRunAbandonedPayload(_FrozenPersistenceContract):
    schema_version: Literal["preliminary-run-abandoned.v0.1"]
    preliminary_run_id: str = Field(min_length=1)
    reason_code: str = Field(min_length=1)


PreliminaryRunEventPayload = Annotated[
    PreliminaryRunStartedPayload
    | PreliminaryRunCompletedPayload
    | PreliminaryRunFailedPayload
    | PreliminaryRunAbandonedPayload,
    Field(discriminator="schema_version"),
]


_RUN_EVENT_PAYLOAD_SCHEMA = {
    PreliminaryRunEventType.RUN_STARTED: "preliminary-run-started.v0.1",
    PreliminaryRunEventType.RUN_COMPLETED: "preliminary-run-completed.v0.1",
    PreliminaryRunEventType.RUN_FAILED: "preliminary-run-failed.v0.1",
    PreliminaryRunEventType.RUN_ABANDONED: "preliminary-run-abandoned.v0.1",
}


class PreliminaryRunLifecycleEvent(_FrozenPersistenceContract):
    schema_version: Literal["preliminary-run-event.v0.1"]
    run_event_id: str = Field(min_length=1)
    preliminary_run_id: str = Field(min_length=1)
    journey_id: str = Field(min_length=1)
    event_sequence: int = Field(ge=1, le=2)
    event_type: PreliminaryRunEventType
    occurred_at: datetime
    payload: PreliminaryRunEventPayload

    @model_validator(mode="after")
    def validate_event_payload(self) -> Self:
        if self.payload.schema_version != _RUN_EVENT_PAYLOAD_SCHEMA[self.event_type]:
            raise ValueError("Run event type and payload schema must match")
        if self.payload.preliminary_run_id != self.preliminary_run_id:
            raise ValueError("Run event payload must identify its run")
        if (
            self.event_type is PreliminaryRunEventType.RUN_STARTED
            and self.event_sequence != 1
        ):
            raise ValueError("RUN_STARTED must be the first run event")
        if (
            self.event_type is not PreliminaryRunEventType.RUN_STARTED
            and self.event_sequence != 2
        ):
            raise ValueError("A terminal event must be the second run event")
        return self


class PreliminaryRunStateProjection(_FrozenPersistenceContract):
    schema_version: Literal["preliminary-run-state-projection.v0.1"]
    preliminary_run_id: str = Field(min_length=1)
    journey_id: str = Field(min_length=1)
    projected_status: PreliminaryRunProjectedStatus
    terminal_event_id: str | None = Field(default=None, min_length=1)
    projected_at: datetime

    @model_validator(mode="after")
    def validate_terminal_reference(self) -> Self:
        terminal = self.projected_status is not PreliminaryRunProjectedStatus.STARTED
        if terminal != (self.terminal_event_id is not None):
            raise ValueError("Only terminal projections carry a terminal event ID")
        return self


class PersistedPreliminaryResult(_FrozenPersistenceContract):
    schema_version: Literal["preliminary-result.v0.1"]
    preliminary_result_id: str = Field(min_length=1)
    preliminary_run_id: str = Field(min_length=1)
    journey_id: str = Field(min_length=1)
    completed_run_event_id: str = Field(min_length=1)
    source: PreliminarySourceSnapshot
    evaluator: PreliminaryEvaluatorReference
    rule_set: PersistedPreliminaryRuleSetReference
    output_schema_version: Literal[
        "preliminary-assessment.v0.1", "preliminary-assessment.v0.2"
    ]
    created_at: datetime
    assessment: Annotated[
        PreliminaryAssessment | PreliminaryAssessmentV2,
        Field(discriminator="schema_version"),
    ]

    @field_validator("rule_set", mode="before")
    @classmethod
    def normalize_rule_reference(cls, value: object) -> object:
        return value.model_dump() if isinstance(value, BaseModel) else value

    @model_validator(mode="after")
    def validate_pinned_result(self) -> Self:
        _validate_compatibility_identity(
            self.evaluator, self.rule_set, self.output_schema_version
        )
        if (
            isinstance(self.assessment, PreliminaryAssessment)
            and self.assessment.preliminary_assessment_id != self.preliminary_run_id
        ):
            raise ValueError("The stored assessment must use the run identity")
        if self.assessment.schema_version != self.output_schema_version:
            raise ValueError("Stored output schema does not match its pin")
        if isinstance(self.assessment, PreliminaryAssessment):
            if self.assessment.rule_set.model_dump() != self.rule_set.model_dump():
                raise ValueError("Stored rule identity does not match its pin")
        elif (
            self.assessment.evaluator_id != self.evaluator.evaluator_id
            or self.assessment.evaluator_version != self.evaluator.evaluator_version
            or self.assessment.rule_set_id != self.rule_set.rule_set_id
            or self.assessment.rule_set_version != self.rule_set.rule_set_version
            or self.assessment.rule_set_fingerprint
            != self.rule_set.rule_set_fingerprint
        ):
            raise ValueError("Stored v0.2 identity does not match its pins")
        lineage = self.assessment.lineage
        if (
            lineage.source_document_id != self.source.source_document_id
            or lineage.extraction_run_id != self.source.extraction_run_id
            or lineage.approval_event_id != self.source.approval_event_id
            or lineage.validated_process_id != self.source.validated_process_id
            or lineage.validated_process_fingerprint
            != self.source.validated_process_fingerprint
        ):
            raise ValueError("Stored assessment lineage does not match its source pin")
        if isinstance(self.assessment, PreliminaryAssessment) and (
            lineage.review_id != self.source.review_id
            or lineage.approved_at != self.source.approved_at
        ):
            raise ValueError("Stored v0.1 lineage does not match its source pin")
        return self


class PreliminaryResultSupersession(_FrozenPersistenceContract):
    schema_version: Literal["preliminary-result-supersession.v0.1"]
    supersession_id: str = Field(min_length=1)
    journey_id: str = Field(min_length=1)
    superseded_result_id: str = Field(min_length=1)
    superseding_result_id: str = Field(min_length=1)
    occurred_at: datetime

    @model_validator(mode="after")
    def require_distinct_results(self) -> Self:
        if self.superseded_result_id == self.superseding_result_id:
            raise ValueError("A Preliminary result cannot supersede itself")
        return self


class PreliminaryFormalLifecycle(_FrozenPersistenceContract):
    schema_version: Literal["preliminary-formal-lifecycle.v0.1"]
    formal_lifecycle_id: str = Field(min_length=1)
    journey_id: str = Field(min_length=1)
    source: PreliminarySourceSnapshot
    route_choice_event_id: str = Field(min_length=1)
    route_choice_event_sequence: int = Field(ge=1)
    status: Literal["AWAITING_FORMAL_INPUTS"]
    preliminary_result_id: str | None = Field(default=None, min_length=1)
    preliminary_result_use: Literal[
        "CONTEXT_ONLY_NOT_FORMAL_EVIDENCE"
    ] | None = None
    created_at: datetime

    @model_validator(mode="after")
    def validate_context_reference(self) -> Self:
        if (self.preliminary_result_id is None) != (
            self.preliminary_result_use is None
        ):
            raise ValueError(
                "A referenced Preliminary result must be context-only and explicit"
            )
        return self


class PreliminaryFormalStartRequest(_FrozenPersistenceContract):
    """Immutable idempotency identity for one formal-start operation."""

    schema_version: Literal["preliminary-formal-start-request.v0.1"]
    formal_start_request_id: str = Field(min_length=1)
    journey_id: str = Field(min_length=1)
    request_token: str = Field(min_length=1)
    formal_lifecycle_id: str = Field(min_length=1)
    route_choice_event_id: str = Field(min_length=1)
    route_choice_event_sequence: int = Field(ge=1)
    preliminary_result_id: str | None = Field(default=None, min_length=1)
    preliminary_result_use: Literal[
        "CONTEXT_ONLY_NOT_FORMAL_EVIDENCE"
    ] | None = None
    created_at: datetime

    @model_validator(mode="after")
    def validate_context_reference(self) -> Self:
        if (self.preliminary_result_id is None) != (
            self.preliminary_result_use is None
        ):
            raise ValueError(
                "A formal-start result reference must be context-only and explicit"
            )
        return self
