"""Explicit Phase 4 human-review and approval screen."""

from __future__ import annotations

from collections.abc import Callable, Sequence
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
    AssertionTarget,
    ReviewProgress,
    build_review_progress,
    document_supported_unreviewed,
    inferred_unreviewed,
    iter_process_assertions,
    iter_step_assertions,
    unknown_unreviewed_by_step,
)
from ai_adoption_engine.presentation.components.page_header import (
    render_page_header,
)


AssertionResolver = Callable[[ProcessReviewSession], ReviewedAssertion]
CollectionResolver = Callable[[ProcessReviewSession], ReviewedCollection]


def _step(session: ProcessReviewSession, step_id: str):
    return next(item for item in session.steps if item.candidate_step_id == step_id)


def _apply(
    session: ProcessReviewSession,
    operation: Callable[[ProcessReviewSession], None],
    *,
    success_message: str,
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
    st.session_state.review_feedback = success_message
    st.session_state.pop("review_focus_path", None)
    refresh_workspace()
    st.rerun()


def _confirm_document_supported(
    working: ProcessReviewSession,
    *,
    step_id: str | None,
    field_paths: list[str],
) -> None:
    targets = (
        iter_process_assertions(working)
        if step_id is None
        else iter_step_assertions(working, step_id)
    )
    by_path = {item.field_path: item for item in targets}
    service = workspace_service().review_service
    for field_path in field_paths:
        target = by_path[field_path]
        service.accept_assertion(
            working,
            target.assertion,
            field_path,
            rationale="Confirmed in a grouped review of document-supported facts.",
        )


def _render_document_confirmation_group(
    session: ProcessReviewSession,
    *,
    targets: list[AssertionTarget],
    key: str,
    scope_label: str,
    step_id: str | None = None,
) -> None:
    pending = document_supported_unreviewed(targets)
    if not pending:
        st.success(f"All document-supported facts for {scope_label} have been reviewed.")
        return
    st.info(
        f"{len(pending)} directly documented fact{'s' if len(pending) != 1 else ''} "
        "can be confirmed together. Inferred, unknown, corrected, rejected and human-supplied values are excluded."
    )
    with st.expander(f"Facts included in this confirmation ({len(pending)})"):
        for item in pending:
            st.markdown(f"**{item.label}**")
            st.write(item.assertion.value)
            for evidence in item.assertion.evidence:
                st.caption(evidence.source_locator)
                st.code(evidence.exact_snippet, language=None, wrap_lines=True)
    if st.button(
        f"Confirm {len(pending)} document-supported fact{'s' if len(pending) != 1 else ''}",
        key=f"confirm-documented-{key}",
        type="primary",
    ):
        field_paths = [item.field_path for item in pending]
        _apply(
            session,
            lambda working: _confirm_document_supported(
                working,
                step_id=step_id,
                field_paths=field_paths,
            ),
            success_message=(
                f"{len(pending)} document-supported fact"
                f"{'s' if len(pending) != 1 else ''} confirmed for {scope_label}. "
                "Each assertion has its own review disposition and audit event."
            ),
        )


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
) -> None:
    assertion = resolver(session)
    with st.container(border=True):
        if st.session_state.get("review_focus_path") == field_path:
            st.warning(f"Review attention requested here: {label}.")
        render_reviewed_assertion(assertion, label=label)
        if assertion.knowledge_state is KnowledgeState.UNKNOWN:
            if assertion.disposition is ReviewDisposition.UNKNOWN_RETAINED:
                actions = ["No change — unknown retained", "Resolve unknown"]
            else:
                actions = ["Choose an action", "Resolve unknown", "Retain unknown"]
        elif assertion.disposition is ReviewDisposition.UNREVIEWED:
            actions = ["Choose an action", "Accept", "Correct", "Reject"]
        elif assertion.disposition is ReviewDisposition.REJECTED:
            actions = ["No change — rejected", "Correct"]
        elif assertion.disposition is ReviewDisposition.CORRECTED:
            actions = ["No change — corrected", "Correct", "Reject"]
        else:
            actions = ["No change — accepted", "Correct", "Reject"]

        state_key = f"{field_path}-{session.updated_at.isoformat()}"
        action = st.selectbox(
            f"Review decision for {label}",
            actions,
            key=f"action-{state_key}",
        )
        corrected = None
        rationale = ""
        chosen_origin = InformationOrigin.HUMAN_SUPPLIED
        cited: list[ResolvedEvidenceReference] = []
        if action in {"Correct", "Resolve unknown"}:
            corrected = _value_input(assertion, state_key, value_kind)
            if evidence_choices:
                by_label = {
                    _evidence_option_label(reference): reference
                    for reference in evidence_choices
                }
                origin_choice = st.selectbox(
                    "Where does this value come from?",
                    [_HUMAN_SUPPLIED_CHOICE, _DOCUMENT_SUPPORTED_CHOICE],
                    key=f"origin-{state_key}",
                    help=(
                        "Only a document-supported value carries evidence into the "
                        "assessment. A human-supplied value is recorded but the "
                        "decision policy treats it as unevidenced."
                    ),
                )
                if origin_choice == _DOCUMENT_SUPPORTED_CHOICE:
                    chosen_origin = InformationOrigin.DOCUMENT_SUPPORTED
                    cited = [
                        by_label[selected]
                        for selected in st.multiselect(
                            "Supporting source evidence (required)",
                            list(by_label),
                            key=f"evidence-{state_key}",
                        )
                    ]
                    st.caption(
                        "The citation is recorded verbatim and shown in the decision "
                        "report. It is not checked for relevance to this value."
                    )
        if action in {"Correct", "Reject", "Resolve unknown"}:
            rationale = st.text_input(
                "Reviewer rationale (required)",
                placeholder="Explain the correction, rejection or supplied value",
                key=f"rationale-{state_key}",
            )
        actionable = action in {
            "Accept",
            "Correct",
            "Reject",
            "Resolve unknown",
            "Retain unknown",
        }
        submitted = st.button(
            "Apply review action",
            key=f"apply-{state_key}",
            disabled=not actionable,
            help=(
                None
                if actionable
                else "Choose a review action to enable this button."
            ),
        )
        if submitted:
            if action in {"Correct", "Reject", "Resolve unknown"} and not rationale.strip():
                st.error("Provide a rationale for this action.")
                return
            if chosen_origin is InformationOrigin.DOCUMENT_SUPPORTED and not cited:
                st.error("Select the source evidence that supports this value.")
                return

            def mutate(working: ProcessReviewSession) -> None:
                target = resolver(working)
                service = workspace_service().review_service
                if action == "Accept":
                    service.accept_assertion(working, target, field_path)
                elif action == "Correct":
                    service.correct_assertion(
                        working,
                        target,
                        field_path,
                        corrected,
                        rationale=rationale,
                        origin=chosen_origin,
                        evidence=list(cited),
                    )
                elif action == "Reject":
                    service.reject_assertion(
                        working, target, field_path, rationale=rationale
                    )
                elif action == "Resolve unknown":
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
                    service.retain_unknown(working, target, field_path)

            saved_action = (
                "unknown retained"
                if action == "Retain unknown"
                else action.lower()
            )
            _apply(
                session,
                mutate,
                success_message=f"{label}: {saved_action} saved.",
            )


def _collection_progress(collection: ReviewedCollection) -> str:
    if not collection.items:
        return "no extracted values · optional"
    reviewed = sum(
        item.disposition is not ReviewDisposition.UNREVIEWED
        for item in collection.items
    )
    return f"{reviewed}/{len(collection.items)} reviewed"


def _step_status(step, progress: ReviewProgress) -> str:
    if not step.retained:
        return ":gray-badge[Removed]"
    remaining = sum(
        item.step_id == step.candidate_step_id for item in progress.outstanding
    )
    if remaining:
        if step.activity.disposition is ReviewDisposition.UNREVIEWED:
            return ":gray-badge[Not reviewed]"
        return (
            f":orange-badge[{remaining} required item"
            f"{'s' if remaining != 1 else ''} remaining]"
        )
    return ":green-badge[Complete]"


def _open_outstanding(item) -> None:
    st.session_state["guided_review_selected_item"] = item.item_id
    if item.step_id is not None:
        st.session_state["selected-review-step"] = item.step_id
    st.session_state["review_focus_path"] = item.field_path
    st.session_state["review_feedback"] = (
        f"Opened {item.location_label} → {item.field_label}. {item.reason}"
    )
    st.rerun()


def _render_review_progress(progress: ReviewProgress) -> None:
    st.subheader("Review progress")
    columns = st.columns(3)
    columns[0].metric("Required items", progress.total_required)
    columns[1].metric("Complete", progress.completed_required)
    columns[2].metric("Remaining", progress.remaining_required)
    st.progress(
        progress.completion_ratio,
        text=(
            f"{progress.completed_required} of {progress.total_required} "
            "required review items complete"
        ),
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
    session: ProcessReviewSession, step_id: str, progress: ReviewProgress
) -> None:
    step = _step(session, step_id)
    if not step.retained:
        st.caption("Rejected step retained in the audit record.")
        return
    top = st.columns([5, 2, 2])
    top[0].markdown(f"### {step.sequence}. {step.activity.value or 'Unknown activity'}")
    top[0].markdown(_step_status(step, progress))
    retained_ids = [item.candidate_step_id for item in session.steps if item.retained]
    position = retained_ids.index(step_id)
    if top[1].button("Move earlier", key=f"up-{step_id}", disabled=position == 0):
        reordered = list(retained_ids)
        reordered[position - 1], reordered[position] = reordered[position], reordered[position - 1]
        _apply(
            session,
            lambda working: workspace_service().review_service.reorder_steps(
                working, reordered, rationale="Reviewer moved the step earlier."
            ),
            success_message=f"Step {step.sequence} moved earlier. Review and re-accept the updated order.",
        )
    if top[2].button("Move later", key=f"down-{step_id}", disabled=position == len(retained_ids) - 1):
        reordered = list(retained_ids)
        reordered[position + 1], reordered[position] = reordered[position], reordered[position + 1]
        _apply(
            session,
            lambda working: workspace_service().review_service.reorder_steps(
                working, reordered, rationale="Reviewer moved the step later."
            ),
            success_message=f"Step {step.sequence} moved later. Review and re-accept the updated order.",
        )

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


def _sync_guided_focus(journey: ReviewJourneyView) -> None:
    """Keep an optional UI bookmark aligned to the persisted preflight queue."""

    selected = journey.default_focus_item_id
    if selected is None:
        st.session_state.pop("guided_review_selected_item", None)
        st.session_state.pop("review_focus_path", None)
        return
    st.session_state["guided_review_selected_item"] = selected
    item = next(
        candidate for candidate in journey.required_items if candidate.item_id == selected
    )
    if item.step_id is not None:
        st.session_state["selected-review-step"] = item.step_id
    if item.field_path is not None:
        st.session_state["review_focus_path"] = item.field_path


def _render_review_summary(journey: ReviewJourneyView) -> None:
    st.header("Review summary")
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
    st.header("Needs your decision")
    with st.container(border=True):
        _render_review_progress(journey.progress)
        st.caption(
            "This queue is the existing Phase 4 approval readiness check. It does not count optional fields as approval requirements."
        )


def _render_document_says(
    session: ProcessReviewSession, journey: ReviewJourneyView
) -> None:
    st.header("What the document says")
    st.caption(
        "These are directly documented extraction assertions with their existing source locators. Confirming one records an individual review event; it does not create new evidence."
    )
    if not journey.document_groups:
        st.success("No directly documented unreviewed facts remain.")
        return
    for group in journey.document_groups:
        with st.expander(
            f"{group.scope_label} — {len(group.field_paths)} directly documented fact"
            f"{'s' if len(group.field_paths) != 1 else ''}",
            expanded=group.step_id is None,
        ):
            targets = (
                iter_process_assertions(session)
                if group.step_id is None
                else iter_step_assertions(session, group.step_id)
            )
            _render_document_confirmation_group(
                session,
                targets=targets,
                key="process" if group.step_id is None else f"step-{group.step_id}",
                scope_label=group.scope_label,
                step_id=group.step_id,
            )


def _render_unknowns(journey: ReviewJourneyView) -> None:
    st.header("Unknown or not provided")
    with st.container(border=True):
        if not journey.unknown_groups:
            st.success("No currently unreviewed unknown values are recorded.")
        else:
            st.write(
                "Unknown values remain explicitly unknown. Keep them as unknown unless legitimate information supports an existing Phase 4 review action."
            )
            for group in journey.unknown_groups:
                st.write(
                    f"- {group.step_label}: {group.count} unknown value"
                    f"{'s' if group.count != 1 else ''}"
                )
        st.caption(
            "Unknown values do not automatically become zero, false, or complete evidence. They only block approval when the real approval readiness check identifies a required field."
        )


def _render_recommended_checks(journey: ReviewJourneyView) -> None:
    st.header("Recommended checks")
    with st.container(border=True):
        if journey.inferred_field_paths:
            st.warning(
                f"{len(journey.inferred_field_paths)} extraction suggestion"
                f"{'s' if len(journey.inferred_field_paths) != 1 else ''} remain unreviewed."
            )
            st.caption(
                "These are suggested by extraction, not directly documented. Review is recommended but they are not presented as approval blockers unless the authoritative preflight says so."
            )
        else:
            st.success("No unreviewed extraction suggestions remain.")


def _render_dependencies_and_structure(
    session: ProcessReviewSession, journey: ReviewJourneyView
) -> None:
    st.header("Dependencies and structural issues")
    with st.container(border=True):
        if journey.invalid_dependency_field_paths:
            st.warning(
                "A retained dependency needs a valid target or must be rejected. Use the activity details below to make the existing correction."
            )
        if journey.open_blocking_conflict_ids:
            st.warning(
                "A process structure issue must be resolved before approval."
            )
        if not journey.invalid_dependency_field_paths and not journey.open_blocking_conflict_ids:
            st.success("No currently blocking dependencies or structural issues.")
        for conflict in session.conflicts:
            st.write(f"{conflict.code}: {conflict.message} ({conflict.status.value})")


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
            if target.assertion.origin is InformationOrigin.DOCUMENT_SUPPORTED
            and target.assertion.evidence
        ]
        for target in documented:
            st.markdown(f"**{target.field_path}**")
            for evidence in target.assertion.evidence:
                st.caption(evidence.source_locator)
                st.code(evidence.exact_snippet, language=None, wrap_lines=True)


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
    st.caption(
        "This approves the current-state process representation. It does not approve AI adoption, ROI, deployment readiness, or completion of all unknown information."
    )
    if st.button("Open assessment results", type="primary"):
        switch_to_registered_page("results")


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
        _render_approved(approved)
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

    selected_item_id = st.session_state.get("guided_review_selected_item")
    journey = build_review_journey(session, selected_item_id=selected_item_id)
    progress = journey.progress
    _sync_guided_focus(journey)
    if not writes_available:
        _render_review_summary(journey)
        _render_needs_your_decision(journey)
        return

    feedback = st.session_state.pop("review_feedback", None)
    if feedback:
        st.success(feedback)
    st.write(
        "Confirm what the document says, distinguish extraction suggestions and reviewer-supplied context, retain legitimate unknowns, and resolve any structural blockers."
    )
    _render_review_summary(journey)
    _render_needs_your_decision(journey)
    _render_document_says(session, journey)
    _render_unknowns(journey)
    _render_dependencies_and_structure(session, journey)
    _render_recommended_checks(journey)

    st.header("Review more detail")
    st.subheader("Process identity")
    if st.session_state.get("review_focus_path") == "process.name":
        st.warning("Review attention requested here: accept or correct the process name below.")
    _assertion_editor(
        session,
        label="Process name",
        field_path="process.name",
        resolver=lambda working: working.process_name,
    )
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

    st.subheader("Ordered activities")
    ordered_steps = sorted(session.steps, key=lambda value: value.sequence)
    for item in ordered_steps:
        st.markdown(
            f"**{item.sequence}. {item.activity.value or 'Unknown activity'}**  \n"
            f"{_step_status(item, progress)}"
        )
    retained_steps = [item for item in ordered_steps if item.retained]
    step_labels = {
        item.candidate_step_id: f"Step {item.sequence}: {item.activity.value or 'Unknown activity'}"
        for item in retained_steps
    }
    if retained_steps:
        if st.session_state.get("selected-review-step") not in step_labels:
            st.session_state.pop("selected-review-step", None)
        selected_step_id = st.selectbox(
            "Select an activity to review in detail",
            list(step_labels),
            format_func=lambda value: step_labels[value],
            key="selected-review-step",
        )
        with st.container(border=True):
            _render_step(session, selected_step_id, progress)
    else:
        st.error("No process activities are currently retained. Restore or retain at least one activity before approval.")

    with st.container(border=True):
        st.subheader("Step order")
        if st.session_state.get("review_focus_path") == "process.steps.order":
            st.warning("Opened from Review progress. Confirm the displayed order below.")
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
                success_message="Step order accepted.",
            )

    with st.container(border=True):
        st.subheader("Resolve structural issues")
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
                            success_message="Blocking conflict resolved.",
                        )

    st.header("Ready for approval")
    with st.container(border=True):
        _render_approval_summary(journey)
        st.subheader("Explicit approval")
        st.write(
            "Approval confirms an acceptable human-reviewed representation of the current-state process. It does not approve AI adoption, deployment, ROI, complete evidence, legal/security sign-off, or a recommendation. Unknown information may remain explicitly unknown."
        )
        _render_technical_traceability(session)
        if not journey.progress.is_ready:
            noun = "item" if journey.progress.remaining_required == 1 else "items"
            verb = "remains" if journey.progress.remaining_required == 1 else "remain"
            st.error(
                f"Not ready for approval — {journey.progress.remaining_required} required "
                f"{noun} {verb}."
            )
            for item in journey.required_items:
                st.write(
                    f"- {item.location_label} → {item.field_label}: {item.reason}"
                )
            st.button(
                "Approve current-state process",
                type="primary",
                disabled=True,
                help=(
                    f"Resolve the {journey.progress.remaining_required} required item"
                    f"{'s' if journey.progress.remaining_required != 1 else ''} listed immediately above."
                ),
            )
            return

        st.success("Ready for approval — all required review items are complete.")
        st.caption("Confirm the statement below to enable approval.")
        confirmation_key = f"approve-current-state-{session.review_id}-{session.updated_at.isoformat()}"
        confirmed = st.checkbox(
            "APPROVE CURRENT-STATE PROCESS",
            key=confirmation_key,
            help="This explicit confirmation is required before approval.",
        )
        rationale = st.text_input(
            "Optional approval rationale",
            key=f"approval-rationale-{session.review_id}",
        )
        submitted = st.button(
            "Approve current-state process",
            type="primary",
            disabled=not confirmed,
            help=(
                None
                if confirmed
                else "Select APPROVE CURRENT-STATE PROCESS to enable approval."
            ),
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
