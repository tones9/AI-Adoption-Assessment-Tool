"""Explicit default-off activation and Streamlit operation identities."""

from __future__ import annotations

import os
from uuid import uuid4

import streamlit as st

from ai_adoption_engine.formal.composition import (
    DEFAULT_FOUR_GATE_POLICY,
    FormalAssessmentServiceBundle,
    build_formal_assessment_service_bundle,
)
from ai_adoption_engine.presentation.context import frozen_evaluation_workspace_selected
from ai_adoption_engine.presentation.preliminary_ui import preliminary_ui_enabled
from ai_adoption_engine.workspace.composition import DEFAULT_DATABASE_PATH


FORMAL_ASSESSMENT_UI_ENV = "AI_ADOPTION_ENGINE_FORMAL_ASSESSMENT_UI"
_TRUTHY = frozenset({"1", "true", "yes", "on"})
_TOKENS_KEY = "formal_assessment_action_tokens"


def formal_assessment_ui_enabled() -> bool:
    """Return the one deployment-wide, default-off activation decision."""

    return (
        preliminary_ui_enabled()
        and os.environ.get(FORMAL_ASSESSMENT_UI_ENV, "").strip().lower() in _TRUTHY
    )


@st.cache_resource
def _cached_formal_assessment_services(
    database_path: str,
    policy_path: str,
) -> FormalAssessmentServiceBundle:
    return build_formal_assessment_service_bundle(database_path, policy_path=policy_path)


def formal_assessment_services() -> FormalAssessmentServiceBundle:
    """Open migration-8 persistence only after every product guard passes."""

    if not formal_assessment_ui_enabled():
        raise RuntimeError("Formal Assessment UI is not enabled")
    if frozen_evaluation_workspace_selected():
        raise RuntimeError("Formal Assessment writes are unavailable for frozen workspaces")
    path = os.environ.get("AI_ADOPTION_ENGINE_DB_PATH", str(DEFAULT_DATABASE_PATH))
    # The explicit path is part of the cache identity even though it is currently
    # constant.  It avoids conflating a test/deployment policy with another DB.
    policy = str(DEFAULT_FOUR_GATE_POLICY)
    return _cached_formal_assessment_services(path, policy)


def formal_assessment_action_token(operation_key: str) -> str:
    tokens = st.session_state.setdefault(_TOKENS_KEY, {})
    token = tokens.get(operation_key)
    if token is None:
        token = f"formal-assessment-ui-{uuid4()}"
        tokens[operation_key] = token
    return token


def clear_formal_assessment_action_token(operation_key: str) -> None:
    tokens = st.session_state.get(_TOKENS_KEY)
    if isinstance(tokens, dict):
        tokens.pop(operation_key, None)
