"""Assessment creation and reopen screen."""

import streamlit as st

from ai_adoption_engine.workspace.models import ExecutionMode
from ai_adoption_engine.presentation.context import (
    clear_workspace_state,
    select_assessment,
    switch_to_registered_page,
    workspace_writes_available,
    workspace_service,
)
from ai_adoption_engine.presentation.components.page_header import (
    render_page_header,
)
from ai_adoption_engine.presentation.components.primitives import (
    destructive_action,
    render_badge,
    render_guard_state,
)


def render() -> None:
    render_page_header(
        "AI Adoption Assessment",
        purpose=(
            "Assess one documented current-state business process through ingestion, "
            "human validation, deterministic assessment and decision support."
        ),
    )
    st.info(
        "Local, single-user MVP. SQLite data is not encrypted at rest. "
        "Do not expose this application as a shared or public service for confidential material."
    )

    writes_available = workspace_writes_available()
    if writes_available:
        with st.container(border=True):
            st.subheader("Start a new assessment")
            with st.form("new-assessment", clear_on_submit=True):
                title = st.text_input("Assessment title", placeholder="Customer complaint handling")
                mode_label = st.radio(
                    "Extraction mode",
                    [
                        "Offline demo — scripted synthetic extraction",
                        "Live provider — configured provider and local credentials",
                    ],
                )
                acknowledged = st.checkbox(
                    "I understand that saved parsed document content is stored locally in an unencrypted SQLite database."
                )
                submitted = st.form_submit_button("Create assessment", type="primary")
            if submitted:
                if not title.strip():
                    st.error("Enter an assessment title.")
                elif not acknowledged:
                    st.error("Acknowledge the local-storage notice before continuing.")
                else:
                    mode = (
                        ExecutionMode.OFFLINE_DEMO
                        if mode_label.startswith("Offline")
                        else ExecutionMode.LIVE_PROVIDER
                    )
                    record = workspace_service().repository.create_assessment(title, mode)
                    select_assessment(record.assessment_id)
                    st.success("Assessment created. Open Source & Extraction to continue.")
                    st.rerun()
    else:
        st.info(
            "This is a frozen evaluation workspace. Saved assessments can be inspected, but ordinary create and delete actions are unavailable."
        )

    st.subheader("Saved assessments")
    assessments = workspace_service().repository.list_assessments()
    if not assessments:
        render_guard_state(
            "No saved assessments yet. Start a new assessment above to create the first record.",
            icon=":material/folder_open:",
        )
        return
    for item in assessments:
        with st.container(border=True):
            left, middle, right = st.columns([5, 2, 1.5], vertical_alignment="center")
            with left:
                st.markdown(f"**{item.title}**")
                created = item.created_at.astimezone().strftime("%d %b %Y")
                mode = item.execution_mode.value.replace("-", " ").title()
                st.caption(f"Created {created} · {mode}")
                st.caption(item.source_filename or "No source supplied")
            with middle:
                render_badge(
                    item.current_stage.value.replace("-", " ").title(),
                    tone=(
                        "primary"
                        if item.current_stage.value in {"approved", "assessed", "package-ready"}
                        else "muted"
                    ),
                )
            with right:
                if st.button("Open", key=f"open-{item.assessment_id}", width="stretch"):
                    select_assessment(item.assessment_id)
                    if not switch_to_registered_page("source"):
                        st.rerun()
            st.caption(f"Assessment ID: {item.assessment_id}")
            if writes_available:
                with st.expander("Delete assessment"):
                    confirmed = st.checkbox(
                        "Permanently delete this assessment and all historical artifacts",
                        key=f"delete-confirm-{item.assessment_id}",
                    )
                    with destructive_action(item.assessment_id):
                        if st.button(
                            "Delete permanently",
                            key=f"delete-{item.assessment_id}",
                            disabled=not confirmed,
                        ):
                            workspace_service().repository.delete_assessment(
                                item.assessment_id, confirmed=True
                            )
                            if st.session_state.get("selected_assessment_id") == item.assessment_id:
                                st.session_state.pop("selected_assessment_id", None)
                                clear_workspace_state()
                            st.rerun()
