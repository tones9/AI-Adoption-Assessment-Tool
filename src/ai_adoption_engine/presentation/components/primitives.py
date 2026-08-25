"""Shared presentation primitives for the assessment UI.

These are the small, repeatable pieces of visual grammar the product needs in
more than one place: a status badge, a business list, an evidence block, a
guard/empty-state panel and the wrapper that demotes a destructive action.

Every helper here is presentation-only.  None of them imports a decision,
policy, scoring or workspace module, none decides what a status *means*, and
none rewrites the text it is given.  Callers pass finished strings; these
helpers only decide how those strings look.

Any caller-supplied text is HTML-escaped before it reaches the page: evidence
snippets are verbatim document content and must never be interpreted as markup.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from html import escape

import streamlit as st


#: The two badge tones the design system allows.  ``primary`` groups states
#: where a path exists, ``muted`` groups states where one does not yet exist.
#: There is deliberately no good/bad (green/amber/red) scale.
BADGE_TONES = ("primary", "muted")


def render_badge(label: str, *, tone: str = "muted") -> None:
    """Render one status badge as a square outline pill."""

    st.markdown(badge_html(label, tone=tone), unsafe_allow_html=True)


def badge_html(label: str, *, tone: str = "muted") -> str:
    """Return the badge markup, for callers composing a row of badges."""

    modifier = "" if tone == "primary" else " aae-badge--muted"
    return f'<span class="aae-badge{modifier}">{escape(str(label))}</span>'


def render_badges(labels: Sequence[tuple[str, str]]) -> None:
    """Render several badges on one line as ``(label, tone)`` pairs."""

    if not labels:
        return
    st.markdown(
        "".join(badge_html(label, tone=tone) for label, tone in labels),
        unsafe_allow_html=True,
    )


def render_business_list(
    items: Iterable[str],
    *,
    eyebrow: str | None = None,
    boxed: bool = True,
) -> None:
    """Render a list as one compact block instead of one paragraph per item."""

    entries = [str(item) for item in items if str(item).strip()]
    if not entries:
        return
    body = "".join(f"<li>{escape(entry)}</li>" for entry in entries)
    label = (
        f'<span class="aae-page-eyebrow">{escape(eyebrow)}</span>' if eyebrow else ""
    )
    opening = '<div class="aae-list-card">' if boxed else "<div>"
    st.markdown(
        f'{opening}{label}<ul class="aae-list">{body}</ul></div>',
        unsafe_allow_html=True,
    )


def render_evidence_block(snippet: str, *, locator: str | None = None) -> None:
    """Render one exact quotation with its locator kept visually subordinate.

    The snippet is rendered verbatim and wraps naturally; it is never
    truncated, re-flowed destructively or paraphrased.
    """

    block = f'<div class="aae-evidence">{escape(str(snippet))}</div>'
    tail = (
        f'<p class="aae-locator">{escape(str(locator))}</p>' if locator else ""
    )
    st.markdown(block + tail, unsafe_allow_html=True)


def render_guard_state(message: str, *, icon: str = "ℹ️") -> None:
    """Render the shared guard / empty-state panel.

    The message and the condition that produced it are unchanged; only its
    presentation is shared.  No action is invented here - a guard that has no
    existing next step shows none.
    """

    with st.container(key="aae-guard-panel"):
        st.info(message, icon=icon)


def destructive_action(key: str):
    """Return a container that demotes the destructive control inside it.

    Weight and position carry the distinction, not an alarm colour.
    """

    return st.container(key=f"aae-destructive-{key}")
