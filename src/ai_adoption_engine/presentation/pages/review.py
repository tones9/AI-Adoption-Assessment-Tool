"""Explicit Phase 4 human-review and approval screen."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import re
from typing import Any

import streamlit as st

from ai_adoption_engine.models.candidate_process import ResolvedEvidenceReference
from ai_adoption_engine.models.enums import KnowledgeState
from ai_adoption_engine.models.review import (
    ConflictStatus,
    InformationOrigin,
    ProcessReviewSession,
    ReviewDisposition,
    ReviewedAssertion,
    ReviewedCollection,
)
from ai_adoption_engine.presentation.components.evidence import render_reviewed_assertion
from ai_adoption_engine.presentation.components.process_flow import render_current_state
from ai_adoption_engine.presentation.components.status import guard
from ai_adoption_engine.presentation.context import (
    frozen_evaluation_workspace_selected,
    hydrate_workspace,
    phase4_review_writes_available,
    refresh_workspace,
    switch_to_registered_page,
    workspace_service,
)
from ai_adoption_engine.presentation.review_journey import (
    ReviewJourneyView,
    build_review_journey,
)
from ai_adoption_engine.presentation.review_progress import (
    ReviewProgress,
    build_review_progress,
    inferred_unreviewed,
    iter_process_assertions,
    iter_step_assertions,
    unknown_unreviewed_by_step,
)
from ai_adoption_engine.presentation.components.page_header import (
    render_page_header,
)
from ai_adoption_engine.presentation.components.primitives import (
    render_badge,
    render_business_list,
    render_stat_strip,
)
from ai_adoption_engine.presentation.preliminary_ui import (
    continue_first_time_route,
    current_journey_state,
    preliminary_ui_enabled,
    render_route_choice,
    route_intent,
)
from ai_adoption_engine.models.preliminary_journey import PreliminaryCurrentRoute


AssertionResolver = Callable[[ProcessReviewSession], ReviewedAssertion]
CollectionResolver = Callable[[ProcessReviewSession], ReviewedCollection]


def _step(session: ProcessReviewSession, step_id: str):
    return next(item for item in session.steps if item.candidate_step_id == step_id)


def _apply(
    session: ProcessReviewSession,
    operation: Callable[[ProcessReviewSession], None],
    *,
    success_message: str,
    clear_editor_field: str | None = None,
) -> None:
    working = session.model_copy(deep=True)
    try:
        operation(working)
        workspace_service().save_review(
            st.session_state.selected_assessment_id, working
        )
    except Exception:
        refresh_workspace()
        st.error(
            "This change was not saved. Provide the required value, rationale, and—when you cite the document—an existing source reference."
        )
        return
    if clear_editor_field is not None:
        modes = dict(st.session_state.get("review_editor_modes", {}))
        modes.pop(clear_editor_field, None)
        st.session_state.review_editor_modes = modes
        drafts = dict(st.session_state.get("review_editor_drafts", {}))
        drafts.pop(clear_editor_field, None)
        st.session_state.review_editor_drafts = drafts
    st.session_state.review_feedback = success_message
    st.session_state.pop("guided_review_selected_item", None)
    st.session_state.pop("review_focus_path", None)
    refresh_workspace()
    st.rerun()


_UNSET = object()


def _value_input(
    assertion: ReviewedAssertion,
    key: str,
    value_kind: type,
    *,
    initial_value: Any = _UNSET,
) -> Any:
    starting_value = assertion.value if initial_value is _UNSET else initial_value
    if value_kind is bool:
        current = starting_value if isinstance(starting_value, bool) else True
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
                value=starting_value if isinstance(starting_value, int) else 0,
                step=1,
                key=f"value-{key}",
            )
        )
    return st.text_input(
        "Corrected/resolved value",
        value=str(starting_value or ""),
        key=f"value-{key}",
    )


_DOCUMENT_SUPPORTED_CHOICE = "Document supported — cite source evidence"
_HUMAN_SUPPLIED_CHOICE = "Human supplied — no document evidence"
def _step_evidence_choices(step) -> tuple[ResolvedEvidenceReference, ...]:
    """Resolved Phase 2 evidence already present anywhere on a reviewed step.

    A reviewer may cite only evidence the extraction already resolved against this
    document, which guarantees the reference is genuine and belongs to the reviewed
    source. Read-only; nothing is created or mutated here.
    """

    references: dict[str, ResolvedEvidenceReference] = {}

    def collect(items) -> None:
        for reference in items:
            references.setdefault(reference.evidence_id, reference)

    for assertion in (step.document_order, step.activity, step.description):
        collect(assertion.evidence)
    for name in (
        "actors",
        "responsible_roles",
        "systems",
        "inputs",
        "outputs",
        "exceptions",
        "operational_characteristics",
    ):
        collection = getattr(step, name)
        collect(collection.evidence)
        for item in collection.items:
            collect(item.evidence)
    for decision in step.decisions:
        collect(decision.condition.evidence)
        collect(decision.branches.evidence)
        for item in decision.branches.items:
            collect(item.evidence)
    for dependency in step.dependencies:
        collect(dependency.target_label.evidence)
        collect(dependency.relationship.evidence)
    return tuple(references.values())


def _evidence_option_label(reference: ResolvedEvidenceReference) -> str:
    snippet = reference.exact_snippet.strip().replace("\n", " ")
    if len(snippet) > 80:
        snippet = f"{snippet[:77]}…"
    return f"{reference.source_locator} — {snippet}"


def _assertion_editor(
    session: ProcessReviewSession,
    *,
    label: str,
    field_path: str,
    resolver: AssertionResolver,
    value_kind: type = str,
    evidence_choices: Sequence[ResolvedEvidenceReference] = (),
    reject_removes_step_id: str | None = None,
) -> None:
    assertion = resolver(session)
    is_unknown = assertion.knowledge_state.value == KnowledgeState.UNKNOWN.value
    disposition = assertion.disposition.value
    is_unreviewed = disposition == ReviewDisposition.UNREVIEWED.value
    modes = dict(st.session_state.get("review_editor_modes", {}))
    editor_mode = modes.get(field_path)
    drafts = dict(st.session_state.get("review_editor_drafts", {}))
    field_draft = dict(drafts.get(field_path, {}))
    state_key = f"{field_path}-{session.updated_at.isoformat()}"

    def remember(**values: Any) -> None:
        updated_drafts = dict(st.session_state.get("review_editor_drafts", {}))
        updated_field = dict(updated_drafts.get(field_path, {}))
        updated_field.update(values)
        updated_drafts[field_path] = updated_field
        st.session_state.review_editor_drafts = updated_drafts

    def open_editor(mode: str) -> None:
        updated = dict(st.session_state.get("review_editor_modes", {}))
        updated[field_path] = mode
        st.session_state.review_editor_modes = updated
        st.rerun()

    def close_editor() -> None:
        updated = dict(st.session_state.get("review_editor_modes", {}))
        updated.pop(field_path, None)
        st.session_state.review_editor_modes = updated
        updated_drafts = dict(st.session_state.get("review_editor_drafts", {}))
        updated_drafts.pop(field_path, None)
        st.session_state.review_editor_drafts = updated_drafts
        st.rerun()

    with st.container(border=True, key=f"review-field-{field_path}"):
        render_reviewed_assertion(assertion, label=label)
        if is_unknown and disposition == ReviewDisposition.UNKNOWN_RETAINED.value:
            st.info("Recorded as not provided. It remains unknown unless you add reliable information.")
        elif disposition == ReviewDisposition.REJECTED.value:
            st.info("This item is excluded from the reviewed process. Its review history is retained.")
        elif not is_unreviewed:
            st.success("This item has been reviewed. You can correct it without losing its audit history.")

        if editor_mode is None:
            if is_unknown:
                add, retain = st.columns(2)
                if add.button(
                    "Add information",
                    key=f"edit-{state_key}",
                    type="primary" if is_unreviewed else "secondary",
                ):
                    open_editor("add")
                if is_unreviewed and retain.button(
                    "Leave as not provided",
                    key=f"retain-{state_key}",
                ):
                    _apply(
                        session,
                        lambda working: workspace_service().review_service.retain_unknown(
                            working, resolver(working), field_path
                        ),
                        success_message=f"{label} remains explicitly not provided.",
                        clear_editor_field=field_path,
                    )
                return

            if is_unreviewed:
                confirm, correct, exclude = st.columns([2, 1, 1])
                if confirm.button(
                    "Confirm and continue",
                    type="primary",
                    key=f"confirm-{state_key}",
                ):
                    _apply(
                        session,
                        lambda working: workspace_service().review_service.accept_assertion(
                            working, resolver(working), field_path
                        ),
                        success_message=f"{label} confirmed.",
                        clear_editor_field=field_path,
                    )
            else:
                correct, exclude = st.columns(2)
            if correct.button("Correct this", key=f"edit-{state_key}"):
                open_editor("correct")
            exclude_label = (
                "Remove this step"
                if reject_removes_step_id is not None
                else "Exclude this information"
            )
            if exclude.button(exclude_label, key=f"exclude-{state_key}"):
                open_editor("exclude")
            return

        if editor_mode in {"correct", "add"}:
            st.markdown(
                "**Correct this information**"
                if editor_mode == "correct"
                else "**Add reliable information**"
            )
            corrected = _value_input(
                assertion,
                state_key,
                value_kind,
                initial_value=field_draft.get("value", assertion.value),
            )
            remember(value=corrected)
            chosen_origin = InformationOrigin.HUMAN_SUPPLIED
            cited: list[ResolvedEvidenceReference] = []
            if evidence_choices:
                by_label = {
                    _evidence_option_label(reference): reference
                    for reference in evidence_choices
                }
                origin_choice = st.selectbox(
                    "Where does this value come from?",
                    [_HUMAN_SUPPLIED_CHOICE, _DOCUMENT_SUPPORTED_CHOICE],
                    index=(
                        1
                        if field_draft.get("origin") == _DOCUMENT_SUPPORTED_CHOICE
                        else 0
                    ),
                    key=f"origin-{state_key}",
                    help=(
                        "Choose document supported only when the selected source excerpt "
                        "directly supports this value."
                    ),
                )
                remember(origin=origin_choice)
                if origin_choice == _DOCUMENT_SUPPORTED_CHOICE:
                    chosen_origin = InformationOrigin.DOCUMENT_SUPPORTED
                    selected_evidence = st.multiselect(
                        "Supporting source evidence (required)",
                        list(by_label),
                        default=[
                            selected
                            for selected in field_draft.get("evidence", [])
                            if selected in by_label
                        ],
                        key=f"evidence-{state_key}",
                    )
                    remember(evidence=selected_evidence)
                    cited = [by_label[selected] for selected in selected_evidence]
            rationale = st.text_input(
                "Why is this change needed?",
                placeholder="Briefly explain the correction or added information",
                value=field_draft.get("rationale", ""),
                key=f"rationale-{state_key}",
            )
            remember(rationale=rationale)
            save, cancel = st.columns(2)
            save_label = (
                "Save correction and continue"
                if editor_mode == "correct"
                else "Save information and continue"
            )
            if save.button(save_label, type="primary", key=f"apply-{state_key}"):
                if not rationale.strip():
                    st.error("Briefly explain why this change is needed.")
                    return
                if (
                    chosen_origin.value == InformationOrigin.DOCUMENT_SUPPORTED.value
                    and not cited
                ):
                    st.error("Select the source evidence that directly supports this value.")
                    return

                def mutate(working: ProcessReviewSession) -> None:
                    target = resolver(working)
                    service = workspace_service().review_service
                    if editor_mode == "add":
                        service.resolve_unknown(
                            working,
                            target,
                            field_path,
                            corrected,
                            rationale=rationale,
                            origin=chosen_origin,
                            evidence=list(cited),
                        )
                    else:
                        service.correct_assertion(
                            working,
                            target,
                            field_path,
                            corrected,
                            rationale=rationale,
                            origin=chosen_origin,
                            evidence=list(cited),
                        )

                _apply(
                    session,
                    mutate,
                    success_message=(
                        f"{label} added."
                        if editor_mode == "add"
                        else f"{label} corrected."
                    ),
                    clear_editor_field=field_path,
                )
            if cancel.button("Cancel", key=f"cancel-{state_key}"):
                close_editor()
            return

        st.markdown(
            "**Remove this process step**"
            if reject_removes_step_id is not None
            else "**Exclude this information**"
        )
        rationale = st.text_input(
            "Why should this be removed?",
            value=field_draft.get("rationale", ""),
            key=f"rationale-{state_key}",
        )
        remember(rationale=rationale)
        remove, cancel = st.columns(2)
        remove_label = (
            "Remove step and continue"
            if reject_removes_step_id is not None
            else "Exclude and continue"
        )
        if remove.button(remove_label, type="primary", key=f"apply-{state_key}"):
            if not rationale.strip():
                st.error("Briefly explain why this should be removed.")
                return

            def reject(working: ProcessReviewSession) -> None:
                if reject_removes_step_id is not None:
                    workspace_service().review_service.remove_step(
                        working,
                        reject_removes_step_id,
                        rationale=rationale,
                    )
                else:
                    workspace_service().review_service.reject_assertion(
                        working,
                        resolver(working),
                        field_path,
                        rationale=rationale,
                    )

            _apply(
                session,
                reject,
                success_message=(
                    f"{label} removed; review and confirm the updated step order."
                    if reject_removes_step_id is not None
                    else f"{label} excluded."
                ),
                clear_editor_field=field_path,
            )
        if cancel.button("Cancel", key=f"cancel-{state_key}"):
            close_editor()


def _collection_progress(collection: ReviewedCollection) -> str:
    if not collection.items:
        return "no extracted values · optional"
    reviewed = sum(
        item.disposition.value != ReviewDisposition.UNREVIEWED.value
        for item in collection.items
    )
    return f"{reviewed}/{len(collection.items)} reviewed"


def _step_status(step, progress: ReviewProgress) -> tuple[str, str]:
    if not step.retained:
        return "Removed", "muted"
    remaining = sum(
        item.step_id == step.candidate_step_id for item in progress.outstanding
    )
    if remaining:
        if step.activity.disposition.value == ReviewDisposition.UNREVIEWED.value:
            return "Not reviewed", "muted"
        return (
            f"{remaining} required item{'s' if remaining != 1 else ''} remaining",
            "muted",
        )
    return "Complete", "primary"


def _open_outstanding(item) -> None:
    st.session_state["guided_review_selected_item"] = item.item_id
    if item.step_id is not None:
        st.session_state["selected-review-step"] = item.step_id
    st.session_state["review_focus_path"] = item.field_path
    st.rerun()


def _render_review_progress(progress: ReviewProgress) -> None:
    render_stat_strip(
        [
            ("Outstanding", progress.remaining_required),
            ("Complete", progress.completed_required),
            ("Remaining", progress.remaining_required),
        ]
    )
    st.caption(
        "This progress follows the Phase 4 approval rules. Optional descriptive fields, "
        "non-blocking unknowns and incomplete AI-assessment evidence do not reduce it."
    )
    if progress.is_ready:
        st.success("Ready for explicit approval.")
        return
    noun = "item" if progress.remaining_required == 1 else "items"
    verb = "needs" if progress.remaining_required == 1 else "need"
    st.warning(
        f"{progress.remaining_required} required {noun} {verb} attention before approval."
    )
    for item in progress.outstanding:
        with st.container(border=True):
            st.markdown(f"**{item.location_label} → {item.field_label}**")
            st.write(item.reason)
            if item.step_id is not None:
                if st.button("Open step", key=f"open-outstanding-{item.item_id}"):
                    _open_outstanding(item)
            elif st.button(
                "Show requirement", key=f"open-outstanding-{item.item_id}"
            ):
                _open_outstanding(item)


def _render_non_blocking_attention(session: ProcessReviewSession) -> None:
    inferred = inferred_unreviewed(session)
    unknown_by_step = unknown_unreviewed_by_step(session)
    unknown_total = sum(unknown_by_step.values())
    with st.expander(
        f"Non-blocking review attention — {len(inferred)} inferred, {unknown_total} unknown"
    ):
        if inferred:
            st.warning(
                f"{len(inferred)} model-inferred item"
                f"{'s' if len(inferred) != 1 else ''} remain identifiable and are recommended for review."
            )
            for item in inferred:
                st.write(f"- {item.activity or 'Process'} → {item.label}: {item.assertion.value}")
                if item.step_id and st.button(
                    "Open inferred item", key=f"open-inferred-{item.field_path}"
                ):
                    st.session_state["selected-review-step"] = item.step_id
                    st.session_state["review_focus_path"] = item.field_path
                    st.session_state["review_feedback"] = (
                        f"Opened model-inferred item: {item.label}."
                    )
                    st.rerun()
        else:
            st.success("No unreviewed model-inferred items.")
        st.caption(
            f"{unknown_total} values remain unknown. They do not block process validation; "
            "resolve them only when legitimate information is available. Otherwise they remain explicitly unknown."
        )
        for step in session.steps:
            count = unknown_by_step.get(step.candidate_step_id, 0)
            if count:
                st.write(
                    f"- Step {step.sequence} — {step.activity.value or 'Unknown activity'}: "
                    f"{count} unknown value{'s' if count != 1 else ''}"
                )


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
        st.caption(
            "No values were extracted. This collection is optional; add a human-supplied value only when you have legitimate information."
        )
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
                success_message=f"Human-supplied {label.lower()} value added.",
            )


def _render_step(
    session: ProcessReviewSession,
    step_id: str,
    progress: ReviewProgress,
    *,
    include_required_controls: bool = True,
) -> None:
    step = _step(session, step_id)
    if not step.retained:
        st.caption("Rejected step retained in the audit record.")
        return
    if include_required_controls:
        focus_path = st.session_state.get("review_focus_path")
        if focus_path and focus_path.startswith(f"steps.{step_id}."):
            st.warning(
                "Opened from Review progress. The outstanding or recommended field is shown in this activity editor."
            )

        _assertion_editor(
            session,
            label="Activity",
            field_path=f"steps.{step_id}.activity",
            resolver=lambda working: _step(working, step_id).activity,
            reject_removes_step_id=step_id,
        )
    _assertion_editor(
        session,
        label="Description (optional)",
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
        collection = getattr(step, attribute)
        with st.expander(f"{label} — {_collection_progress(collection)}"):
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
            _assertion_editor(
                session,
                label=f"Dependency {index + 1} target",
                field_path=f"steps.{step_id}.dependencies[{index}].target_label",
                resolver=lambda working, i=index: _step(working, step_id).dependencies[
                    i
                ].target_label,
            )
            _assertion_editor(
                session,
                label=f"Dependency {index + 1} relationship",
                field_path=f"steps.{step_id}.dependencies[{index}].relationship",
                resolver=lambda working, i=index: _step(working, step_id).dependencies[
                    i
                ].relationship,
            )
            st.write(
                f"{dependency.relationship.value or 'Relationship unknown'}: "
                f"{dependency.target_label.value or 'Target unknown'}"
            )
            target_steps = [
                item
                for item in session.steps
                if item.retained and item.candidate_step_id != step_id
            ]
            targets = [item.candidate_step_id for item in target_steps]
            labels = {
                item.candidate_step_id: f"Step {item.sequence}: {item.activity.value or 'Unknown activity'}"
                for item in target_steps
            }
            if dependency.retained and dependency.target_candidate_step_id in targets:
                st.success(
                    "Current target: " + labels[dependency.target_candidate_step_id]
                )
            elif dependency.retained:
                st.warning("This retained dependency needs a valid target or must be rejected.")
            else:
                st.caption("Dependency rejected and retained only in the audit record.")
            selected = st.selectbox(
                "Resolved target step",
                [None, *targets],
                index=([None, *targets].index(dependency.target_candidate_step_id) if dependency.target_candidate_step_id in targets else 0),
                key=f"dependency-target-{step_id}-{index}",
                format_func=lambda value: "Choose a step" if value is None else labels[value],
            )
            rationale = st.text_input(
                "Dependency rationale", key=f"dependency-rationale-{step_id}-{index}"
            )
            left, right = st.columns(2)
            if left.button(
                "Save dependency target",
                key=f"resolve-dependency-{step_id}-{index}",
                disabled=(
                    selected is None
                    or (
                        dependency.retained
                        and selected == dependency.target_candidate_step_id
                    )
                ),
                help=(
                    "Choose a different valid target to save a correction."
                    if selected is None or selected == dependency.target_candidate_step_id
                    else None
                ),
            ):
                if not rationale.strip():
                    st.error("Provide a dependency rationale.")
                else:
                    _apply(
                        session,
                        lambda working, i=index: workspace_service().review_service.correct_dependency(
                            working, step_id, i, selected, rationale=rationale
                        ),
                        success_message="Dependency target saved.",
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
                        success_message="Dependency rejected.",
                    )

    with st.expander("Assessment characteristics"):
        # Criteria and accountability are gate-material: the decision policy requires an
        # evidence reference before it will read them, so the reviewer must be able to
        # cite one. Capability signals are deliberately excluded from this affordance;
        # they are not evidence-gated on the current decision path.
        criterion_evidence = _step_evidence_choices(step)
        for index, characteristic in enumerate(step.criteria):
            _assertion_editor(
                session,
                label=characteristic.name.value.replace("_", " ").title(),
                field_path=f"steps.{step_id}.criteria[{index}]",
                resolver=lambda working, i=index: _step(working, step_id).criteria[i].assertion,
                value_kind=int,
                evidence_choices=criterion_evidence,
            )
        _assertion_editor(
            session,
            label="Human accountability required",
            field_path=f"steps.{step_id}.human_accountability_required",
            resolver=lambda working: _step(working, step_id).human_accountability_required,
            value_kind=bool,
            evidence_choices=criterion_evidence,
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
        if st.button(
            "Save primary actor",
            key=f"save-primary-actor-{step_id}",
            disabled=selected_actor == step.primary_actor,
            help=(
                "Choose a different actor to save."
                if selected_actor == step.primary_actor
                else None
            ),
        ):
            _apply(
                session,
                lambda working: workspace_service().review_service.select_primary_actor(
                    working, step_id, selected_actor
                ),
                success_message="Optional primary actor saved.",
            )
    if include_required_controls:
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
                        success_message="Process step removed. Review and re-accept the updated order.",
                    )


def _display_required_items(journey: ReviewJourneyView):
    """Arrange the authoritative queue for a natural human review sequence."""

    def priority(item) -> tuple[int, int, str]:
        if item.field_path == "process.name":
            return (0, 0, item.item_id)
        if item.field_path == "process.steps.order":
            return (3, 0, item.item_id)
        if item.step_sequence is not None:
            dependency_rank = 1 if item.field_label == "Activity" else 2
            return (1, item.step_sequence * 10 + dependency_rank, item.item_id)
        return (2, 0, item.item_id)

    return tuple(sorted(journey.required_items, key=priority))


@dataclass(frozen=True)
class _RequiredCheck:
    item_id: str
    label: str
    field_path: str | None
    step_id: str | None
    field_label: str
    completed: bool
    outstanding: Any | None = None


def _required_checks(
    session: ProcessReviewSession,
    journey: ReviewJourneyView,
) -> tuple[_RequiredCheck, ...]:
    """Show the whole required path while deriving completion from preflight."""

    remaining = list(_display_required_items(journey))
    checks: list[_RequiredCheck] = []

    def add_base(
        *,
        label: str,
        field_path: str,
        field_label: str,
        step_id: str | None = None,
    ) -> None:
        outstanding = next(
            (
                item
                for item in remaining
                if item.field_path == field_path and item.field_label == field_label
            ),
            None,
        )
        if outstanding is not None:
            remaining.remove(outstanding)
        checks.append(
            _RequiredCheck(
                item_id=(
                    outstanding.item_id
                    if outstanding is not None
                    else f"complete:{field_path}"
                ),
                label=label,
                field_path=field_path,
                step_id=step_id,
                field_label=field_label,
                completed=outstanding is None,
                outstanding=outstanding,
            )
        )

    add_base(
        label="Process name",
        field_path="process.name",
        field_label="Process name",
    )
    for step in sorted(session.steps, key=lambda value: value.sequence):
        if not step.retained:
            continue
        add_base(
            label=f"Step {step.sequence}: {step.activity.value or 'Unnamed step'}",
            field_path=f"steps.{step.candidate_step_id}.activity",
            field_label="Activity",
            step_id=step.candidate_step_id,
        )
    add_base(
        label="Step order",
        field_path="process.steps.order",
        field_label="Step order",
    )
    checks.extend(
        _RequiredCheck(
            item_id=item.item_id,
            label=_required_item_label(item),
            field_path=item.field_path,
            step_id=item.step_id,
            field_label=item.field_label,
            completed=False,
            outstanding=item,
        )
        for item in remaining
    )
    return tuple(checks)


def _sync_guided_focus(
    session: ProcessReviewSession,
    journey: ReviewJourneyView,
) -> None:
    """Keep the UI bookmark aligned to persisted approval preflight state."""

    checks = _required_checks(session, journey)
    check_ids = {item.item_id for item in checks}
    selected = st.session_state.get("guided_review_selected_item")
    if selected not in check_ids:
        selected = next(
            (item.item_id for item in checks if not item.completed),
            checks[0].item_id if checks else None,
        )
    ready_redirect_key = f"review-ready-redirected-{session.review_id}"
    if journey.progress.is_ready and not st.session_state.get(ready_redirect_key):
        st.session_state[ready_redirect_key] = True
        st.session_state.pop("guided_review_selected_item", None)
        st.session_state.pop("review_focus_path", None)
        st.session_state["review-workspace-mode"] = "Final approval"
        return
    if not journey.progress.is_ready:
        st.session_state.pop(ready_redirect_key, None)
    if selected is None:
        return
    st.session_state["guided_review_selected_item"] = selected
    item = next(candidate for candidate in checks if candidate.item_id == selected)
    if item.step_id is not None:
        st.session_state["selected-review-step"] = item.step_id
    if item.field_path is not None:
        st.session_state["review_focus_path"] = item.field_path


def _required_item_label(item) -> str:
    if item.field_path == "process.name":
        return "Process name"
    if item.field_path == "process.steps.order":
        return "Step order"
    if item.step_sequence is not None:
        suffix = "" if item.field_label == "Activity" else f" · {item.field_label}"
        return f"Step {item.step_sequence}: {item.activity or 'Unnamed step'}{suffix}"
    if item.field_label == "Structural conflict":
        occurrence = re.search(r":(\d+)$", item.item_id)
        return (
            f"Structure issue {int(occurrence.group(1)) + 1}"
            if occurrence
            else "Structure issue"
        )
    return item.field_label


def _render_workspace_progress(journey: ReviewJourneyView) -> None:
    progress = journey.progress
    completed = progress.completed_required
    total = progress.total_required
    left = progress.remaining_required
    with st.container(key="review-workspace-progress"):
        heading, count = st.columns([5, 2], vertical_alignment="bottom")
        heading.markdown(f"### {completed} of {total} required checks complete")
        count.markdown(f"**{left} left**" if left else "**Ready to approve**")
        st.progress(progress.completion_ratio)
        st.caption(
            "Only the checks required to validate this process are counted here. Optional details can stay unanswered."
        )


def _render_requirement_buttons(
    session: ProcessReviewSession,
    journey: ReviewJourneyView,
) -> None:
    checks = _required_checks(session, journey)
    st.markdown("### Required review")
    if journey.progress.is_ready:
        st.success("Every required check is complete. Completed checks remain available below.")
    else:
        st.caption(
            "Confirm each required item. After you save, the next unfinished check opens automatically."
        )
    selected = st.session_state.get("guided_review_selected_item")
    with st.container(key="review-requirement-buttons"):
        for item in checks:
            if item.completed:
                label = f"✓ {item.label} — Confirmed"
            elif item.item_id == selected:
                label = f"● {item.label} — Current"
            else:
                label = f"○ {item.label} — Needs review"
            if st.button(
                label,
                key=f"open-outstanding-{item.item_id}",
                type=(
                    "primary"
                    if item.item_id == selected and not item.completed
                    else "secondary"
                ),
                width="stretch",
            ):
                st.session_state["guided_review_selected_item"] = item.item_id
                if item.step_id is not None:
                    st.session_state["selected-review-step"] = item.step_id
                if item.field_path is not None:
                    st.session_state["review_focus_path"] = item.field_path
                st.rerun()


def _render_step_order_editor(session: ProcessReviewSession) -> None:
    retained = [
        item
        for item in sorted(session.steps, key=lambda value: value.sequence)
        if item.retained
    ]
    st.markdown("### Confirm the step order")
    st.write("Check that the activities are shown in the order the work happens.")
    retained_ids = [step.candidate_step_id for step in retained]
    for position, step in enumerate(retained):
        row = st.columns([1, 5, 2, 2], vertical_alignment="center")
        row[0].markdown(f"**{step.sequence}**")
        row[1].write(step.activity.value or "Unnamed activity")
        if row[2].button(
            "Move earlier",
            key=f"order-up-{step.candidate_step_id}",
            disabled=position == 0,
        ):
            reordered = list(retained_ids)
            reordered[position - 1], reordered[position] = (
                reordered[position],
                reordered[position - 1],
            )
            _apply(
                session,
                lambda working: workspace_service().review_service.reorder_steps(
                    working,
                    reordered,
                    rationale="Reviewer moved the step earlier.",
                ),
                success_message="Step order updated. Confirm the complete order when it is correct.",
            )
        if row[3].button(
            "Move later",
            key=f"order-down-{step.candidate_step_id}",
            disabled=position == len(retained) - 1,
        ):
            reordered = list(retained_ids)
            reordered[position + 1], reordered[position] = (
                reordered[position],
                reordered[position + 1],
            )
            _apply(
                session,
                lambda working: workspace_service().review_service.reorder_steps(
                    working,
                    reordered,
                    rationale="Reviewer moved the step later.",
                ),
                success_message="Step order updated. Confirm the complete order when it is correct.",
            )
    if session.order_accepted:
        st.success("Step order confirmed.")
    elif st.button(
        "Confirm step order and continue",
        type="primary",
        key="accept-current-step-order",
    ):
        _apply(
            session,
            lambda working: workspace_service().review_service.accept_step_order(
                working,
                rationale="Reviewer confirmed the displayed current-state order.",
            ),
            success_message="Step order saved.",
        )
    st.caption("Moving a step makes the order unconfirmed until you confirm it again.")


def _render_dependency_editor(session: ProcessReviewSession, item) -> None:
    match = re.search(r"\.dependencies\[(\d+)\]", item.field_path or "")
    if item.step_id is None or match is None:
        st.error("This dependency could not be opened. Its persisted review record is unchanged.")
        return
    index = int(match.group(1))
    step = _step(session, item.step_id)
    dependency = step.dependencies[index]
    st.markdown(f"### Check the dependency for Step {step.sequence}")
    st.write(
        f"**{step.activity.value or 'Unnamed activity'}** currently depends on "
        f"**{dependency.target_label.value or 'an unspecified step'}**."
    )
    st.write("Choose the correct earlier/later process step, or remove this dependency.")
    target_steps = [
        candidate
        for candidate in session.steps
        if candidate.retained and candidate.candidate_step_id != item.step_id
    ]
    targets = [candidate.candidate_step_id for candidate in target_steps]
    labels = {
        candidate.candidate_step_id: (
            f"Step {candidate.sequence}: {candidate.activity.value or 'Unnamed activity'}"
        )
        for candidate in target_steps
    }
    selected = st.selectbox(
        "Which step should it depend on?",
        [None, *targets],
        index=(
            [None, *targets].index(dependency.target_candidate_step_id)
            if dependency.target_candidate_step_id in targets
            else 0
        ),
        key=f"dependency-target-{item.step_id}-{index}",
        format_func=lambda value: "Choose a step" if value is None else labels[value],
    )
    rationale = st.text_input(
        "Why are you making this change?",
        key=f"dependency-rationale-{item.step_id}-{index}",
    )
    save, remove = st.columns(2)
    if save.button(
        "Save dependency",
        type="primary",
        key=f"resolve-dependency-{item.step_id}-{index}",
        disabled=selected is None,
    ):
        if not rationale.strip():
            st.error("Briefly explain why this dependency is correct.")
        else:
            _apply(
                session,
                lambda working: workspace_service().review_service.correct_dependency(
                    working, item.step_id, index, selected, rationale=rationale
                ),
                success_message="Dependency saved.",
            )
    if remove.button(
        "Remove dependency",
        key=f"reject-dependency-{item.step_id}-{index}",
    ):
        if not rationale.strip():
            st.error("Briefly explain why this dependency should be removed.")
        else:
            _apply(
                session,
                lambda working: workspace_service().review_service.reject_dependency(
                    working, item.step_id, index, rationale=rationale
                ),
                success_message="Dependency removed.",
            )


def _render_conflict_editor(session: ProcessReviewSession, item) -> None:
    open_conflicts = [
        conflict
        for conflict in session.conflicts
        if conflict.blocking and conflict.status.value == ConflictStatus.OPEN.value
    ]
    occurrence = re.search(r":(\d+)$", item.item_id)
    index = int(occurrence.group(1)) if occurrence else 0
    conflict = open_conflicts[index] if index < len(open_conflicts) else None
    if conflict is None:
        st.success("This structural issue is already resolved.")
        return
    st.markdown("### Resolve a process structure issue")
    st.write(conflict.message)
    resolution = st.text_input(
        "How was this resolved?", key=f"conflict-resolution-{conflict.conflict_id}"
    )
    if st.button("Save resolution", type="primary", key=f"resolve-conflict-{conflict.conflict_id}"):
        if not resolution.strip():
            st.error("Describe how the issue was resolved.")
        else:
            _apply(
                session,
                lambda working: workspace_service().review_service.resolve_conflict(
                    working, conflict.conflict_id, resolution=resolution
                ),
                success_message="Structure issue resolved.",
            )


def _render_selected_requirement(
    session: ProcessReviewSession,
    journey: ReviewJourneyView,
) -> None:
    checks = _required_checks(session, journey)
    if not checks:
        return
    selected_id = st.session_state.get("guided_review_selected_item")
    item = next(
        (candidate for candidate in checks if candidate.item_id == selected_id),
        None,
    )
    if item is None:
        item = next((candidate for candidate in checks if not candidate.completed), None)
    if item is None:
        st.info("Select a completed check above to review or edit it.")
        return
    with st.container(border=True, key="review-selected-workspace"):
        st.caption("CURRENT CHECK")
        if item.field_path == "process.name":
            st.markdown("### Check the process name")
            st.write("Is this the correct name for the process described in the document?")
            _assertion_editor(
                session,
                label="Process name",
                field_path="process.name",
                resolver=lambda working: working.process_name,
            )
        elif item.field_path == "process.steps.order":
            _render_step_order_editor(session)
        elif item.field_label == "Dependency":
            _render_dependency_editor(session, item.outstanding)
        elif item.field_label == "Structural conflict":
            _render_conflict_editor(session, item.outstanding)
        elif item.step_id is not None:
            step = _step(session, item.step_id)
            st.markdown(f"### Check Step {step.sequence}")
            st.write("Is this a real activity in the process?")
            _assertion_editor(
                session,
                label="Activity",
                field_path=f"steps.{item.step_id}.activity",
                resolver=lambda working: _step(working, item.step_id).activity,
                reject_removes_step_id=item.step_id,
            )
        else:
            st.markdown(f"### {item.field_label}")
            st.warning(item.reason)


def _render_review_summary(journey: ReviewJourneyView) -> None:
    st.subheader("Review summary")
    with st.container(border=True):
        st.warning("CANDIDATE PROCESS — NEEDS VALIDATION")
        st.markdown(
            f"**Originally extracted:** {journey.candidate_process_name or 'Unknown process name'}"
        )
        st.write(
            "Activities: "
            + (" → ".join(journey.candidate_activities) or "No activities extracted")
        )
        if journey.extraction_issue_messages:
            st.caption("Extraction warnings are retained for review.")
            for message in journey.extraction_issue_messages:
                st.write(f"- {message}")
        st.caption(
            "This is a candidate representation, not an approved process, AI recommendation, or deployment decision."
        )


def _render_needs_your_decision(journey: ReviewJourneyView) -> None:
    st.subheader("Review progress")
    _render_review_progress(journey.progress)
    st.caption(
        "This queue is the existing Phase 4 approval readiness check. It does not count optional fields as approval requirements."
    )


def _render_approval_summary(journey: ReviewJourneyView) -> None:
    st.subheader("Approval summary")
    st.write(
        f"**Original extraction:** {journey.candidate_process_name or 'Unknown'}"
    )
    st.write(
        "**Current reviewed process:** "
        + (journey.reviewed_process_name or "Unknown")
    )
    st.write(
        "**Retained activity order:** "
        + (" → ".join(journey.reviewed_activities) or "No retained activities")
    )
    audit = journey.audit
    st.caption(
        "Review record: "
        f"{len(audit.corrections)} correction(s), "
        f"{len(audit.rejections_or_removals)} rejection/removal action(s), "
        f"{len(audit.structural_changes)} dependency/order/structure action(s), and "
        f"{len(audit.accepted_documented)} documented confirmation(s)."
    )
    if audit.human_supplied_fields:
        st.caption(
            "Added by the reviewer — no document evidence claimed: "
            + ", ".join(audit.human_supplied_fields)
        )
    if audit.retained_unknowns:
        st.caption(
            "Explicitly retained unknown values: " + ", ".join(audit.retained_unknowns)
        )
    unknown_total = sum(group.count for group in journey.unknown_groups)
    if unknown_total:
        st.caption(
            f"Unknown / not provided values still visible in this review: {unknown_total}. They remain unknown unless a reviewer takes an existing permitted action."
        )
    with st.expander("Review action trace"):
        categories = (
            ("Corrections", audit.corrections),
            ("Rejections or removals", audit.rejections_or_removals),
            ("Dependency, order, or structural decisions", audit.structural_changes),
            ("Directly documented confirmations", audit.accepted_documented),
            ("Retained unknowns", audit.retained_unknowns),
        )
        for label, fields in categories:
            st.markdown(f"**{label}**")
            if fields:
                for field_path in fields:
                    st.write(f"- {field_path}")
            else:
                st.caption("None recorded.")
    st.caption(
        "Provenance remains distinct: directly documented values retain source evidence; reviewer-supplied values do not claim document evidence; extraction suggestions remain suggestions; unknown values remain unknown."
    )


def _render_technical_traceability(session: ProcessReviewSession) -> None:
    """Keep existing field paths and document locators inspectable without new evidence logic."""

    with st.expander("Technical traceability"):
        st.caption(f"Persisted review ID: {session.review_id}")
        targets = iter_process_assertions(session)
        for step in session.steps:
            targets.extend(iter_step_assertions(session, step.candidate_step_id))
        documented = [
            target
            for target in targets
            if target.assertion.origin.value == InformationOrigin.DOCUMENT_SUPPORTED.value
            and target.assertion.evidence
        ]
        for target in documented:
            st.markdown(f"**{target.field_path}**")
            for evidence in target.assertion.evidence:
                st.caption(evidence.source_locator)
                st.code(evidence.exact_snippet, language=None, wrap_lines=True)


def _render_route_summary(snapshot) -> None:
    if not preliminary_ui_enabled():
        return
    intent = route_intent(snapshot)
    with st.container(border=True):
        st.markdown("### Planned route after process approval")
        if intent is None:
            st.warning("Choose what happens after validation before approval.")
            render_route_choice(snapshot, key_prefix="review-route-missing")
            return
        label = (
            "Explore this process"
            if intent.route.value == "EXPLORE_PROCESS"
            else "Run an organisational assessment"
        )
        st.write(f"**{label}**")
        st.caption(
            "Both routes use this same reviewed and approved current-state process."
        )
        if st.button("Change choice", key="review-change-route"):
            st.session_state.preliminary_change_route = True
            st.rerun()
        if st.session_state.get("preliminary_change_route"):
            render_route_choice(snapshot, key_prefix="review-route-change")


def _continue_journey_setup(snapshot) -> None:
    try:
        with st.spinner("Preparing your selected route…"):
            continue_first_time_route(snapshot)
    except Exception:
        st.session_state.preliminary_setup_incomplete = True
        st.error(
            "Your selected route could not start safely. The current-state process approval remains valid."
        )
        return
    st.session_state.pop("preliminary_change_route", None)
    switch_to_registered_page("process-journey")


def _render_approved(approved, snapshot) -> None:
    st.success("Current-state process explicitly approved.")
    st.caption(
        f"Review {approved.review.review_id} · Approved {approved.approval.approved_at.isoformat()}"
    )
    render_current_state(approved.business_process)
    with st.expander("Review provenance and audit"):
        st.write(f"Review events: {len(approved.review.events)}")
        for event in approved.review.events:
            st.caption(f"{event.sequence}. {event.action.value} — {event.field_path}")
    st.caption(
        "This approves the current-state process representation. It does not approve AI adoption, ROI, deployment readiness, or completion of all unknown information."
    )
    if preliminary_ui_enabled():
        try:
            state = current_journey_state(snapshot)
        except Exception:
            st.error(
                "Preliminary journey history could not be safely validated. No data was changed."
            )
            return
        if (
            state is not None
            and state.current_route.value != PreliminaryCurrentRoute.UNSELECTED.value
        ):
            label = (
                "Open Preliminary Assessment"
                if state.current_route.value == PreliminaryCurrentRoute.EXPLORE_PROCESS.value
                else "Open organisational assessment"
            )
            if st.button(label, type="primary"):
                switch_to_registered_page("process-journey")
            return
        intent = route_intent(snapshot)
        if intent is None:
            st.warning("Choose a route to continue after process approval.")
            render_route_choice(snapshot, key_prefix="approved-route")
            intent = route_intent(snapshot)
        if intent is not None:
            st.warning("Journey setup incomplete")
            st.write(
                "Your current-state process approval remains valid. You do not need to approve it again."
            )
            if st.button("Continue journey setup", type="primary"):
                _continue_journey_setup(snapshot)
        return
    if st.button("Open assessment results", type="primary"):
        switch_to_registered_page("results")


def _render_optional_workspace(
    session: ProcessReviewSession, journey: ReviewJourneyView
) -> None:
    st.subheader("Optional details")
    st.write(
        "These details can improve the process record, but they do not block validation. "
        "Only change them when you have reliable information."
    )
    with st.expander("Process description and objective", expanded=False):
        _assertion_editor(
            session,
            label="Process description (optional)",
            field_path="process.description",
            resolver=lambda working: working.process_description,
        )
        _assertion_editor(
            session,
            label="Process objective (optional)",
            field_path="process.objective",
            resolver=lambda working: working.process_objective,
        )

    retained_steps = [
        step
        for step in sorted(session.steps, key=lambda value: value.sequence)
        if step.retained
    ]
    if retained_steps:
        labels = {
            step.candidate_step_id: (
                f"Step {step.sequence}: {step.activity.value or 'Unnamed activity'}"
            )
            for step in retained_steps
        }
        selected_id = st.selectbox(
            "Choose a step to inspect",
            list(labels),
            format_func=lambda value: labels[value],
            key="optional-review-step",
        )
        with st.expander("Edit this step's optional details", expanded=False):
            _render_step(
                session,
                selected_id,
                journey.progress,
                include_required_controls=False,
            )

    with st.expander("Information not provided in the document", expanded=False):
        unknown_total = sum(group.count for group in journey.unknown_groups)
        if unknown_total:
            st.write(
                f"{unknown_total} optional values were not provided. That is allowed; they remain "
                "recorded as not provided unless you add legitimate information."
            )
            for group in journey.unknown_groups:
                st.write(f"- {group.step_label}: {group.count}")
        else:
            st.success("No optional values are currently marked as not provided.")

    with st.expander("Suggested details to double-check", expanded=False):
        if journey.inferred_field_paths:
            st.write(
                f"{len(journey.inferred_field_paths)} extracted detail"
                f"{'s were' if len(journey.inferred_field_paths) != 1 else ' was'} inferred "
                "rather than stated directly. Checking them is recommended but not required for approval."
            )
        else:
            st.success("No inferred details remain to check.")


def _render_final_approval_workspace(
    session: ProcessReviewSession, journey: ReviewJourneyView, snapshot
) -> None:
    st.subheader("Final approval")
    with st.container(border=True, key="review-approval-summary"):
        st.markdown("### Process ready for approval" if journey.progress.is_ready else "### Finish required review first")
        st.write(f"**Process:** {journey.reviewed_process_name or 'Unnamed process'}")
        process_name_confirmed = session.process_name.disposition.value in {
            ReviewDisposition.ACCEPTED.value,
            ReviewDisposition.CORRECTED.value,
        }
        activity_confirmed = sum(
            step.retained
            and step.activity.disposition.value
            in {ReviewDisposition.ACCEPTED.value, ReviewDisposition.CORRECTED.value}
            for step in session.steps
        )
        st.write(
            f"**Process name:** {'Confirmed' if process_name_confirmed else 'Check required'}"
        )
        st.write(
            f"**Activities:** {activity_confirmed} of "
            f"{len(journey.reviewed_activities)} confirmed"
        )
        st.write(
            f"**Step order:** {'Confirmed' if session.order_accepted else 'Check required'}"
        )
        optional_targets = iter_process_assertions(session)[1:]
        for step in session.steps:
            if not step.retained:
                continue
            optional_targets.extend(
                target
                for target in iter_step_assertions(
                    session, step.candidate_step_id
                )
                if target.field_path
                not in {
                    f"steps.{step.candidate_step_id}.activity",
                    f"steps.{step.candidate_step_id}.document_order",
                }
            )
        optional_reviewed = sum(
            target.assertion.disposition.value
            != ReviewDisposition.UNREVIEWED.value
            for target in optional_targets
        )
        optional_unknown = sum(
            target.assertion.knowledge_state.value == KnowledgeState.UNKNOWN.value
            for target in optional_targets
        )
        st.write(
            f"**Optional details:** {optional_reviewed} reviewed · "
            f"{optional_unknown} not provided"
        )
        with st.expander("View the reviewed activity order"):
            for index, activity in enumerate(journey.reviewed_activities, start=1):
                st.write(f"{index}. {activity}")

        if not journey.progress.is_ready:
            remaining = journey.progress.remaining_required
            verb = "needs" if remaining == 1 else "need"
            st.warning(
                f"{remaining} required check{'s' if remaining != 1 else ''} still "
                f"{verb} your attention. Return to Required review to finish "
                f"{'it' if remaining == 1 else 'them'}."
            )
            st.button(
                "Approve current-state process",
                type="primary",
                disabled=True,
                help="Complete every required check before approval.",
            )
            return

        st.success("All required checks are complete.")
        st.write(
            "Approval confirms that this is an acceptable representation of the current process. "
            "It does not approve AI adoption, deployment, ROI, or legal and security sign-off."
        )
        confirmation_key = (
            f"approve-current-state-{session.review_id}-{session.updated_at.isoformat()}"
        )
        confirmed = st.checkbox(
            "I approve this current-state process",
            key=confirmation_key,
            help="This confirmation is required before approval.",
        )
        if not confirmed:
            st.caption("Tick the approval confirmation to enable approval.")
        rationale = st.text_input(
            "Approval note (optional)",
            key=f"approval-rationale-{session.review_id}",
        )
        route_ready = (
            not preliminary_ui_enabled() or route_intent(snapshot) is not None
        )
        submitted = st.button(
            "Approve current-state process",
            type="primary",
            disabled=not confirmed or not route_ready,
            help=(
                "Choose the planned route before approval."
                if not route_ready
                else (
                    None
                    if confirmed
                    else "Tick the approval confirmation first."
                )
            ),
        )
        if submitted:
            result = workspace_service().approve(
                snapshot.assessment.assessment_id, rationale=rationale or None
            )
            if result.approved is None:
                for error in result.errors:
                    st.error(error.message)
            else:
                refreshed = refresh_workspace()
                if preliminary_ui_enabled() and route_intent(refreshed) is not None:
                    try:
                        with st.spinner("Preparing your selected route…"):
                            continue_first_time_route(refreshed)
                    except Exception:
                        st.session_state.preliminary_setup_incomplete = True
                        st.rerun()
                    if switch_to_registered_page("process-journey"):
                        return
                st.rerun()

    with st.expander("Technical review record"):
        _render_approval_summary(journey)
        _render_technical_traceability(session)


def render() -> None:
    render_page_header("Validate process")
    if frozen_evaluation_workspace_selected():
        st.info(
            "This is a frozen evaluation record. Process-validation changes are unavailable, and the ordinary workspace will not be opened."
        )
        return
    snapshot = hydrate_workspace()
    if snapshot is None:
        guard("Create or open an assessment first.")
    writes_available = phase4_review_writes_available()
    if not writes_available:
        st.info(
            "Review changes are unavailable because this is a frozen evaluation record. You can inspect any safely loaded current state, but it cannot be changed here."
        )
    approved = st.session_state.get("approved_review")
    if approved is not None:
        _render_approved(approved, snapshot)
        return
    candidate = st.session_state.get("candidate_extraction_result")
    if candidate is None or candidate.candidate is None:
        guard("Complete candidate extraction before starting process validation.")
    session = st.session_state.get("review_session")
    if session is None:
        st.warning("CANDIDATE PROCESS — NEEDS VALIDATION")
        st.write(
            "A candidate process was extracted from the document. Start validation to confirm or correct it before assessment."
        )
        if writes_available and st.button("Start process validation", type="primary"):
            try:
                workspace_service().start_review(snapshot.assessment.assessment_id)
            except Exception:
                st.error("Process validation could not start. Refresh and try again.")
                return
            refresh_workspace()
            st.rerun()
        return

    _render_route_summary(snapshot)

    selected_item_id = st.session_state.get("guided_review_selected_item")
    journey = build_review_journey(session, selected_item_id=selected_item_id)
    progress = journey.progress
    _sync_guided_focus(session, journey)
    if not writes_available:
        _render_review_summary(journey)
        _render_needs_your_decision(journey)
        return

    # Keep this top-level delta path present on every review rerun. If the
    # feedback element is inserted only after a save, every interactive block
    # below it moves by one position on the following rerun. Streamlit can then
    # retain the old keyed widgets as stale blocks when the page changes.
    feedback_slot = st.empty()
    feedback = st.session_state.pop("review_feedback", None)
    if feedback:
        feedback_slot.success(feedback)
    st.write(
        "Review the extracted process in a short guided sequence. Required checks are "
        "kept separate from optional details."
    )
    _render_workspace_progress(journey)
    st.session_state.setdefault("review-workspace-mode", "Required review")
    mode = st.segmented_control(
        "Review area",
        ["Required review", "Optional details", "Final approval"],
        key="review-workspace-mode",
        label_visibility="collapsed",
        width="stretch",
    )
    if mode == "Optional details":
        _render_optional_workspace(session, journey)
    elif mode == "Final approval":
        _render_final_approval_workspace(
            session, journey, snapshot
        )
    else:
        _render_requirement_buttons(session, journey)
        _render_selected_requirement(session, journey)
