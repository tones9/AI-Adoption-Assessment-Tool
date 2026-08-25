"""The shared page header used by every page.

One header component, one place that decides how a page announces itself: an
optional eyebrow that says where the reader is, the page title, and an optional
one-line statement of what the page is for.

The header is rendered *before* any guard or empty state so a reader always
knows which page they are on, even when the page cannot show content yet.  The
title is still emitted with ``st.title`` so it remains the page's semantic H1.

Presentation only: it receives finished strings and never composes them.
"""

from __future__ import annotations

from html import escape

import streamlit as st


def render_page_header(
    title: str,
    *,
    eyebrow: str | None = None,
    purpose: str | None = None,
) -> None:
    """Render eyebrow, H1 and purpose line in that fixed order."""

    if eyebrow:
        st.markdown(
            f'<span class="aae-page-eyebrow">{escape(eyebrow)}</span>',
            unsafe_allow_html=True,
        )
    st.title(title)
    if purpose:
        st.markdown(
            f'<p class="aae-purpose">{escape(purpose)}</p>',
            unsafe_allow_html=True,
        )
