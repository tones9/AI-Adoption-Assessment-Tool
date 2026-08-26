"""Literal evidence and provenance display."""

from __future__ import annotations

import streamlit as st

from ai_adoption_engine.models.review import ReviewedAssertion
from ai_adoption_engine.presentation.components.primitives import (
    render_badges,
    render_evidence_block,
)


_ORIGIN_LABELS = {
    "DOCUMENT_SUPPORTED": "Document supported",
    "MODEL_INFERRED": "Model inferred",
    "HUMAN_SUPPLIED": "Human supplied",
    "UNKNOWN": "Unknown",
}

_DISPOSITION_LABELS = {
    "unreviewed": "Unreviewed",
    "accepted": "Accepted",
    "corrected": "Corrected",
    "rejected": "Rejected",
    "unknown-retained": "Unknown retained",
}

def origin_label(origin) -> str:
    return _ORIGIN_LABELS.get(getattr(origin, "value", str(origin)), str(origin))


def render_reviewed_assertion(assertion: ReviewedAssertion, *, label: str) -> None:
    st.markdown(f"**{label}**")
    if assertion.value is None:
        st.caption("Value: Unknown")
    else:
        st.write(assertion.value)
    disposition = assertion.disposition.value
    disposition_label = _DISPOSITION_LABELS.get(disposition, disposition)
    render_badges(
        [
            (origin_label(assertion.origin), "muted"),
            (
                disposition_label,
                "primary" if disposition in {"accepted", "corrected"} else "muted",
            ),
        ]
    )
    details = [f"Knowledge: {assertion.knowledge_state.value}"]
    if assertion.confidence is not None:
        details.append(f"Extraction confidence: {assertion.confidence:.2f}")
    st.caption(" · ".join(details))
    st.caption(assertion.rationale)
    if assertion.evidence:
        with st.expander(f"Supporting evidence ({len(assertion.evidence)})"):
            for item in assertion.evidence:
                render_evidence_block(
                    item.exact_snippet,
                    locator=(
                        f"{item.source_locator} · Document {item.document_id} · "
                        f"Block {item.block_id} · Offsets "
                        f"{item.block_start_offset}:{item.block_end_offset}"
                    ),
                )
    elif assertion.origin.value == "HUMAN_SUPPLIED":
        st.caption("Human-supplied information — no document evidence claimed.")
