"""The shared decision header for decision-facing pages.

Every primary decision surface answers the same five questions in the same
order: where am I, what was decided, why, what does it mean, what happens next.
This component renders that block from already-built text so Assessment
Results, the Decision Package and the Decision Continuation Workspace cannot
drift apart.

It is presentation-only.  It receives finished sentences and never interprets
an assessment, reads a policy, or decides what to say.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence

import streamlit as st


@dataclass(frozen=True)
class HeaderSection:
    """One titled block of already-built business text."""

    heading: str
    lines: tuple[str, ...]


def render_decision_header(
    *,
    context_line: str,
    headline: str,
    sections: Sequence[HeaderSection],
) -> None:
    """Render where-am-I, the decision, and its supporting blocks in order."""

    st.caption(context_line)
    st.subheader("Decision today")
    st.markdown(f"### {headline}")
    for section in sections:
        if not section.lines:
            continue
        st.subheader(section.heading)
        for line in section.lines:
            st.write(line)
