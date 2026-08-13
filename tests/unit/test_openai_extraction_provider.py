from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_adoption_engine.extraction.chunking import plan_chunks
from ai_adoption_engine.extraction.configuration import load_extraction_configuration
from ai_adoption_engine.extraction.errors import (
    ExtractionProviderAuthenticationError,
    ExtractionProviderBadRequest,
    ExtractionProviderConnectionError,
    ExtractionProviderError,
    ExtractionProviderNotFound,
    ExtractionProviderPermissionDenied,
    ExtractionProviderRateLimit,
    ExtractionProviderRefusal,
    ExtractionProviderServerError,
    ExtractionProviderTimeout,
)
from ai_adoption_engine.extraction.providers.base import ExtractionRequest
from ai_adoption_engine.extraction.providers.openai import OpenAIExtractionProvider
from ai_adoption_engine.ingestion.text import ingest_raw_text
from ai_adoption_engine.models.extraction import RawChunkExtraction
from tests.fakes.extraction_provider import raw_chunk, raw_step


CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "extraction.v0.1.json"


class FakeResponses:
    def __init__(self, response: object | Exception) -> None:
        self.response = response
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class FakeClient:
    def __init__(self, response: object | Exception) -> None:
        self.responses = FakeResponses(response)


def _request() -> ExtractionRequest:
    ingestion = ingest_raw_text("Agent records the complaint.")
    assert ingestion.document is not None
    return ExtractionRequest(
        document_id=ingestion.document.document_id,
        chunk=plan_chunks(ingestion.document)[0],
        schema_version="candidate-process.v0.1",
        prompt_version="process-extraction.v0.1",
    )


def test_openai_adapter_uses_responses_structured_output_without_tools() -> None:
    extraction = raw_chunk(
        raw_step(
            local_step_id="one",
            activity="Record complaint",
            block_id="t-b0001",
            snippet="Agent records the complaint.",
        )
    )
    response = SimpleNamespace(
        output_parsed=extraction,
        output=[],
        id="resp-test",
        model="gpt-5.6-terra",
        usage=SimpleNamespace(input_tokens=120, output_tokens=80),
    )
    client = FakeClient(response)
    provider = OpenAIExtractionProvider(
        load_extraction_configuration(CONFIG_PATH), client=client
    )
    result = provider.extract_chunk(_request())

    call = client.responses.calls[0]
    assert call["model"] == "gpt-5.6-terra"
    assert call["reasoning"] == {"effort": "medium"}
    assert call["text_format"] is RawChunkExtraction
    assert call["tools"] == []
    assert call["stream"] is False
    assert call["store"] is False
    assert result.invocation.request_id == "resp-test"
    assert result.invocation.usage.input_tokens == 120


def test_openai_adapter_maps_refusal_without_leaking_refusal_text() -> None:
    response = SimpleNamespace(
        output_parsed=None,
        output=[SimpleNamespace(content=[SimpleNamespace(refusal="sensitive detail")])],
    )
    provider = OpenAIExtractionProvider(
        load_extraction_configuration(CONFIG_PATH), client=FakeClient(response)
    )
    with pytest.raises(ExtractionProviderRefusal) as exc_info:
        provider.extract_chunk(_request())
    assert "sensitive detail" not in str(exc_info.value)


def _sdk_error(
    name: str,
    *,
    status_code: int | None,
    request_id: str | None,
    retry_count: int,
) -> Exception:
    error_type = type(name, (Exception,), {})
    error = error_type("secret response body and credential material")
    error.status_code = status_code
    error.request_id = request_id
    error.request = SimpleNamespace(
        headers={"x-stainless-retry-count": str(retry_count)}
    )
    return error


@pytest.mark.parametrize(
    (
        "sdk_name",
        "status_code",
        "request_id",
        "retry_count",
        "expected_type",
        "expected_category",
        "expected_exhausted",
    ),
    [
        (
            "BadRequestError",
            400,
            "req_bad_request",
            0,
            ExtractionProviderBadRequest,
            "bad-request",
            False,
        ),
        (
            "AuthenticationError",
            401,
            "req_authentication",
            0,
            ExtractionProviderAuthenticationError,
            "authentication",
            False,
        ),
        (
            "PermissionDeniedError",
            403,
            "req_permission",
            0,
            ExtractionProviderPermissionDenied,
            "permission-denied",
            False,
        ),
        (
            "NotFoundError",
            404,
            "req_not_found",
            0,
            ExtractionProviderNotFound,
            "model-or-resource-not-found",
            False,
        ),
        (
            "RateLimitError",
            429,
            "req_rate_limit",
            2,
            ExtractionProviderRateLimit,
            "rate-limit-or-quota",
            True,
        ),
        (
            "APIConnectionError",
            None,
            None,
            2,
            ExtractionProviderConnectionError,
            "connection",
            True,
        ),
        (
            "APITimeoutError",
            None,
            None,
            2,
            ExtractionProviderTimeout,
            "timeout",
            True,
        ),
        (
            "InternalServerError",
            500,
            "req_server_error",
            2,
            ExtractionProviderServerError,
            "server-error",
            True,
        ),
        (
            "APIStatusError",
            422,
            "req_status_error",
            0,
            ExtractionProviderError,
            "provider-error",
            False,
        ),
    ],
)
def test_openai_adapter_classifies_sdk_errors_without_leaking_details(
    sdk_name: str,
    status_code: int | None,
    request_id: str | None,
    retry_count: int,
    expected_type: type[ExtractionProviderError],
    expected_category: str,
    expected_exhausted: bool,
) -> None:
    provider = OpenAIExtractionProvider(
        load_extraction_configuration(CONFIG_PATH),
        client=FakeClient(
            _sdk_error(
                sdk_name,
                status_code=status_code,
                request_id=request_id,
                retry_count=retry_count,
            )
        ),
    )
    with pytest.raises(expected_type) as exc_info:
        provider.extract_chunk(_request())

    error = exc_info.value
    assert "secret" not in str(error)
    assert error.category.value == expected_category
    assert error.http_status_code == status_code
    assert error.request_id == request_id
    assert error.provider_name == "openai"
    assert error.requested_model == "gpt-5.6-terra"
    assert error.sdk_retries_exhausted is expected_exhausted


def test_openai_adapter_discards_unsafe_request_id() -> None:
    provider = OpenAIExtractionProvider(
        load_extraction_configuration(CONFIG_PATH),
        client=FakeClient(
            _sdk_error(
                "BadRequestError",
                status_code=400,
                request_id="unsafe request id\nsecret-header: value",
                retry_count=0,
            )
        ),
    )
    with pytest.raises(ExtractionProviderBadRequest) as exc_info:
        provider.extract_chunk(_request())
    assert exc_info.value.request_id is None


def test_provider_output_schema_contains_no_trusted_offsets() -> None:
    schema_text = str(RawChunkExtraction.model_json_schema())
    assert "block_start_offset" not in schema_text
    assert "document_start_offset" not in schema_text
