"""The application shell: brand, grouped navigation and assessment context.

The sidebar is the most-seen surface in the product, so it is composed in one
place.  Three things live here and nowhere else:

* the product's display name and byline;
* the navigation list, grouped into the main journey and the optional
  continuation branch;
* the open assessment's context - title, technical identifier, execution-mode
  disclosure and workspace stage.

Navigation semantics are unchanged.  The links are ``st.page_link`` links to
the very same ``st.Page`` objects that ``st.navigation`` registers, so there is
one routing definition and no second source of truth about destinations.  The
grouping is visual only: order and destinations are exactly as before.

Presentation only - it reads an already-loaded snapshot and never loads,
decides or advances anything.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from html import escape

import streamlit as st

from ai_adoption_engine.presentation.components.status import (
    render_mode_banner,
    render_progress,
)
from ai_adoption_engine.presentation.theme import PRODUCT_BYLINE, PRODUCT_NAME


NO_ASSESSMENT_OPEN = "No assessment open."


@dataclass(frozen=True)
class NavGroup:
    """One visual group of navigation links.

    ``eyebrow`` is a group label; ``None`` means the group carries no label.
    ``pages`` are the registered ``st.Page`` objects, in their fixed order.
    """

    eyebrow: str | None
    pages: Sequence[object]


def render_brand() -> None:
    """Render the product name and byline at the top of the sidebar."""

    st.markdown(
        f'<div class="aae-brand">{escape(PRODUCT_NAME)}</div>'
        f'<div class="aae-byline">{escape(PRODUCT_BYLINE)}</div>'
        '<div class="aae-rule"></div>',
        unsafe_allow_html=True,
    )


def render_nav(groups: Sequence[NavGroup], *, active_page=None) -> None:
    """Render the grouped navigation links and mark the active destination."""

    for index, group in enumerate(groups):
        if index:
            st.markdown('<div class="aae-rule"></div>', unsafe_allow_html=True)
        if group.eyebrow:
            st.markdown(
                f'<span class="aae-eyebrow">{escape(group.eyebrow)}</span>',
                unsafe_allow_html=True,
            )
        for page in group.pages:
            with st.container(key=f"aae-nav-{_slug(page)}"):
                st.page_link(page)
    if active_page is not None:
        _mark_active(active_page)


def _slug(page) -> str:
    """A stable CSS hook for one navigation row, from its registered title."""

    title = str(getattr(page, "title", "") or "page").lower()
    return "".join(
        character if character.isalnum() else "-" for character in title
    ).strip("-") or "page"


def _mark_active(page) -> None:
    """Give the current destination the active treatment.

    Streamlit does not expose a stable per-item hook on a page link, so the
    active row is addressed through the container key this shell assigned to
    it.  The key is derived from the application's own registered page title.
    """

    key = _slug(page)
    st.markdown(
        f"""
        <style>
        .st-key-aae-nav-{key} a[data-testid="stPageLink-NavLink"] {{
            background: var(--aae-primary) !important;
        }}
        .st-key-aae-nav-{key} a[data-testid="stPageLink-NavLink"] p,
        .st-key-aae-nav-{key} a[data-testid="stPageLink-NavLink"] span,
        .st-key-aae-nav-{key} a[data-testid="stPageLink-NavLink"] [data-testid="stIconMaterial"] {{
            color: #FFFFFF !important;
            font-weight: 600;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_assessment_context(snapshot, *, notice: str | None = None) -> None:
    """Render the open assessment's context, or say that none is open."""

    st.markdown('<div class="aae-rule"></div>', unsafe_allow_html=True)
    if snapshot is not None:
        assessment = snapshot.assessment
        st.markdown(
            f'<div class="aae-context-title">{escape(assessment.title)}</div>'
            f'<div class="aae-context-id">{escape(assessment.assessment_id)}</div>',
            unsafe_allow_html=True,
        )
        render_mode_banner(assessment.execution_mode)
        render_progress(assessment.current_stage)
        return
    if notice:
        st.markdown(
            f'<div class="aae-context-empty">{escape(notice)}</div>',
            unsafe_allow_html=True,
        )
        return
    st.markdown(
        f'<div class="aae-context-empty">{escape(NO_ASSESSMENT_OPEN)}</div>',
        unsafe_allow_html=True,
    )


def render_sidebar(
    groups: Sequence[NavGroup],
    *,
    active_page=None,
    snapshot,
    notice: str | None = None,
) -> None:
    """Compose the whole sidebar in its approved order."""

    render_brand()
    render_nav(groups, active_page=active_page)
    render_assessment_context(snapshot, notice=notice)
