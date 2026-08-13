"""Dependency-free current/future process flow cards."""

from __future__ import annotations

import streamlit as st


def render_current_state(process) -> None:
    st.subheader(process.name)
    if process.description:
        st.write(process.description)
    if process.business_objective:
        st.caption(f"Objective: {process.business_objective}")
    for index, step in enumerate(process.steps):
        with st.container(border=True):
            st.markdown(f"**{step.sequence}. {step.activity}**")
            if step.primary_actor:
                st.caption(f"Primary actor: {step.primary_actor}")
            if step.systems:
                st.caption("Systems: " + ", ".join(step.systems))
        if index < len(process.steps) - 1:
            st.caption("↓")


def render_future_state(workflow) -> None:
    st.warning(workflow.status.value, icon="⚠️")
    for index, step in enumerate(workflow.steps):
        with st.container(border=True):
            st.markdown(f"**{step.sequence}. {step.proposed_activity}**")
            st.caption(
                f"Intervention: {step.intervention_type.value.replace('_', ' ').title()}"
            )
            st.write(f"Recommendation: {step.recommendation_mode.value}")
            if step.capabilities:
                st.caption(
                    "AI capabilities: "
                    + ", ".join(item.value.replace("_", " ").title() for item in step.capabilities)
                )
            if step.human_roles:
                st.caption(
                    "Human controls: "
                    + ", ".join(item.role_type.value for item in step.human_roles)
                )
            if step.controls_and_constraints:
                st.write(step.controls_and_constraints)
        if index < len(workflow.steps) - 1:
            st.caption("↓")

