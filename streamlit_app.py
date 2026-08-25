"""Phase 7 Streamlit application entrypoint."""

import sys
from pathlib import Path

import streamlit as st

# Streamlit executes this file directly; keep the repository runnable before install.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from ai_adoption_engine.presentation.components.shell import NavGroup, render_sidebar
from ai_adoption_engine.presentation.context import (
    frozen_evaluation_workspace_selected,
    hydrate_workspace,
)
from ai_adoption_engine.presentation.pages import (
    assessments,
    decision_continuation,
    decision_package,
    gap_resolution,
    reassessment,
    results,
    review,
    source,
)
from ai_adoption_engine.presentation.theme import PRODUCT_NAME, inject_global_styles


st.set_page_config(
    page_title=PRODUCT_NAME,
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# The one centralised stylesheet: static design tokens only, injected once.
# No document, assessment or user content is interpolated into it.
inject_global_styles()

main_journey = [
    st.Page(assessments.render, title="Assessments", icon=":material/home:", url_path="assessments", default=True),
    st.Page(source.render, title="Source & Extraction", icon=":material/description:", url_path="source"),
    st.Page(review.render, title="Validate process", icon=":material/fact_check:", url_path="review"),
    st.Page(results.render, title="Assessment Results", icon=":material/analytics:", url_path="results"),
    st.Page(decision_package.render, title="Decision Package", icon=":material/account_tree:", url_path="decision-package"),
]
continuation = [
    st.Page(decision_continuation.render, title="Decision continuation", icon=":material/route:", url_path="decision-continuation"),
    st.Page(gap_resolution.render, title="Gap resolution", icon=":material/help_center:", url_path="gap-resolution"),
    st.Page(reassessment.render, title="Reassessment", icon=":material/restart_alt:", url_path="reassessment"),
]
pages = [*main_journey, *continuation]
page = st.navigation(pages, position="sidebar", expanded=True)
protected_p2_page = (
    frozen_evaluation_workspace_selected()
    and page.url_path in {"source", "review"}
)
snapshot = None if protected_p2_page else hydrate_workspace()
if st.session_state.get("workspace_load_error"):
    st.error(st.session_state.workspace_load_error)
with st.sidebar:
    render_sidebar(
        [
            NavGroup(None, main_journey),
            NavGroup("Optional continuation", continuation),
        ],
        active_page=page,
        snapshot=snapshot,
        notice=(
            "Frozen evaluation record — ordinary workspace access is disabled."
            if protected_p2_page
            else None
        ),
    )
page.run()
