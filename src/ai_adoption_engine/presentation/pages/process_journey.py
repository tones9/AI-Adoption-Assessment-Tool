"""Opt-in Preliminary Assessment journey and result presentation."""

from __future__ import annotations

import streamlit as st

from ai_adoption_engine.models.preliminary_assessment import AssessmentJourney
from ai_adoption_engine.models.preliminary_journey import (
    FormalLifecycleStatus,
    PreliminaryCurrentRoute,
    PreliminaryJourneyHistory,
    PreliminaryJourneyStatus,
)
from ai_adoption_engine.models.preliminary_persistence import (
    PreliminaryResultReferenceUse,
    PreliminaryRunProjectedStatus,
)
from ai_adoption_engine.models.preliminary_presentation import (
    PreliminaryResultPresentation,
    PresentationEvidenceSections,
)
from ai_adoption_engine.presentation.components.page_header import render_page_header
from ai_adoption_engine.presentation.components.status import guard
from ai_adoption_engine.presentation.context import (
    frozen_evaluation_workspace_selected,
    hydrate_workspace,
    switch_to_registered_page,
)
from ai_adoption_engine.presentation.preliminary_ui import (
    action_token,
    clear_action_token,
    current_journey_history,
    materialize_route_intent,
    preliminary_services,
    preliminary_ui_enabled,
    render_route_choice,
    route_intent,
)
from ai_adoption_engine.presentation.preliminary_result import (
    PreliminaryPresentationError,
    present_preliminary_result,
)
from ai_adoption_engine.presentation.supporting_evidence_ui import (
    supporting_evidence_ui_enabled,
)
from ai_adoption_engine.presentation.supporting_evidence_workflow import (
    render_supporting_evidence_workflow,
)


_WARNING = (
    "**Provisional exploration only.** This Preliminary Assessment is not an "
    "organisational decision, formal outcome, gate result, Decision Package, or "
    "approval to implement. It does not satisfy formal evidence requirements."
)


def _go(page: str, fallback: str) -> None:
    if not switch_to_registered_page(page):
        st.info(fallback)


def _confidence(value) -> str:
    return f"{value.level.value} evidence coverage"


def _v0_2_selected() -> bool:
    return (
        preliminary_services().journeys.supported_identity.output_schema_version
        == "preliminary-assessment.v0.2"
    )


def _render_dimensions(history: PreliminaryJourneyHistory) -> None:
    state = history.state
    route = {
        PreliminaryCurrentRoute.UNSELECTED: "No route selected",
        PreliminaryCurrentRoute.EXPLORE_PROCESS: "Explore this process",
        PreliminaryCurrentRoute.ORGANISATIONAL_ASSESSMENT: (
            "Run an organisational assessment"
        ),
    }[state.current_route]
    preliminary = state.preliminary_status.value.replace("_", " ").title()
    formal = (
        "Awaiting formal inputs"
        if state.formal_lifecycle_status
        is FormalLifecycleStatus.AWAITING_FORMAL_INPUTS
        else "Not started"
    )
    columns = st.columns(3)
    columns[0].metric("Current route", route)
    columns[1].metric("Preliminary status", preliminary)
    columns[2].metric("Formal lifecycle", formal)


def _render_v0_1_result(result) -> None:
    assessment = result.assessment
    st.subheader("Preliminary result")
    st.markdown(f"### {_confidence(assessment.confidence)}")
    st.caption(
        "Confidence describes evidence coverage, not probability, safety, or implementation readiness."
    )
    st.subheader("Likely directions by activity")
    for activity in assessment.activity_results:
        with st.container(border=True):
            st.markdown(f"### {activity.activity}")
            st.write(f"**{activity.provisional_direction.value}**")
            st.caption(_confidence(activity.confidence))
            st.markdown("**Why this direction**")
            st.write(activity.rationale)
            st.markdown("**Documented facts**")
            if activity.documented_facts:
                for fact in activity.documented_facts:
                    st.write(f"- {fact.statement}")
                    st.caption(fact.source_locator)
                    with st.expander(f"Source excerpt · {fact.fact_id}"):
                        st.code(fact.exact_excerpt, language=None, wrap_lines=True)
            else:
                st.caption("No documented facts were admissible for this activity.")
            st.markdown("**Reasonable inferences**")
            if activity.reasonable_inferences:
                for inference in activity.reasonable_inferences:
                    st.write(f"- {inference.statement}")
                    st.caption(
                        f"{_confidence(inference.confidence)} · derived from "
                        + ", ".join(inference.derived_from_fact_ids)
                    )
                    st.caption(inference.rationale)
            else:
                st.caption("No reviewed reasonable inferences were used.")
            st.markdown("**Unknowns**")
            if activity.unknowns:
                st.caption(
                    "Unknown means not established; it does not mean zero, false, low, or not applicable."
                )
                for unknown in activity.unknowns:
                    st.write(f"- {unknown.unresolved_question}")
                    if unknown.evidence_needed:
                        st.caption(f"Evidence needed: {unknown.evidence_needed}")
                    if unknown.owner_needed:
                        st.caption(f"Owner needed: {unknown.owner_needed}")
            else:
                st.caption("No material unknowns remain for this provisional direction.")
            st.markdown("**Next evidence to collect**")
            if activity.next_evidence_to_collect:
                for request in activity.next_evidence_to_collect:
                    st.write(f"- {request.description}")
                    if request.suggested_owner:
                        st.caption(f"Suggested owner: {request.suggested_owner}")
            else:
                st.caption("No additional evidence request was generated for this activity.")
            with st.expander("Technical rule and decision-input trace"):
                st.caption(f"Deciding rule: {activity.deciding_rule_code.value}")
                for item in activity.decision_input_trace:
                    value = (
                        "unknown"
                        if item.normalized_value is None
                        else str(item.normalized_value)
                    )
                    st.caption(
                        f"{item.input_name.value}: {value} · "
                        f"{item.classification.value} · material={item.material}"
                    )
                    if item.comparison:
                        st.code(
                            item.comparison.model_dump_json(),
                            language="json",
                        )
    st.caption("No single process-wide direction has been generated.")
    with st.expander("Evaluator, rules, fingerprint and lineage"):
        st.caption(f"Run ID: {result.preliminary_run_id}")
        st.caption(f"Result ID: {result.preliminary_result_id}")
        st.caption(
            f"Evaluator: {result.evaluator.evaluator_id} / "
            f"{result.evaluator.evaluator_version}"
        )
        st.caption(
            f"Rule set: {result.rule_set.rule_set_id} / "
            f"{result.rule_set.rule_set_version}"
        )
        st.code(result.rule_set.rule_set_fingerprint, language=None)
        st.caption(f"Output schema: {result.output_schema_version}")
        st.caption(
            f"Approved review artifact: {result.source.approved_review_artifact_id}"
        )


def _render_source_excerpts(items) -> None:
    for item in items:
        st.write(f"- {item.statement}")
        explanation = getattr(item, "explanation", None)
        if explanation:
            st.caption(explanation)
        for index, excerpt in enumerate(item.source_excerpts, start=1):
            with st.expander(f"Source excerpt {index}"):
                st.caption(excerpt.source_locator)
                st.code(excerpt.exact_excerpt, language=None, wrap_lines=True)


def _render_evidence_sections(sections: PresentationEvidenceSections) -> None:
    st.markdown("**Documented evidence**")
    if sections.documented_source:
        _render_source_excerpts(sections.documented_source)
    else:
        st.caption("No documented evidence is shown for this section.")

    st.markdown("**Reviewed inferences**")
    if sections.reviewed_inference:
        _render_source_excerpts(sections.reviewed_inference)
    else:
        st.caption("No reviewed inference is shown for this section.")

    st.markdown("**Rule-derived inferences**")
    if sections.engine_inference:
        _render_source_excerpts(sections.engine_inference)
    else:
        st.caption("No rule-derived inference is shown for this section.")

    st.markdown("**Unknowns**")
    if sections.unknown:
        _render_source_excerpts(sections.unknown)
    else:
        st.caption("No material unknown is shown for this section.")

    st.markdown("**Conflicts**")
    if sections.conflict:
        _render_source_excerpts(sections.conflict)
    else:
        st.caption("No material conflict is shown for this section.")

    st.markdown("**Next evidence to collect**")
    if sections.next_evidence:
        for item in sections.next_evidence:
            st.write(f"- {item}")
    else:
        st.caption("No additional evidence request is shown for this section.")


def _render_v0_2_result(presentation: PreliminaryResultPresentation) -> None:
    customer = presentation.customer
    st.subheader(customer.title)
    st.warning(customer.provisional_warning)
    st.markdown(f"### {customer.overall_evidence_coverage}")
    st.caption(customer.evidence_coverage_explanation)
    st.caption(customer.overall_direction_statement)

    for activity in customer.activities:
        with st.container(border=True):
            st.markdown(f"### {activity.heading}")
            st.write(f"**{activity.state}**")
            if activity.provisional_direction:
                st.write(f"**{activity.provisional_direction}**")
            st.caption(activity.evidence_coverage)
            st.write(activity.explanation)

            for opportunity in activity.opportunities:
                st.markdown(f"#### {opportunity.heading}")
                st.write(f"**{opportunity.provisional_direction}**")
                st.caption(opportunity.evidence_coverage)
                st.markdown("**Why this direction**")
                st.write(opportunity.explanation)
                _render_evidence_sections(opportunity.evidence)

            for discovery in activity.discovery_needs:
                st.markdown(f"#### {discovery.heading}")
                st.write("**More evidence is needed**")
                st.caption(discovery.evidence_coverage)
                st.write(discovery.explanation)
                _render_evidence_sections(discovery.evidence)

            st.markdown("#### Activity evidence")
            _render_evidence_sections(activity.evidence)

    audit = presentation.audit
    if audit is None:
        return
    with st.expander("Technical and audit details", expanded=False):
        identity = audit.source_identity
        st.caption(f"Result ID: {identity.preliminary_result_id}")
        st.caption(f"Run ID: {identity.preliminary_run_id}")
        st.caption(f"Journey ID: {identity.journey_id}")
        st.caption(
            f"Evaluator: {identity.evaluator_id} / {identity.evaluator_version}"
        )
        st.caption(
            f"Rule set: {identity.rule_set_id} / {identity.rule_set_version}"
        )
        st.code(identity.rule_set_fingerprint, language=None)
        st.caption(f"Output schema: {identity.output_schema_version}")
        st.caption(f"Source document: {identity.source_document_id}")
        st.caption(
            f"Approved review artifact: {identity.approved_review_artifact_id}"
        )
        for entry in audit.entries:
            st.markdown(f"**{entry.entry_type} · {entry.identifier}**")
            if entry.codes:
                st.caption("Codes: " + ", ".join(entry.codes))
            if entry.referenced_identifiers:
                st.caption(
                    "References: " + ", ".join(entry.referenced_identifiers)
                )
            for trace in entry.decision_trace_json:
                st.code(trace, language="json")


def _render_result(result) -> None:
    try:
        presentation = present_preliminary_result(result, include_audit=True)
    except PreliminaryPresentationError:
        st.error(
            "This Preliminary Assessment result could not be displayed safely. "
            "No partial result has been presented."
        )
        return
    audit = presentation.audit
    if audit is None:
        st.error(
            "This Preliminary Assessment result could not be displayed safely. "
            "No partial result has been presented."
        )
        return
    if audit.source_identity.output_schema_version == "preliminary-assessment.v0.1":
        _render_v0_1_result(result)
        return
    if audit.source_identity.output_schema_version == "preliminary-assessment.v0.2":
        _render_v0_2_result(presentation)
        return
    st.error(
        "This Preliminary Assessment result could not be displayed safely. "
        "No partial result has been presented."
    )


def _render_history(history: PreliminaryJourneyHistory) -> None:
    show_key = f"preliminary-history-{history.state.journey.journey_id}"
    if st.button("View assessment history", key=f"open-{show_key}"):
        st.session_state[show_key] = True
    with st.expander(
        "Preliminary Assessment history",
        expanded=bool(st.session_state.get(show_key)),
    ):
        if not history.runs:
            st.caption("No Preliminary Assessment runs yet.")
            return
        v0_2_selected = _v0_2_selected()
        for item in history.runs:
            terminal = item.lifecycle_events[-1]
            label = item.status.value.title()
            if item.superseded_by_result_id:
                label += " · Superseded"
            st.markdown(f"**{label}**")
            if not v0_2_selected:
                st.caption(
                    f"Run {item.manifest.preliminary_run_id} · "
                    f"{terminal.occurred_at.isoformat()}"
                )
                if item.manifest.retry_of_run_id:
                    st.caption(f"Retry of: {item.manifest.retry_of_run_id}")
                if item.result:
                    st.caption(f"Result: {item.result.preliminary_result_id}")
                if item.terminal_code:
                    st.caption(f"Technical status code: {item.terminal_code}")
            else:
                st.caption(terminal.occurred_at.isoformat())
                st.caption("Immutable Preliminary Assessment history item")
                with st.expander("Historical technical details", expanded=False):
                    st.caption(f"Run ID: {item.manifest.preliminary_run_id}")
                    st.caption(
                        f"Output schema: {item.manifest.output_schema_version}"
                    )
                    if item.manifest.retry_of_run_id:
                        st.caption(f"Retry of: {item.manifest.retry_of_run_id}")
                    if item.result:
                        st.caption(f"Result ID: {item.result.preliminary_result_id}")
                    if item.terminal_code:
                        st.caption(f"Technical status code: {item.terminal_code}")
            st.divider()


def _run(history: PreliminaryJourneyHistory, *, retry_run_id: str | None = None) -> None:
    state = history.state
    route_event = state.current_route_event
    if route_event is None:
        st.error("Choose Explore this process before running the assessment.")
        return
    key = (
        f"retry:{state.journey.journey_id}:{retry_run_id}"
        if retry_run_id
        else f"run:{state.journey.journey_id}:{route_event.event_id}"
    )
    try:
        with st.spinner("Running the deterministic Preliminary Assessment…"):
            if retry_run_id:
                preliminary_services().runs.retry_and_persist(
                    state.journey.journey_id,
                    retry_run_id,
                    request_token=action_token(key),
                    route_choice_event_id=route_event.event_id,
                    route_choice_event_sequence=route_event.event_sequence,
                )
            else:
                preliminary_services().runs.evaluate_and_persist(
                    state.journey.journey_id,
                    request_token=action_token(key),
                    route_choice_event_id=route_event.event_id,
                    route_choice_event_sequence=route_event.event_sequence,
                )
    except Exception:
        st.error(
            "The Preliminary Assessment could not complete safely. No partial result has been presented."
        )
        return
    clear_action_token(key)
    st.rerun()


def _change_route(history: PreliminaryJourneyHistory) -> None:
    state = history.state
    target = (
        AssessmentJourney.ORGANISATIONAL_ASSESSMENT
        if state.current_route is PreliminaryCurrentRoute.EXPLORE_PROCESS
        else AssessmentJourney.EXPLORE_PROCESS
    )
    target_label = (
        "Run an organisational assessment"
        if target is AssessmentJourney.ORGANISATIONAL_ASSESSMENT
        else "Explore this process"
    )
    with st.expander("Change route"):
        st.write(
            "Switching routes preserves every Preliminary run, result, recovery record, and formal lifecycle."
        )
        confirmed = st.checkbox(
            f"I understand that switching to {target_label} does not cancel or convert prior work",
            key=f"confirm-route-{state.journey.journey_id}-{target.value}",
        )
        if st.button(
            target_label,
            key=f"change-route-{target.value}",
            disabled=not confirmed,
        ):
            key = f"route:{state.journey.journey_id}:{target.value}"
            try:
                preliminary_services().journeys.select_route(
                    state.journey.journey_id,
                    target,
                    request_token=action_token(key),
                    expected_latest_sequence=state.latest_event_sequence,
                )
            except Exception:
                st.error(
                    "The journey changed in another window. Refresh and review the latest route before trying again."
                )
                return
            clear_action_token(key)
            st.rerun()


def _render_explore(history: PreliminaryJourneyHistory) -> None:
    state = history.state
    st.warning(_WARNING)
    if state.formal_lifecycle_status is FormalLifecycleStatus.AWAITING_FORMAL_INPUTS:
        st.info(
            "Organisational assessment setup retained — Awaiting formal inputs. Switching to Explore did not cancel it."
        )
    if state.active_preliminary_result is not None:
        _render_result(state.active_preliminary_result)

    if state.preliminary_status is PreliminaryJourneyStatus.NOT_STARTED:
        st.subheader("Run a Preliminary Assessment")
        st.write(
            "Use the approved current-state process to get provisional activity-level directions and identify missing evidence."
        )
        if st.button("Run Preliminary Assessment", type="primary"):
            _run(history)
    elif state.preliminary_status is PreliminaryJourneyStatus.RUNNING:
        st.subheader("Preliminary Assessment running")
        st.write(
            "A run is recorded as in progress. It may still be running in another window. Never mark it interrupted unless you know it stopped."
        )
        running = next(
            item
            for item in history.runs
            if item.status is PreliminaryRunProjectedStatus.STARTED
        )
        if _v0_2_selected():
            with st.expander("Technical run details", expanded=False):
                st.caption(f"Run ID: {running.manifest.preliminary_run_id}")
        else:
            st.caption(f"Run: {running.manifest.preliminary_run_id}")
        confirmed = st.checkbox(
            "I know this run is no longer executing",
            key=f"confirm-abandon-{running.manifest.preliminary_run_id}",
        )
        if st.button(
            "Mark run as interrupted",
            disabled=not confirmed,
            key=f"abandon-{running.manifest.preliminary_run_id}",
        ):
            key = f"abandon:{running.manifest.preliminary_run_id}"
            try:
                preliminary_services().runs.abandon_interrupted_run(
                    state.journey.journey_id,
                    running.manifest.preliminary_run_id,
                    recovery_request_token=action_token(key),
                )
            except Exception:
                st.error("The run could not be marked interrupted safely.")
                return
            clear_action_token(key)
            st.rerun()
    elif state.preliminary_status is PreliminaryJourneyStatus.AVAILABLE:
        confirmed = st.checkbox(
            "I understand that a new run creates a new immutable result",
            key=f"confirm-rerun-{state.journey.journey_id}",
        )
        if st.button(
            "Run a new Preliminary Assessment",
            disabled=not confirmed,
        ):
            _run(history)
    elif state.preliminary_status is PreliminaryJourneyStatus.RETRY_AVAILABLE:
        st.error(
            "The latest Preliminary Assessment failed or was interrupted. No partial result was saved."
        )
        predecessor = next(
            item
            for item in history.runs
            if item.status
            in {
                PreliminaryRunProjectedStatus.FAILED,
                PreliminaryRunProjectedStatus.ABANDONED,
            }
        )
        if st.button("Retry Preliminary Assessment", type="primary"):
            _run(history, retry_run_id=predecessor.manifest.preliminary_run_id)
    elif state.preliminary_status is PreliminaryJourneyStatus.RERUN_REQUIRED:
        st.warning(
            "Historical results were produced with a different source, evaluator, rule set, fingerprint, or output identity. They are not current."
        )
        if st.button("Run Preliminary Assessment", type="primary"):
            _run(history)


def _render_organisational(history: PreliminaryJourneyHistory) -> None:
    state = history.state
    if state.formal_lifecycle_status is FormalLifecycleStatus.AWAITING_FORMAL_INPUTS:
        st.subheader("Awaiting formal inputs")
        if supporting_evidence_ui_enabled() and state.formal_lifecycle is not None:
            render_supporting_evidence_workflow(
                state.formal_lifecycle.formal_lifecycle_id
            )
            return
        st.write(
            "The organisational assessment setup is saved. Supporting evidence, evidence review, formal conversion, and formal assessment are not available in this release."
        )
        st.info(
            "No formal evidence requirements have been satisfied and no outcome, approval, or Decision Package has been created."
        )
        return
    st.subheader("Start organisational assessment setup")
    st.write(
        "This creates only a separate lifecycle awaiting additional organisational evidence. It does not run a formal assessment."
    )
    context_only = st.checkbox(
        "Reference the latest Preliminary Assessment as context only — not formal evidence",
        value=False,
        disabled=state.latest_compatible_result is None,
    )
    confirmed = st.checkbox(
        "I understand this does not satisfy evidence requirements or approve implementation",
        key=f"confirm-formal-{state.journey.journey_id}",
    )
    if st.button(
        "Start organisational assessment setup",
        type="primary",
        disabled=not confirmed,
    ):
        event = state.current_route_event
        if event is None:
            st.error("Select the organisational route before starting setup.")
            return
        key = f"formal:{state.journey.journey_id}:{event.event_id}"
        result = state.latest_compatible_result if context_only else None
        try:
            preliminary_services().formal.start_formal_lifecycle(
                state.journey.journey_id,
                request_token=action_token(key),
                route_choice_event_id=event.event_id,
                route_choice_event_sequence=event.event_sequence,
                preliminary_result_id=(
                    result.preliminary_result_id if result is not None else None
                ),
                preliminary_result_use=(
                    PreliminaryResultReferenceUse.CONTEXT_ONLY_NOT_FORMAL_EVIDENCE
                    if result is not None
                    else None
                ),
            )
        except Exception:
            st.error(
                "The organisational assessment setup could not be created safely. No formal assessment was run."
            )
            return
        clear_action_token(key)
        st.rerun()


def render() -> None:
    if not preliminary_ui_enabled():
        render_page_header("Process journey")
        st.info("Process journey is not enabled for this application session.")
        return
    if frozen_evaluation_workspace_selected():
        render_page_header("Process journey")
        st.info(
            "Preliminary journey actions are unavailable for this frozen evaluation record."
        )
        return
    snapshot = hydrate_workspace()
    if snapshot is None:
        render_page_header("Process journey")
        guard("Create or open an assessment first.")
    candidate = st.session_state.get("candidate_extraction_result")
    if candidate is None or candidate.candidate is None:
        render_page_header("Process journey")
        st.subheader("A current-state process is required")
        st.write(
            "Upload and extract one current-state process document before choosing a journey."
        )
        if st.button("Open Source & Extraction", type="primary"):
            _go("source", "Open Source & Extraction from the sidebar.")
        return
    approved = st.session_state.get("approved_review")
    if approved is None:
        render_page_header("Process journey")
        if route_intent(snapshot) is None:
            st.subheader("Choose what happens after validation")
            render_route_choice(snapshot, key_prefix="journey-prerequisite-route")
            if st.button("Open route choice", type="primary"):
                _go("source", "Open Source & Extraction from the sidebar.")
        else:
            st.subheader("Process validation in progress")
            st.write(
                "Complete the current-state process review and explicit approval before the journey can be persisted."
            )
            if st.button("Continue process validation", type="primary"):
                _go("review", "Open Validate process from the sidebar.")
        return
    try:
        history = current_journey_history(snapshot)
    except Exception:
        st.error(
            "Preliminary journey history is unsupported or corrupt and could not "
            "be safely validated. No data was changed and no result has been treated as current."
        )
        return
    if history is None:
        render_page_header("Process journey")
        st.success("Current-state process approved")
        st.warning("Journey setup incomplete")
        st.write(
            "Your process approval remains valid. You do not need to review or approve the process again."
        )
        if route_intent(snapshot) is None:
            render_route_choice(snapshot, key_prefix="journey-approved-route")
        if route_intent(snapshot) is not None and st.button(
            "Continue journey setup", type="primary"
        ):
            try:
                materialize_route_intent(snapshot)
            except Exception:
                st.error(
                    "Journey setup could not complete safely. The process approval remains valid."
                )
                return
            st.rerun()
        return

    _render_dimensions(history)
    if history.state.current_route is PreliminaryCurrentRoute.UNSELECTED:
        st.warning("Choose a route before continuing.")
        render_route_choice(snapshot, key_prefix="journey-unselected-route")
        if route_intent(snapshot) is not None and st.button(
            "Continue journey setup", type="primary", key="journey-select-route"
        ):
            try:
                materialize_route_intent(snapshot)
            except Exception:
                st.error("The route could not be saved safely. Refresh and try again.")
                return
            st.rerun()
        return
    _change_route(history)
    if history.state.current_route is PreliminaryCurrentRoute.EXPLORE_PROCESS:
        render_page_header("Explore this process")
        _render_explore(history)
    else:
        render_page_header("Organisational assessment")
        _render_organisational(history)
    _render_history(history)
