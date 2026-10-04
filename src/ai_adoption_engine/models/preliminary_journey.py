"""Read and command contracts for the explicit Preliminary journey service."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from ai_adoption_engine.models.preliminary_assessment import AssessmentJourney
from ai_adoption_engine.models.preliminary_persistence import (
    PersistedPreliminaryResult,
    PreliminaryFormalLifecycle,
    PreliminaryFormalStartRequest,
    PreliminaryJourney,
    PreliminaryJourneyEvent,
    PreliminaryRouteRequest,
    PreliminaryJourneyEventType,
    PreliminaryFormalLifecycleStartedPayload,
    PreliminaryResultSupersession,
    PreliminaryRunLifecycleEvent,
    PreliminaryRunManifest,
    PreliminaryRunProjectedStatus,
)


class _FrozenJourneyContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PreliminaryCurrentRoute(StrEnum):
    UNSELECTED = "UNSELECTED"
    EXPLORE_PROCESS = "EXPLORE_PROCESS"
    ORGANISATIONAL_ASSESSMENT = "ORGANISATIONAL_ASSESSMENT"


class PreliminaryJourneyStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    RUNNING = "RUNNING"
    AVAILABLE = "AVAILABLE"
    RETRY_AVAILABLE = "RETRY_AVAILABLE"
    RERUN_REQUIRED = "RERUN_REQUIRED"


class FormalLifecycleStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    AWAITING_FORMAL_INPUTS = "AWAITING_FORMAL_INPUTS"


class ApprovedReviewArtifactPin(_FrozenJourneyContract):
    assessment_id: str = Field(min_length=1)
    artifact_id: str = Field(min_length=1)
    artifact_revision: int = Field(ge=1)
    artifact_schema_version: str = Field(min_length=1)
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PreliminaryCompatibilityIdentity(_FrozenJourneyContract):
    evaluator_id: str = Field(min_length=1)
    evaluator_version: str = Field(min_length=1)
    rule_set_id: str = Field(min_length=1)
    rule_set_version: str = Field(min_length=1)
    rule_set_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_schema_version: str = Field(min_length=1)


class JourneyCreationResult(_FrozenJourneyContract):
    journey: PreliminaryJourney
    created: bool


class RouteSelectionResult(_FrozenJourneyContract):
    request: PreliminaryRouteRequest
    effective_route_event: PreliminaryJourneyEvent
    replayed: bool


class FormalStartResult(_FrozenJourneyContract):
    request: PreliminaryFormalStartRequest
    lifecycle: PreliminaryFormalLifecycle
    start_event: PreliminaryJourneyEvent
    replayed: bool

    def model_post_init(self, __context: object) -> None:
        payload = self.start_event.payload
        if (
            self.start_event.event_type
            is not PreliminaryJourneyEventType.FORMAL_LIFECYCLE_STARTED
            or not isinstance(payload, PreliminaryFormalLifecycleStartedPayload)
            or self.request.formal_lifecycle_id
            != self.lifecycle.formal_lifecycle_id
            or payload.formal_lifecycle_id != self.lifecycle.formal_lifecycle_id
            or self.request.journey_id != self.lifecycle.journey_id
            or self.start_event.journey_id != self.lifecycle.journey_id
            or self.request.route_choice_event_id
            != self.lifecycle.route_choice_event_id
            or self.request.route_choice_event_sequence
            != self.lifecycle.route_choice_event_sequence
            or payload.route_choice_event_id
            != self.lifecycle.route_choice_event_id
            or payload.route_choice_event_sequence
            != self.lifecycle.route_choice_event_sequence
            or self.request.preliminary_result_id
            != self.lifecycle.preliminary_result_id
            or self.request.preliminary_result_use
            != self.lifecycle.preliminary_result_use
        ):
            raise ValueError("Formal-start result records must identify one lifecycle")


class PreliminaryJourneyState(_FrozenJourneyContract):
    journey: PreliminaryJourney
    latest_event_sequence: int = Field(ge=1)
    current_route: PreliminaryCurrentRoute
    current_route_event: PreliminaryJourneyEvent | None = None
    preliminary_status: PreliminaryJourneyStatus
    formal_lifecycle_status: FormalLifecycleStatus
    latest_compatible_result: PersistedPreliminaryResult | None = None
    active_preliminary_result: PersistedPreliminaryResult | None = None
    formal_lifecycle: PreliminaryFormalLifecycle | None = None

    @property
    def selected_route(self) -> AssessmentJourney | None:
        if self.current_route is PreliminaryCurrentRoute.UNSELECTED:
            return None
        return AssessmentJourney(self.current_route.value)


class PreliminaryRunHistoryItem(_FrozenJourneyContract):
    """Validated immutable history for one evaluator run."""

    manifest: PreliminaryRunManifest
    lifecycle_events: tuple[PreliminaryRunLifecycleEvent, ...] = Field(min_length=1)
    status: PreliminaryRunProjectedStatus
    result: PersistedPreliminaryResult | None = None
    superseded_by_result_id: str | None = Field(default=None, min_length=1)
    terminal_code: str | None = Field(default=None, min_length=1)


class PreliminaryJourneyHistory(_FrozenJourneyContract):
    """Presentation-safe validated state and immutable history."""

    state: PreliminaryJourneyState
    journey_events: tuple[PreliminaryJourneyEvent, ...] = Field(min_length=1)
    runs: tuple[PreliminaryRunHistoryItem, ...] = ()
    supersessions: tuple[PreliminaryResultSupersession, ...] = ()
