"""Explicit Phase 4 human-review and approval screen."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st

from ai_adoption_engine.models.enums import KnowledgeState
from ai_adoption_engine.models.review import (
    ConflictStatus,
    ProcessReviewSession,
    ReviewedAssertion,
    ReviewedCollection,
)
from ai_adoption_engine.presentation.components.evidence import render_reviewed_assertion
from ai_adoption_engine.presentation.components.process_flow import render_current_state
from ai_adoption_engine.presentation.components.status import guard
from ai_adoption_engine.presentation.context import (
    hydrate_workspace,
    refresh_workspace,
    workspace_service,
)


AssertionResolver = Callable[[ProcessReviewSession], ReviewedAssertion]
CollectionResolver = Callable[[ProcessReviewSession], ReviewedCollection]


def _step(session: ProcessReviewSession, step_id: str):
    return next(item for item in session.steps if item.candidate_step_id == step_id)


def _apply(session: ProcessReviewSession, operation: Callable[[ProcessReviewSession], None]) -> None:
    working = session.model_copy(deep=True)
    try:
        operation(working)
        workspace_service().save_review(
            st.session_state.selected_assessment_id, working
        )
    except Exception as exc:
        refresh_workspace()
        st.error(str(exc))
        return
    refresh_workspace()
    st.rerun()


def _value_input(assertion: ReviewedAssertion, key: str, value_kind: type) -> Any:
    if value_kind is bool:
        current = assertion.value if isinstance(assertion.value, bool) else True
        return st.selectbox(
            "Corrected/resolved value",
            [True, False],
            index=0 if current else 1,
            key=f"value-{key}",
        )
    if value_kind is int:
        return int(
            st.number_input(
                "Corrected/resolved value (0–5)",
                min_value=0,
                max_value=5,
                value=assertion.value if isinstance(assertion.value, int) else 0,
                step=1,
                key=f"value-{key}",
            )
        )
    return st.text_input(
        "Corrected/resolved value",
        value=str(assertion.value or ""),
        key=f"value-{key}",
    )


def _assertion_editor(
    session: ProcessReviewSession,
    *,
    label: str,
    field_path: str,
    resolver: AssertionResolver,
    value_kind: type = str,
) -> None:
    assertion = resolver(session)
    with st.container(border=True):
        render_reviewed_assertion(assertion, label=label)
        actions = (
            ["Resolve Unknown", "Retain Unknown"]
            if assertion.knowledge_state is KnowledgeState.UNKNOWN
            else ["Accept", "Correct", "Reject"]
        )
        with st.form(f"review-{field_path}"):
            action = st.selectbox("Review action", actions, key=f"action-{field_path}")
            corrected = _value_input(assertion, field_path, value_kind)
            rationale = st.text_input(
                "Reviewer rationale",
                placeholder="Required for corrections, rejections and resolved unknowns",
                key=f"rationale-{field_path}",
            )
            submitted = st.form_submit_button("Apply review action")
        if submitted:
            if action in {"Correct", "Reject", "Resolve Unknown"} and not rationale.strip():
                st.error("Provide a rationale for this action.")
                return

            def mutate(working: ProcessReviewSession) -> None:
                target = resolver(working)
                service = workspace_service().review_service
                if action == "Accept":
                    service.accept_assertion(working, target, field_path, rationale=rationale or None)
                elif action == "Correct":
                    service.correct_assertion(
                        working, target, field_path, corrected, rationale=rationale
                    )
                elif action == "Reject":
                    service.reject_assertion(
                        working, target, field_path, rationale=rationale
                    )
                elif action == "Resolve Unknown":
                    service.resolve_unknown(
                        working, target, field_path, corrected, rationale=rationale
                    )
                else:
                    service.retain_unknown(
                        working, target, field_path, rationale=rationale or None
                    )

            _apply(session, mutate)


def _collection_editor(
    session: ProcessReviewSession,
    *,
    label: str,
    field_path: str,
    resolver: CollectionResolver,
) -> None:
    collection = resolver(session)
    st.markdown(f"**{label}**")
    st.caption(
        f"Extraction completeness: {collection.completeness.value}. {collection.rationale}"
    )
    if not collection.items:
        st.caption("No reviewed values currently retained.")
    for index, _ in enumerate(collection.items):
        _assertion_editor(
            session,
            label=f"{label} item {index + 1}",
            field_path=f"{field_path}.items[{index}]",
            resolver=lambda working, i=index: resolver(working).items[i],
        )
    with st.form(f"add-{field_path}"):
        value = st.text_input("Add human-supplied value", key=f"add-value-{field_path}")
        rationale = st.text_input("Rationale", key=f"add-rationale-{field_path}")
        add = st.form_submit_button("Add value")
    if add:
        if not value.strip() or not rationale.strip():
            st.error("A value and rationale are required.")
        else:
            _apply(
                session,
                lambda working: workspace_service().review_service.add_human_collection_item(
                    working,
                    resolver(working),
                    field_path,
                    value,
                    rationale=rationale,
                ),
            )


def _render_step(session: ProcessReviewSession, step_id: str) -> None:
    step = _step(session, step_id)
    if not step.retained:
        st.caption("Rejected step retained in the audit record.")
        return
    top = st.columns([6, 1, 1])
    top[0].markdown(f"### {step.sequence}. {step.activity.value or 'Unknown activity'}")
    retained_ids = [item.candidate_step_id for item in session.steps if item.retained]
    position = retained_ids.index(step_id)
    if top[1].button("↑", key=f"up-{step_id}", disabled=position == 0):
        reordered = list(retained_ids)
        reordered[position - 1], reordered[position] = reordered[position], reordered[position - 1]
        _apply(
            session,
            lambda working: workspace_service().review_service.reorder_steps(
                working, reordered, rationale="Reviewer moved the step earlier."
            ),
        )
    if top[2].button("↓", key=f"down-{step_id}", disabled=position == len(retained_ids) - 1):
        reordered = list(retained_ids)
        reordered[position + 1], reordered[position] = reordered[position], reordered[position + 1]
        _apply(
            session,
            lambda working: workspace_service().review_service.reorder_steps(
                working, reordered, rationale="Reviewer moved the step later."
            ),
        )

    _assertion_editor(
        session,
        label="Activity",
        field_path=f"steps.{step_id}.activity",
        resolver=lambda working: _step(working, step_id).activity,
    )
    _assertion_editor(
        session,
        label="Description",
        field_path=f"steps.{step_id}.description",
        resolver=lambda working: _step(working, step_id).description,
    )

    for attribute, label in (
        ("actors", "Actors"),
        ("responsible_roles", "Responsible roles"),
        ("systems", "Systems and tools"),
        ("inputs", "Inputs"),
        ("outputs", "Outputs"),
        ("exceptions", "Exceptions"),
        ("operational_characteristics", "Operational facts"),
    ):
        with st.expander(label):
            _collection_editor(
                session,
                label=label,
                field_path=f"steps.{step_id}.{attribute}",
                resolver=lambda working, name=attribute: getattr(_step(working, step_id), name),
            )

    with st.expander("Decisions and branches"):
        if not step.decisions:
            st.caption("No candidate decisions were extracted.")
        for index, decision in enumerate(step.decisions):
            _assertion_editor(
                session,
                label=f"Decision {index + 1} condition",
                field_path=f"steps.{step_id}.decisions[{index}].condition",
                resolver=lambda working, i=index: _step(working, step_id).decisions[i].condition,
            )
            _collection_editor(
                session,
                label="Branches",
                field_path=f"steps.{step_id}.decisions[{index}].branches",
                resolver=lambda working, i=index: _step(working, step_id).decisions[i].branches,
            )

    with st.expander("Dependencies"):
        if not step.dependencies:
            st.caption("No candidate dependencies were extracted.")
        for index, dependency in enumerate(step.dependencies):
            st.write(
                f"{dependency.relationship.value or 'Relationship unknown'}: "
                f"{dependency.target_label.value or 'Target unknown'}"
            )
            targets = [item.candidate_step_id for item in session.steps if item.retained and item.candidate_step_id != step_id]
            selected = st.selectbox(
                "Resolved target step",
                [None, *targets],
                index=([None, *targets].index(dependency.target_candidate_step_id) if dependency.target_candidate_step_id in targets else 0),
                key=f"dependency-target-{step_id}-{index}",
            )
            rationale = st.text_input(
                "Dependency rationale", key=f"dependency-rationale-{step_id}-{index}"
            )
            left, right = st.columns(2)
            if left.button("Resolve dependency", key=f"resolve-dependency-{step_id}-{index}"):
                if not rationale.strip():
                    st.error("Provide a dependency rationale.")
                else:
                    _apply(
                        session,
                        lambda working, i=index: workspace_service().review_service.correct_dependency(
                            working, step_id, i, selected, rationale=rationale
                        ),
                    )
            if right.button("Reject dependency", key=f"reject-dependency-{step_id}-{index}"):
                if not rationale.strip():
                    st.error("Provide a dependency rationale.")
                else:
                    _apply(
                        session,
                        lambda working, i=index: workspace_service().review_service.reject_dependency(
                            working, step_id, i, rationale=rationale
                        ),
                    )

    with st.expander("Assessment characteristics"):
        for index, characteristic in enumerate(step.criteria):
            _assertion_editor(
                session,
                label=characteristic.name.value.replace("_", " ").title(),
                field_path=f"steps.{step_id}.criteria[{index}]",
                resolver=lambda working, i=index: _step(working, step_id).criteria[i].assertion,
                value_kind=int,
            )
        _assertion_editor(
            session,
            label="Human accountability required",
            field_path=f"steps.{step_id}.human_accountability_required",
            resolver=lambda working: _step(working, step_id).human_accountability_required,
            value_kind=bool,
        )

    with st.expander("Capability signals"):
        for index, signal in enumerate(step.capability_signals):
            _assertion_editor(
                session,
                label=signal.name.replace("_", " ").title(),
                field_path=f"steps.{step_id}.capability_signals[{index}]",
                resolver=lambda working, i=index: _step(working, step_id).capability_signals[i].assertion,
                value_kind=bool,
            )

    retained_actors = [item.value for item in step.actors.items if item.retained and item.value]
    if retained_actors:
        selected_actor = st.selectbox(
            "Optional primary actor for the Phase 1 projection",
            [None, *retained_actors],
            index=([None, *retained_actors].index(step.primary_actor) if step.primary_actor in retained_actors else 0),
            key=f"primary-actor-{step_id}",
        )
        if st.button("Save primary actor", key=f"save-primary-actor-{step_id}"):
            _apply(
                session,
                lambda working: workspace_service().review_service.select_primary_actor(
                    working, step_id, selected_actor
                ),
            )
    with st.expander("Reject this process step"):
        reason = st.text_input("Removal rationale", key=f"remove-rationale-{step_id}")
        if st.button("Reject/remove step", key=f"remove-step-{step_id}"):
            if not reason.strip():
                st.error("Provide a rationale.")
            else:
                _apply(
                    session,
                    lambda working: workspace_service().review_service.remove_step(
                        working, step_id, rationale=reason
                    ),
                )


def _render_approved(approved) -> None:
    st.success("Current-state process explicitly approved.")
    st.caption(
        f"Review {approved.review.review_id} · Approved {approved.approval.approved_at.isoformat()}"
    )
    render_current_state(approved.business_process)
    with st.expander("Review provenance and audit"):
        st.write(f"Review events: {len(approved.review.events)}")
        for event in approved.review.events:
            st.caption(f"{event.sequence}. {event.action.value} — {event.field_path}")
    with st.expander("Reopen for editing"):
        confirmed = st.checkbox(
            "I understand this will make the active approval, assessment and decision package non-current. Historical milestone revisions will be retained."
        )
        if st.button("Reset active workspace to review", disabled=not confirmed):
            workspace_service().reset_to_review(st.session_state.selected_assessment_id)
            refresh_workspace()
            st.rerun()


def render() -> None:
    snapshot = hydrate_workspace()
    if snapshot is None:
        guard("Create or open an assessment first.")
    st.title("Process Review")
    approved = st.session_state.get("approved_review")
    if approved is not None:
        _render_approved(approved)
        return
    candidate = st.session_state.get("candidate_extraction_result")
    if candidate is None or candidate.candidate is None:
        guard("Complete candidate extraction before starting human review.")
    st.warning("CANDIDATE / UNCONFIRMED PROCESS EXTRACTION")
    session = st.session_state.get("review_session")
    if session is None:
        if st.button("Start human review", type="primary"):
            workspace_service().start_review(snapshot.assessment.assessment_id)
            refresh_workspace()
            st.rerun()
        return

    st.write(
        "Confirm what the document says, distinguish inference and human input, retain legitimate unknowns, and resolve structural blockers."
    )
    _assertion_editor(
        session,
        label="Process name",
        field_path="process.name",
        resolver=lambda working: working.process_name,
    )
    _assertion_editor(
        session,
        label="Process description",
        field_path="process.description",
        resolver=lambda working: working.process_description,
    )
    _assertion_editor(
        session,
        label="Process objective",
        field_path="process.objective",
        resolver=lambda working: working.process_objective,
    )

    st.header("Ordered activities")
    for item in sorted(session.steps, key=lambda value: value.sequence):
        with st.expander(
            f"{item.sequence}. {item.activity.value or 'Unknown activity'}",
            expanded=item.sequence == 1,
        ):
            _render_step(session, item.candidate_step_id)

    with st.container(border=True):
        st.subheader("Step order")
        st.write(" → ".join(
            str(item.activity.value) for item in sorted(session.steps, key=lambda value: value.sequence) if item.retained
        ))
        if session.order_accepted:
            st.success("Step order accepted.")
        elif st.button("Accept current step order", type="primary"):
            _apply(
                session,
                lambda working: workspace_service().review_service.accept_step_order(
                    working, rationale="Reviewer confirmed the displayed current-state order."
                ),
            )

    with st.container(border=True):
        st.subheader("Blocking conflicts")
        open_blocking = [
            item for item in session.conflicts if item.blocking and item.status is ConflictStatus.OPEN
        ]
        if not open_blocking:
            st.success("No unresolved blocking structural conflicts.")
        for conflict in session.conflicts:
            st.warning(f"{conflict.code}: {conflict.message} ({conflict.status.value})")
            if conflict.status is ConflictStatus.OPEN:
                resolution = st.text_input(
                    "Resolution", key=f"conflict-resolution-{conflict.conflict_id}"
                )
                if st.button("Resolve conflict", key=f"resolve-conflict-{conflict.conflict_id}"):
                    if not resolution.strip():
                        st.error("Describe how the conflict was resolved.")
                    else:
                        _apply(
                            session,
                            lambda working, conflict_id=conflict.conflict_id: workspace_service().review_service.resolve_conflict(
                                working, conflict_id, resolution=resolution
                            ),
                        )

    with st.container(border=True):
        st.subheader("Explicit approval")
        st.write(
            "Approval confirms that this is an acceptable human-reviewed representation of the current-state process. "
            "Unknown AI-assessment information may remain unknown."
        )
        with st.form("approve-current-state"):
            confirmed = st.checkbox("APPROVE CURRENT-STATE PROCESS")
            rationale = st.text_input("Optional approval rationale")
            submitted = st.form_submit_button(
                "Approve current-state process", type="primary", disabled=not confirmed
            )
        if submitted:
            result = workspace_service().approve(
                snapshot.assessment.assessment_id, rationale=rationale or None
            )
            if result.approved is None:
                for error in result.errors:
                    st.error(
                        error.message + (f" ({error.field_path})" if error.field_path else "")
                    )
            else:
                refresh_workspace()
                st.rerun()

