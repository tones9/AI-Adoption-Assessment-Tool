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

from collections.abc import Sequence
from dataclasses import dataclass
from html import escape

import streamlit as st


@dataclass(frozen=True)
class HeaderSection:
    """One titled block of already-built business text."""

    heading: str
    lines: tuple[str, ...]


@dataclass(frozen=True)
class HeaderAction:
    """One named primary action placed inside its owning decision block."""

    section_heading: str
    label: str
    key: str
    icon: str | None = None


def render_decision_header(
    *,
    context_line: str,
    headline: str,
    sections: Sequence[HeaderSection],
    headline_heading: str = "Decision today",
    headline_note: str | None = None,
    boxed: bool = False,
    headline_as_title: bool = False,
    action: HeaderAction | None = None,
) -> bool:
    """Render where-am-I, the decision, and its supporting blocks in order.

    ``headline_heading`` names the decision block for the surface in question -
    an assessment reports the decision today, a Decision Package summarises the
    decision it delivers.  ``headline_note`` carries one short qualifier that
    belongs with the decision itself rather than with a later block.
    """

    st.caption(context_line)
    if headline_as_title:
        st.title(headline)
    else:
        st.subheader(headline_heading)
        st.markdown(f"### {headline}")
    if headline_note:
        st.caption(headline_note)
    action_clicked = False
    for section in sections:
        if not section.lines:
            continue
        block = st.container(border=True) if boxed else st.container()
        with block:
            if boxed:
                st.markdown(
                    f'<span class="aae-page-eyebrow">{escape(section.heading)}</span>',
                    unsafe_allow_html=True,
                )
            else:
                st.subheader(section.heading)
            for line in section.lines:
                st.write(line)
            if action is not None and action.section_heading == section.heading:
                action_clicked = st.button(
                    action.label,
                    key=action.key,
                    icon=action.icon,
                    type="primary",
                )
    return action_clicked
