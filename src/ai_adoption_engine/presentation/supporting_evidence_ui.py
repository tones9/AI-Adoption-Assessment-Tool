"""Default-off activation and session orchestration for supporting evidence."""

from __future__ import annotations

import os
from uuid import uuid4

import streamlit as st

from ai_adoption_engine.presentation.context import (
    frozen_evaluation_workspace_selected,
)
from ai_adoption_engine.presentation.preliminary_ui import (
    default_on_flag_enabled,
    preliminary_ui_enabled,
)
from ai_adoption_engine.supporting_evidence.composition import (
    SupportingEvidenceServiceBundle,
    build_supporting_evidence_service_bundle,
)
from ai_adoption_engine.workspace.composition import DEFAULT_DATABASE_PATH


SUPPORTING_EVIDENCE_UI_ENV = "AI_ADOPTION_ENGINE_SUPPORTING_EVIDENCE_UI"
_TOKENS_KEY = "supporting_evidence_action_tokens"


def supporting_evidence_ui_enabled() -> bool:
    return preliminary_ui_enabled() and default_on_flag_enabled(
        SUPPORTING_EVIDENCE_UI_ENV
    )


@st.cache_resource
def _cached_supporting_evidence_services(
    database_path: str,
) -> SupportingEvidenceServiceBundle:
    return build_supporting_evidence_service_bundle(database_path)


def supporting_evidence_services() -> SupportingEvidenceServiceBundle:
    if not supporting_evidence_ui_enabled():
        raise RuntimeError("Supporting-evidence UI is not enabled")
    if frozen_evaluation_workspace_selected():
        raise RuntimeError("Supporting-evidence writes are unavailable for frozen workspaces")
    path = os.environ.get("AI_ADOPTION_ENGINE_DB_PATH", str(DEFAULT_DATABASE_PATH))
    return _cached_supporting_evidence_services(path)


def supporting_action_token(operation_key: str) -> str:
    tokens = st.session_state.setdefault(_TOKENS_KEY, {})
    token = tokens.get(operation_key)
    if token is None:
        token = f"supporting-ui-{uuid4()}"
        tokens[operation_key] = token
    return token


def clear_supporting_action_token(operation_key: str) -> None:
    tokens = st.session_state.get(_TOKENS_KEY)
    if isinstance(tokens, dict):
        tokens.pop(operation_key, None)
