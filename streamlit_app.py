"""Phase 7 Streamlit application entrypoint."""

import sys
from pathlib import Path

import streamlit as st

# Streamlit executes this file directly; keep the repository runnable before install.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from ai_adoption_engine.presentation.components.status import (
    render_mode_banner,
    render_progress,
)
from ai_adoption_engine.presentation.context import hydrate_workspace
from ai_adoption_engine.presentation.pages import (
    assessments,
    decision_package,
    gap_resolution,
    results,
    review,
    source,
)


st.set_page_config(
    page_title="AI Adoption Engine",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Static design tokens only; no document or user content is interpolated here.
st.markdown(
    """
    <style>
    .block-container {max-width: 1240px; padding-top: 1.8rem; padding-bottom: 4rem;}
    h1, h2, h3 {letter-spacing: -0.025em;}
    [data-testid="stMetric"] {background: #ffffff; border: 1px solid #dce4df; padding: 1rem; border-radius: .6rem;}
    [data-testid="stSidebar"] {border-right: 1px solid #dce4df;}
    </style>
    """,
    unsafe_allow_html=True,
)

snapshot = hydrate_workspace()
if st.session_state.get("workspace_load_error"):
    st.error(st.session_state.workspace_load_error)
with st.sidebar:
    st.markdown("### AI Adoption Engine")
    if snapshot is not None:
        st.markdown(f"**{snapshot.assessment.title}**")
        st.caption(snapshot.assessment.assessment_id)
        render_mode_banner(snapshot.assessment.execution_mode)
        render_progress(snapshot.assessment.current_stage)
    else:
        st.caption("Create or open an assessment to begin.")

pages = [
    st.Page(assessments.render, title="Assessments", icon=":material/home:", url_path="assessments", default=True),
    st.Page(source.render, title="Source & Extraction", icon=":material/description:", url_path="source"),
    st.Page(review.render, title="Process Review", icon=":material/fact_check:", url_path="review"),
    st.Page(results.render, title="Assessment Results", icon=":material/analytics:", url_path="results"),
    st.Page(decision_package.render, title="Decision Package", icon=":material/account_tree:", url_path="decision-package"),
    st.Page(gap_resolution.render, title="Gap resolution", icon=":material/help_center:", url_path="gap-resolution"),
]
page = st.navigation(pages, position="sidebar", expanded=True)
page.run()
