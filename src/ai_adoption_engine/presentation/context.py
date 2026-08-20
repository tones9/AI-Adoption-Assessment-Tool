"""Shared Streamlit composition and workspace hydration."""

from __future__ import annotations

import os

import streamlit as st

from ai_adoption_engine.workspace.composition import (
    DEFAULT_DATABASE_PATH,
    build_decision_continuation_service,
    build_m2_reassessment_service,
    build_workspace_service,
)
from ai_adoption_engine.workspace.models import ArtifactType
from ai_adoption_engine.persistence.base import PersistenceError
from ai_adoption_engine.persistence.reassessment import (
    M2FrozenWorkspaceError,
    assert_m2_write_target_allowed,
)


@st.cache_resource
def get_workspace_service(database_path: str):
    return build_workspace_service(database_path)


@st.cache_resource
def get_m2_reassessment_service(database_path: str):
    return build_m2_reassessment_service(database_path)


@st.cache_resource
def get_decision_continuation_service(database_path: str):
    return build_decision_continuation_service(database_path)


def workspace_service():
    path = os.environ.get("AI_ADOPTION_ENGINE_DB_PATH", str(DEFAULT_DATABASE_PATH))
    return get_workspace_service(path)


def m2_reassessment_service():
    path = os.environ.get("AI_ADOPTION_ENGINE_DB_PATH", str(DEFAULT_DATABASE_PATH))
    return get_m2_reassessment_service(path)


def grw_continuation_available() -> bool:
    """Return whether GRW continuation may be composed for this database path."""

    path = os.environ.get("AI_ADOPTION_ENGINE_DB_PATH", str(DEFAULT_DATABASE_PATH))
    try:
        assert_m2_write_target_allowed(path)
    except M2FrozenWorkspaceError:
        return False
    return True


def decision_continuation_service():
    path = os.environ.get("AI_ADOPTION_ENGINE_DB_PATH", str(DEFAULT_DATABASE_PATH))
    return get_decision_continuation_service(path)


def clear_workspace_state() -> None:
    for key in (
        "loaded_assessment_id",
        "workspace_snapshot",
        "ingestion_result",
        "candidate_extraction_result",
        "review_session",
        "approved_review",
        "integrated_assessment_result",
        "decision_package_result",
        "selected_step_id",
        "grw_m2_run_id",
        "dcw_selected_m2_run_id",
        "dcw_return_page",
    ):
        st.session_state.pop(key, None)


def switch_to_registered_page(page_key: str) -> bool:
    """Switch through a Page definition matching the app's native navigation."""

    if page_key == "decision-continuation":
        from ai_adoption_engine.presentation.pages import decision_continuation

        page = st.Page(
            decision_continuation.render,
            title="Decision continuation",
            icon=":material/route:",
            url_path="decision-continuation",
        )
    elif page_key == "gap-resolution":
        from ai_adoption_engine.presentation.pages import gap_resolution

        page = st.Page(
            gap_resolution.render,
            title="Gap resolution",
            icon=":material/help_center:",
            url_path="gap-resolution",
        )
    elif page_key == "reassessment":
        from ai_adoption_engine.presentation.pages import reassessment

        page = st.Page(
            reassessment.render,
            title="Reassessment",
            icon=":material/restart_alt:",
            url_path="reassessment",
        )
    else:
        return False
    st.switch_page(page)
    return True


def select_assessment(assessment_id: str) -> None:
    clear_workspace_state()
    st.session_state.selected_assessment_id = assessment_id
    hydrate_workspace(force=True)


def hydrate_workspace(*, force: bool = False):
    assessment_id = st.session_state.get("selected_assessment_id")
    if not assessment_id:
        return None
    if (
        not force
        and st.session_state.get("loaded_assessment_id") == assessment_id
        and st.session_state.get("workspace_snapshot") is not None
    ):
        return st.session_state.workspace_snapshot
    try:
        snapshot = workspace_service().repository.load_workspace(assessment_id)
    except PersistenceError:
        clear_workspace_state()
        st.session_state.workspace_load_error = (
            "The saved assessment could not be opened because an artifact failed integrity or schema validation. "
            "No partial state was loaded."
        )
        return None
    st.session_state.pop("workspace_load_error", None)
    st.session_state.loaded_assessment_id = assessment_id
    st.session_state.workspace_snapshot = snapshot
    mapping = {
        ArtifactType.INGESTION_RESULT: "ingestion_result",
        ArtifactType.CANDIDATE_EXTRACTION_RESULT: "candidate_extraction_result",
        ArtifactType.REVIEW_SESSION: "review_session",
        ArtifactType.APPROVED_REVIEW: "approved_review",
        ArtifactType.INTEGRATED_ASSESSMENT_RESULT: "integrated_assessment_result",
        ArtifactType.DECISION_PACKAGE_RESULT: "decision_package_result",
    }
    for artifact_type, key in mapping.items():
        artifact = snapshot.active_artifacts.get(artifact_type)
        if artifact is None:
            st.session_state.pop(key, None)
        else:
            st.session_state[key] = artifact.payload
    return snapshot


def refresh_workspace():
    return hydrate_workspace(force=True)
