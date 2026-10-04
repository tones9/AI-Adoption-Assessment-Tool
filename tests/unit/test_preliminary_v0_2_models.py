import pytest
from pydantic import ValidationError

from ai_adoption_engine.models.preliminary_assessment_v0_2 import MatchedSubSpan, SourceSpan


def _span():
    return SourceSpan(
        source_document_id="doc-1",
        approved_review_artifact_id="review-1",
        approved_evidence_item_id="evidence-1",
        source_block_id="block-1",
        document_start=10,
        document_end=17,
        block_start=2,
        block_end=9,
        exact_text="records",
        source_locator="line 1",
        fact_or_reviewed_inference_id="fact-1",
    )


def test_source_span_and_subspan_contracts_validate_exact_ranges() -> None:
    span = _span()
    match = MatchedSubSpan(
        parent_source_span_signature=span.signature(),
        match_start_in_span=0,
        match_end_in_span=7,
        exact_matched_text="records",
        normalized_matched_key="records",
        matched_literal_code="PD2-001-L001",
    )
    assert match.exact_matched_text == span.exact_text


@pytest.mark.parametrize("field,value", [("document_end", 18), ("block_end", 10), ("exact_text", "altered text")])
def test_invalid_source_span_length_is_rejected(field, value) -> None:
    data = _span().model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        SourceSpan.model_validate(data)


def test_subspan_length_mismatch_is_rejected() -> None:
    with pytest.raises(ValidationError):
        MatchedSubSpan(
            parent_source_span_signature=_span().signature(),
            match_start_in_span=0,
            match_end_in_span=6,
            exact_matched_text="records",
            normalized_matched_key="records",
            matched_literal_code="PD2-001-L001",
        )
