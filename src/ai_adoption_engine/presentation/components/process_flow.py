"""Dependency-free current/future process flow cards."""

from __future__ import annotations

import streamlit as st

from ai_adoption_engine.models.decision_support import ProposedFutureStateWorkflow
from ai_adoption_engine.models.four_gate_decision_support import (
    FourGateProposedFutureStateWorkflow,
)
from ai_adoption_engine.presentation import labels
from ai_adoption_engine.presentation.contracts import (
    UnsupportedPresentationContract,
)


def render_current_state(process) -> None:
    st.subheader(process.name)
    if process.description:
        st.write(process.description)
    if process.business_objective:
        st.caption(f"Objective: {process.business_objective}")
    for index, step in enumerate(process.steps):
        with st.container(border=True):
            st.markdown(f"**{step.sequence}. {step.activity}**")
            if step.actor:
                st.caption(f"Primary actor: {step.actor}")
            if step.systems:
                st.caption("Systems: " + ", ".join(step.systems))
        if index < len(process.steps) - 1:
            st.caption("↓")


def render_future_state(workflow) -> None:
    if isinstance(workflow, FourGateProposedFutureStateWorkflow):
        st.warning(workflow.status, icon="⚠️")
        for index, step in enumerate(workflow.steps):
            with st.container(border=True):
                st.markdown(f"**{step.sequence}. {step.proposed_activity}**")
                st.write(
                    "Final decision: "
                    + labels.four_gate_outcome_label(step.final_outcome.value)
                )
                st.caption(
                    "Capability use: "
                    + labels.human_label(step.capability_use_status.value)
                )
                if step.capabilities:
                    st.caption(
                        "AI capabilities: "
                        + ", ".join(
                            labels.human_label(item.value)
                            for item in step.capabilities
                        )
                    )
                if step.controls_and_constraints:
                    st.write(step.controls_and_constraints)
            if index < len(workflow.steps) - 1:
                st.caption("↓")
        return
    if not isinstance(workflow, ProposedFutureStateWorkflow):
        raise UnsupportedPresentationContract(
            "The future-state artifact contract is not supported for presentation."
        )
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
