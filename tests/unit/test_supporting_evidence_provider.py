from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from ai_adoption_engine.extraction.chunking import plan_chunks
from ai_adoption_engine.extraction.errors import (
    ExtractionProviderAuthenticationError,
    ExtractionProviderConfigurationError,
    ExtractionProviderInvalidOutput,
    ExtractionProviderRateLimit,
    ExtractionProviderRefusal,
    ExtractionProviderServerError,
    ExtractionProviderTimeout,
)
from ai_adoption_engine.ingestion.text import ingest_raw_text
from ai_adoption_engine.models.formal_evidence import (
    DocumentCategory,
    EvidenceClassification,
)
from ai_adoption_engine.supporting_evidence.openai import (
    OpenAISupportingEvidenceProvider,
    build_supporting_evidence_prompt,
    load_supporting_evidence_openai_configuration,
)
from ai_adoption_engine.supporting_evidence.provider import (
    SUPPORTING_EVIDENCE_PROMPT_ID,
    SUPPORTING_EVIDENCE_PROVIDER_SCHEMA,
    ApprovedActivity,
    RawSupportingCitation,
    RawSupportingEvidenceBatch,
    RawSupportingEvidenceItem,
    SupportingEvidenceProviderRequest,
    raw_schema_forbids_formal_values,
)


ROOT = Path(__file__).parents[2]


def _request() -> SupportingEvidenceProviderRequest:
    result = ingest_raw_text("Monthly volume is 100.")
    assert result.document is not None
    return SupportingEvidenceProviderRequest(
        document_id="supporting-document-1",
        document_content_sha256="a" * 64,
        chunk=plan_chunks(result.document)[0],
        approved_activities=(ApprovedActivity("step-1", "Record complaint"),),
    )


def _batch() -> RawSupportingEvidenceBatch:
    return RawSupportingEvidenceBatch(
        schema_version=SUPPORTING_EVIDENCE_PROVIDER_SCHEMA,
        items=(
            RawSupportingEvidenceItem(
                proposed_claim="Monthly volume is 100.",
                proposed_classification=EvidenceClassification.DOCUMENTED_FACT,
                primary_citation=RawSupportingCitation(
                    document_id="supporting-document-1",
                    block_id="t-b0001",
                    exact_excerpt="Monthly volume is 100.",
                ),
                proposed_category=DocumentCategory.PROCESS_VOLUMES_AND_FREQUENCY,
                suggested_activity_ids=("step-1",),
                ambiguity_indicated=False,
                conflict_indicated=False,
                relevance_explanation="May inform review.",
            ),
        ),
    )


class FakeResponses:
    def __init__(self, response=None, failure: Exception | None = None) -> None:
        self.response = response
        self.failure = failure
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self.failure is not None:
            raise self.failure
        return self.response


def _provider(responses: FakeResponses) -> OpenAISupportingEvidenceProvider:
    configuration = load_supporting_evidence_openai_configuration(
        ROOT / "config" / "supporting_evidence_extraction.v0.1.json"
    )
    return OpenAISupportingEvidenceProvider(
        configuration,
        client=SimpleNamespace(responses=responses),
    )


def test_closed_schema_forbids_unknown_and_formal_value_fields() -> None:
    assert raw_schema_forbids_formal_values()
    payload = _batch().model_dump(mode="json")
    payload["items"][0]["formal_value"] = 5
    with pytest.raises(ValidationError):
        RawSupportingEvidenceBatch.model_validate(payload)


def test_prompt_uses_dedicated_identity_and_untrusted_bounded_blocks() -> None:
    prompt = build_supporting_evidence_prompt(_request())
    assert SUPPORTING_EVIDENCE_PROMPT_ID in prompt
    assert 'block_id="t-b0001"' in prompt
    assert "step-1: Record complaint" in prompt
    assert "formal value" not in prompt.lower()


def test_openai_adapter_is_separate_closed_and_returns_valid_schema() -> None:
    responses = FakeResponses(SimpleNamespace(output=[], output_parsed=_batch()))
    provider = _provider(responses)
    assert provider.extract(_request()) == _batch()
    call = responses.calls[0]
    assert call["text_format"] is RawSupportingEvidenceBatch
    assert call["tools"] == []
    assert call["stream"] is False
    assert call["store"] is False
    assert provider.extractor_identity.output_schema_id == SUPPORTING_EVIDENCE_PROVIDER_SCHEMA


def test_openai_adapter_maps_auth_refusal_and_malformed_output_safely() -> None:
    AuthenticationError = type("AuthenticationError", (Exception,), {})
    with pytest.raises(ExtractionProviderAuthenticationError):
        _provider(FakeResponses(failure=AuthenticationError("secret"))).extract(_request())

    refusal = SimpleNamespace(
        output=[SimpleNamespace(content=[SimpleNamespace(refusal="sensitive refusal")])],
        output_parsed=None,
    )
    with pytest.raises(ExtractionProviderRefusal) as refused:
        _provider(FakeResponses(refusal)).extract(_request())
    assert "sensitive" not in str(refused.value)

    malformed = SimpleNamespace(output=[], output_parsed={"schema_version": "wrong"})
    with pytest.raises(ExtractionProviderInvalidOutput):
        _provider(FakeResponses(malformed)).extract(_request())


@pytest.mark.parametrize(
    ("error_name", "status", "expected"),
    [
        ("APITimeoutError", None, ExtractionProviderTimeout),
        ("RateLimitError", 429, ExtractionProviderRateLimit),
        ("InternalServerError", 503, ExtractionProviderServerError),
    ],
)
def test_openai_adapter_maps_provider_failures_without_raw_details(
    error_name: str, status: int | None, expected: type[Exception]
) -> None:
    error_type = type(error_name, (Exception,), {})
    error = error_type("secret provider body")
    error.status_code = status
    with pytest.raises(expected) as failure:
        _provider(FakeResponses(failure=error)).extract(_request())
    assert "secret" not in str(failure.value)


def test_openai_adapter_defers_and_safely_maps_client_construction_failure() -> None:
    configuration = load_supporting_evidence_openai_configuration(
        ROOT / "config" / "supporting_evidence_extraction.v0.1.json"
    )

    def fail_client(**kwargs):
        raise RuntimeError("secret configuration detail")

    provider = OpenAISupportingEvidenceProvider(
        configuration,
        client_factory=fail_client,
    )
    assert provider.extractor_identity.provider_id == "openai"
    with pytest.raises(ExtractionProviderConfigurationError) as failure:
        provider.extract(_request())
    assert "secret" not in str(failure.value)
