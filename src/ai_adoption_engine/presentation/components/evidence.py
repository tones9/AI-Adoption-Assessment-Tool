"""Literal evidence and provenance display."""

from __future__ import annotations

import streamlit as st

from ai_adoption_engine.models.review import ReviewedAssertion


_ORIGIN_LABELS = {
    "DOCUMENT_SUPPORTED": "Document supported",
    "MODEL_INFERRED": "Model inferred",
    "HUMAN_SUPPLIED": "Human supplied",
    "UNKNOWN": "Unknown",
}


def origin_label(origin) -> str:
    return _ORIGIN_LABELS.get(getattr(origin, "value", str(origin)), str(origin))


def render_reviewed_assertion(assertion: ReviewedAssertion, *, label: str) -> None:
    st.markdown(f"**{label}**")
    if assertion.value is None:
        st.caption("Value: Unknown")
    else:
        st.write(assertion.value)
    details = [
        origin_label(assertion.origin),
        f"Knowledge: {assertion.knowledge_state.value}",
        f"Review: {assertion.disposition.value}",
    ]
    if assertion.confidence is not None:
        details.append(f"Extraction confidence: {assertion.confidence:.2f}")
    st.caption(" · ".join(details))
    st.caption(assertion.rationale)
    if assertion.evidence:
        with st.expander(f"Supporting evidence ({len(assertion.evidence)})"):
            for index, item in enumerate(assertion.evidence, start=1):
                st.caption(f"{index}. {item.source_locator}")
                st.code(item.exact_snippet, language=None, wrap_lines=True)
                st.caption(
                    f"Document {item.document_id} · Block {item.block_id} · "
                    f"Offsets {item.block_start_offset}:{item.block_end_offset}"
                )
    elif assertion.origin.value == "HUMAN_SUPPLIED":
        st.caption("Human-supplied information — no document evidence claimed.")

