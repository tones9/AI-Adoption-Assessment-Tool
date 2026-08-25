"""Shared, business-readable workflow and mode status."""

from __future__ import annotations

from html import escape

import streamlit as st

from ai_adoption_engine.presentation.components.primitives import render_guard_state
from ai_adoption_engine.workspace.models import ExecutionMode, WorkflowStage


_STAGES = [
    (WorkflowStage.INGESTED, "Source"),
    (WorkflowStage.CANDIDATE_READY, "Candidate"),
    (WorkflowStage.IN_REVIEW, "Review"),
    (WorkflowStage.APPROVED, "Approved"),
    (WorkflowStage.ASSESSED, "Assessed"),
    (WorkflowStage.PACKAGE_READY, "Decision package"),
]

# Completed / current / upcoming are carried by symbol, weight and structure,
# never by colour alone.
_MARKS = {"done": "✓", "current": "→", "todo": "•"}


def render_mode_banner(mode: ExecutionMode) -> None:
    if mode is ExecutionMode.OFFLINE_DEMO:
        st.warning(
            "OFFLINE DEMO — SCRIPTED SYNTHETIC EXTRACTION. "
            "No live model is used and extraction is restricted to the bundled fixture.",
            icon="🧪",
        )
    else:
        st.info(
            "LIVE PROVIDER MODE — extraction uses the configured provider only when you explicitly start it.",
            icon="☁️",
        )


def render_progress(stage: WorkflowStage) -> None:
    """Render the six workspace stages as a vertical rail.

    A vertical list is used because the sidebar is 248px wide: six evenly
    divided columns cannot hold these labels without breaking them mid-word.
    The stage semantics are unchanged - the workspace's recorded stage is the
    current one, everything before it is complete and everything after it is
    still to come.
    """

    rank = {WorkflowStage.NEW: 0, **{item: index for index, (item, _) in enumerate(_STAGES, start=1)}}
    current = rank[stage]
    rows = []
    for index, (_, label) in enumerate(_STAGES, start=1):
        if index < current:
            state = "done"
        elif index == current:
            state = "current"
        else:
            state = "todo"
        rows.append(
            f'<div class="aae-stage-row aae-stage-{state}">'
            f'<span class="aae-stage-mark">{_MARKS[state]}</span>'
            f'<span class="aae-stage-label">{escape(label)}</span>'
            "</div>"
        )
    st.markdown(
        '<div class="aae-stage">' + "".join(rows) + "</div>",
        unsafe_allow_html=True,
    )


def guard(message: str) -> None:
    """Stop the page on an unmet prerequisite, in the shared guard panel.

    The condition and the message are unchanged; only the presentation is
    shared.
    """

    render_guard_state(message)
    st.stop()
