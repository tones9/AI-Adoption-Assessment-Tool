"""The single expandable technical section used by decision-facing pages.

Owning the label in one place is the point: the governing design fixes exactly
one Layer 2 control, ``Technical reasoning and evidence``, so a reader learns it
once and finds it everywhere.  This component renders nothing itself - callers
write the authoritative values inside the returned container.
"""

from __future__ import annotations

import streamlit as st


TECHNICAL_DETAILS_LABEL = "Technical reasoning and evidence"


def technical_details(*, expanded: bool = False):
    """Return the canonical, collapsed-by-default technical section."""

    return st.expander(TECHNICAL_DETAILS_LABEL, expanded=expanded)
