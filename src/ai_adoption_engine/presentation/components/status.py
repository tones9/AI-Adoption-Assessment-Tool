"""Shared, business-readable workflow and mode status."""

from __future__ import annotations

import streamlit as st

from ai_adoption_engine.workspace.models import ExecutionMode, WorkflowStage


_STAGES = [
    (WorkflowStage.INGESTED, "Source"),
    (WorkflowStage.CANDIDATE_READY, "Candidate"),
    (WorkflowStage.IN_REVIEW, "Review"),
    (WorkflowStage.APPROVED, "Approved"),
    (WorkflowStage.ASSESSED, "Assessed"),
    (WorkflowStage.PACKAGE_READY, "Decision package"),
]


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
    rank = {WorkflowStage.NEW: 0, **{item: index for index, (item, _) in enumerate(_STAGES, start=1)}}
    current = rank[stage]
    columns = st.columns(len(_STAGES))
    for index, ((_, label), column) in enumerate(zip(_STAGES, columns), start=1):
        with column:
            st.caption(("✓ " if index <= current else "○ ") + label)


def guard(message: str) -> None:
    st.info(message, icon="ℹ️")
    st.stop()
