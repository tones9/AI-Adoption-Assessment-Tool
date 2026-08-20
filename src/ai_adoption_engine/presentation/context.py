"""Shared Streamlit composition and workspace hydration."""

from __future__ import annotations

import os

import streamlit as st

from ai_adoption_engine.workspace.composition import (
    DEFAULT_DATABASE_PATH,
    build_m2_reassessment_service,
    build_workspace_service,
)
from ai_adoption_engine.workspace.models import ArtifactType
from ai_adoption_engine.persistence.base import PersistenceError


@st.cache_resource
def get_workspace_service(database_path: str):
    return build_workspace_service(database_path)


@st.cache_resource
def get_m2_reassessment_service(database_path: str):
    return build_m2_reassessment_service(database_path)


def workspace_service():
    path = os.environ.get("AI_ADOPTION_ENGINE_DB_PATH", str(DEFAULT_DATABASE_PATH))
    return get_workspace_service(path)


def m2_reassessment_service():
    path = os.environ.get("AI_ADOPTION_ENGINE_DB_PATH", str(DEFAULT_DATABASE_PATH))
    return get_m2_reassessment_service(path)


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
    ):
        st.session_state.pop(key, None)


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
