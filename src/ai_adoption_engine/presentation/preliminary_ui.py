"""Shared activation, session intent, and safe Preliminary UI orchestration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from uuid import uuid4

import streamlit as st

from ai_adoption_engine.models.preliminary_assessment import AssessmentJourney
from ai_adoption_engine.models.preliminary_journey import (
    ApprovedReviewArtifactPin,
    FormalLifecycleStatus,
    PreliminaryCompatibilityIdentity,
    PreliminaryCurrentRoute,
    PreliminaryJourneyHistory,
    PreliminaryJourneyState,
    PreliminaryJourneyStatus,
)
from ai_adoption_engine.preliminary.composition import (
    PreliminaryServiceBundle,
    build_preliminary_service_bundle,
)
from ai_adoption_engine.preliminary.journey import (
    current_preliminary_compatibility_identity,
    preliminary_v0_2_compatibility_identity,
)
from ai_adoption_engine.presentation.context import (
    frozen_evaluation_workspace_selected,
)
from ai_adoption_engine.workspace.composition import DEFAULT_DATABASE_PATH
from ai_adoption_engine.workspace.models import ArtifactType, WorkspaceSnapshot


PRELIMINARY_UI_ENV = "AI_ADOPTION_ENGINE_PRELIMINARY_UI"
PRELIMINARY_EVALUATOR_ENV = "AI_ADOPTION_ENGINE_PRELIMINARY_EVALUATOR"
PRELIMINARY_EVALUATOR_V0_1 = "preliminary-evaluator.v0.1"
PRELIMINARY_EVALUATOR_V0_2 = "preliminary-evaluator.v0.2"
_TRUTHY = frozenset({"1", "true", "yes", "on"})
_INTENT_KEY = "preliminary_route_intent"
_ACTION_TOKENS_KEY = "preliminary_action_tokens"


@dataclass(frozen=True)
class PreliminaryRouteIntent:
    assessment_id: str
    source_document_id: str
    extraction_run_id: str
    route: AssessmentJourney


class UnsupportedPreliminaryEvaluatorConfiguration(ValueError):
    """The deployment requested no approved whole compatibility identity."""


def default_on_flag_enabled(name: str) -> bool:
    """Default-on kill switch (D-038).

    Unset or empty enables the feature; an explicit ``1/true/yes/on`` enables
    it; an explicit ``0/false/no/off`` disables it. Any other value fails closed
    (disabled) because the operator's intent is ambiguous.
    """

    value = os.environ.get(name, "").strip().lower()
    if value == "" or value in _TRUTHY:
        return True
    return False


def preliminary_ui_enabled() -> bool:
    """The one central activation decision: on unless explicitly switched off."""

    return default_on_flag_enabled(PRELIMINARY_UI_ENV)


def configured_preliminary_compatibility_identity() -> PreliminaryCompatibilityIdentity:
    """Resolve one evaluator selector to its complete frozen identity."""

    evaluator_id = os.environ.get(PRELIMINARY_EVALUATOR_ENV)
    # D-038: the latest evaluator (v0.2) is the default; v0.1 stays explicit.
    if evaluator_id is None or evaluator_id == "" or evaluator_id == PRELIMINARY_EVALUATOR_V0_2:
        return preliminary_v0_2_compatibility_identity()
    if evaluator_id == PRELIMINARY_EVALUATOR_V0_1:
        return current_preliminary_compatibility_identity()
    raise UnsupportedPreliminaryEvaluatorConfiguration(
        f"Unsupported {PRELIMINARY_EVALUATOR_ENV} value"
    )


@st.cache_resource
def _cached_preliminary_services(
    database_path: str,
    evaluator_id: str,
) -> PreliminaryServiceBundle:
    if evaluator_id == PRELIMINARY_EVALUATOR_V0_1:
        identity = current_preliminary_compatibility_identity()
    elif evaluator_id == PRELIMINARY_EVALUATOR_V0_2:
        identity = preliminary_v0_2_compatibility_identity()
    else:
        raise UnsupportedPreliminaryEvaluatorConfiguration(
            f"Unsupported {PRELIMINARY_EVALUATOR_ENV} value"
        )
    return build_preliminary_service_bundle(
        database_path,
        supported_identity=identity,
    )


def preliminary_services() -> PreliminaryServiceBundle:
    if not preliminary_ui_enabled():
        raise RuntimeError("Preliminary UI is not enabled")
    if frozen_evaluation_workspace_selected():
        raise RuntimeError("Preliminary writes are unavailable for frozen workspaces")
    identity = configured_preliminary_compatibility_identity()
    path = os.environ.get("AI_ADOPTION_ENGINE_DB_PATH", str(DEFAULT_DATABASE_PATH))
    return _cached_preliminary_services(path, identity.evaluator_id)


def clear_preliminary_session_state() -> None:
    st.session_state.pop(_INTENT_KEY, None)
    st.session_state.pop(_ACTION_TOKENS_KEY, None)
    for key in tuple(st.session_state):
        if key.startswith("preliminary_"):
            st.session_state.pop(key, None)


def _candidate_identity(snapshot: WorkspaceSnapshot) -> tuple[str, str] | None:
    artifact = snapshot.active_artifacts.get(ArtifactType.CANDIDATE_EXTRACTION_RESULT)
    candidate = getattr(artifact.payload, "candidate", None) if artifact else None
    if candidate is None:
        return None
    return candidate.source_document_id, candidate.extraction_run_id


def route_intent(snapshot: WorkspaceSnapshot) -> PreliminaryRouteIntent | None:
    raw = st.session_state.get(_INTENT_KEY)
    if not isinstance(raw, PreliminaryRouteIntent):
        return None
    identity = _candidate_identity(snapshot)
    if (
        identity is None
        or raw.assessment_id != snapshot.assessment.assessment_id
        or (raw.source_document_id, raw.extraction_run_id) != identity
    ):
        st.session_state.pop(_INTENT_KEY, None)
        return None
    return raw


def set_route_intent(
    snapshot: WorkspaceSnapshot,
    route: AssessmentJourney,
) -> PreliminaryRouteIntent:
    identity = _candidate_identity(snapshot)
    if identity is None:
        raise ValueError("A candidate extraction is required before route choice")
    intent = PreliminaryRouteIntent(
        assessment_id=snapshot.assessment.assessment_id,
        source_document_id=identity[0],
        extraction_run_id=identity[1],
        route=route,
    )
    st.session_state[_INTENT_KEY] = intent
    return intent


def render_route_choice(
    snapshot: WorkspaceSnapshot,
    *,
    key_prefix: str,
) -> PreliminaryRouteIntent | None:
    """Render the two equal pre-approval choices with one shared contract."""

    st.write(
        "Both routes validate and approve the same extracted current-state process first."
    )
    current = route_intent(snapshot)
    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            st.markdown("### Explore this process")
            st.write(
                "Get provisional activity-level directions and identify missing "
                "evidence. This is not approval to implement."
            )
            if st.button(
                "Explore this process",
                key=f"{key_prefix}-explore",
                type=(
                    "primary"
                    if current and current.route is AssessmentJourney.EXPLORE_PROCESS
                    else "secondary"
                ),
                width="stretch",
            ):
                current = set_route_intent(
                    snapshot, AssessmentJourney.EXPLORE_PROCESS
                )
                st.rerun()
    with right:
        with st.container(border=True):
            st.markdown("### Run an organisational assessment")
            st.write(
                "Set up a separate formal lifecycle. Additional organisational "
                "evidence will be required later."
            )
            if st.button(
                "Run an organisational assessment",
                key=f"{key_prefix}-organisational",
                type=(
                    "primary"
                    if current
                    and current.route
                    is AssessmentJourney.ORGANISATIONAL_ASSESSMENT
                    else "secondary"
                ),
                width="stretch",
            ):
                current = set_route_intent(
                    snapshot, AssessmentJourney.ORGANISATIONAL_ASSESSMENT
                )
                st.rerun()
    return current


def approved_review_pin(
    snapshot: WorkspaceSnapshot,
) -> ApprovedReviewArtifactPin | None:
    artifact = snapshot.active_artifacts.get(ArtifactType.APPROVED_REVIEW)
    if artifact is None:
        return None
    return ApprovedReviewArtifactPin(
        assessment_id=snapshot.assessment.assessment_id,
        artifact_id=artifact.artifact_id,
        artifact_revision=artifact.artifact_revision,
        artifact_schema_version=artifact.artifact_schema_version,
        payload_sha256=artifact.payload_sha256,
    )


def current_journey_state(
    snapshot: WorkspaceSnapshot,
) -> PreliminaryJourneyState | None:
    if not preliminary_ui_enabled() or frozen_evaluation_workspace_selected():
        return None
    pin = approved_review_pin(snapshot)
    if pin is None:
        return None
    return preliminary_services().journeys.find_journey_for_approved_review(pin)


def current_journey_history(
    snapshot: WorkspaceSnapshot,
) -> PreliminaryJourneyHistory | None:
    state = current_journey_state(snapshot)
    if state is None:
        return None
    return preliminary_services().journeys.get_history(state.journey.journey_id)


def preliminary_destination_title(snapshot: WorkspaceSnapshot) -> str | None:
    """Return the customer-facing destination for a materialized route."""

    state = current_journey_state(snapshot)
    if state is None or state.current_route is PreliminaryCurrentRoute.UNSELECTED:
        return None
    if state.current_route is PreliminaryCurrentRoute.EXPLORE_PROCESS:
        return "Preliminary Assessment"
    return "Organisational Assessment"


def journey_materialized(snapshot: WorkspaceSnapshot) -> bool:
    if not preliminary_ui_enabled() or frozen_evaluation_workspace_selected():
        return False
    pin = approved_review_pin(snapshot)
    if pin is None:
        return False
    return preliminary_services().journeys.journey_exists_for_approved_review_artifact(
        assessment_id=pin.assessment_id,
        approved_review_artifact_id=pin.artifact_id,
    )


def action_token(key: str) -> str:
    tokens = st.session_state.setdefault(_ACTION_TOKENS_KEY, {})
    return tokens.setdefault(key, f"ui-{uuid4().hex}")


def clear_action_token(key: str) -> None:
    tokens = st.session_state.get(_ACTION_TOKENS_KEY, {})
    tokens.pop(key, None)


def materialize_route_intent(
    snapshot: WorkspaceSnapshot,
) -> PreliminaryJourneyState:
    intent = route_intent(snapshot)
    pin = approved_review_pin(snapshot)
    if intent is None or pin is None:
        raise ValueError("An approved process and current route choice are required")
    services = preliminary_services()
    created = services.journeys.create_or_reuse_journey(pin)
    state = services.journeys.get_state(created.journey.journey_id)
    key = f"materialize:{created.journey.journey_id}:{intent.route.value}"
    services.journeys.select_route(
        created.journey.journey_id,
        intent.route,
        request_token=action_token(key),
        expected_latest_sequence=state.latest_event_sequence,
    )
    clear_action_token(key)
    st.session_state.pop("preliminary_setup_incomplete", None)
    return services.journeys.get_state(created.journey.journey_id)


def continue_first_time_route(
    snapshot: WorkspaceSnapshot,
) -> PreliminaryJourneyState:
    """Materialize the selected route and perform its one-time first action.

    The route choice and process approval together are the user's authorization
    for this initial action. Existing runs and formal lifecycles are never
    repeated: this helper only advances a genuinely not-started route.
    """

    state = materialize_route_intent(snapshot)
    route_event = state.current_route_event
    if route_event is None:
        raise ValueError("The selected route has no persisted route-choice event")

    services = preliminary_services()
    journey_id = state.journey.journey_id
    if (
        state.current_route is PreliminaryCurrentRoute.EXPLORE_PROCESS
        and state.preliminary_status is PreliminaryJourneyStatus.NOT_STARTED
    ):
        key = f"first-time-run:{journey_id}:{route_event.event_id}"
        services.runs.evaluate_and_persist(
            journey_id,
            request_token=action_token(key),
            route_choice_event_id=route_event.event_id,
            route_choice_event_sequence=route_event.event_sequence,
        )
        clear_action_token(key)
    elif (
        state.current_route
        is PreliminaryCurrentRoute.ORGANISATIONAL_ASSESSMENT
        and state.formal_lifecycle_status is FormalLifecycleStatus.NOT_STARTED
    ):
        key = f"first-time-formal:{journey_id}:{route_event.event_id}"
        services.formal.start_formal_lifecycle(
            journey_id,
            request_token=action_token(key),
            route_choice_event_id=route_event.event_id,
            route_choice_event_sequence=route_event.event_sequence,
        )
        clear_action_token(key)

    return services.journeys.get_state(journey_id)
