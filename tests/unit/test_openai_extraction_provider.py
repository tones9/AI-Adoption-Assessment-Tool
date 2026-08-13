from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Callable

import pytest

from ai_adoption_engine.extraction.chunking import plan_chunks
from ai_adoption_engine.extraction.configuration import load_extraction_configuration
from ai_adoption_engine.extraction.errors import (
    ExtractionProviderAuthenticationError,
    ExtractionProviderBadRequest,
    ExtractionProviderConnectionError,
    ExtractionProviderError,
    ExtractionProviderInvalidOutput,
    ExtractionProviderNotFound,
    ExtractionProviderPermissionDenied,
    ExtractionProviderRateLimit,
    ExtractionProviderRefusal,
    ExtractionProviderServerError,
    ExtractionProviderTimeout,
)
from ai_adoption_engine.extraction.providers.base import ExtractionRequest
from ai_adoption_engine.extraction.providers.openai import OpenAIExtractionProvider
from ai_adoption_engine.extraction.service import ProcessExtractionService
from ai_adoption_engine.ingestion.text import ingest_raw_text
from ai_adoption_engine.models.extraction import ExtractionStatus, RawChunkExtraction
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


def _structured_output_payload(output_text: str) -> dict:
    return {
        "id": "resp_mock",
        "object": "response",
        "created_at": 1.0,
        "status": "completed",
        "model": "gpt-5.6-terra",
        "output": [
            {
                "id": "msg_mock",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": output_text,
                        "annotations": [],
                    }
                ],
            }
        ],
        "parallel_tool_calls": False,
        "tool_choice": "auto",
        "tools": [],
    }


def _real_sdk_provider(
    handler: Callable[[object], object],
    *,
    strict_response_validation: bool = False,
) -> OpenAIExtractionProvider:
    httpx = pytest.importorskip("httpx")
    openai = pytest.importorskip("openai")
    transport = httpx.MockTransport(handler)
    client = openai.OpenAI(
        api_key="test-only-key",
        http_client=httpx.Client(transport=transport),
        _strict_response_validation=strict_response_validation,
    )
    return OpenAIExtractionProvider(
        load_extraction_configuration(CONFIG_PATH), client=client
    )


def _mock_http_response(request: object, payload: dict) -> object:
    httpx = pytest.importorskip("httpx")
    return httpx.Response(
        200,
        json=payload,
        headers={"x-request-id": "req_mock"},
        request=request,
    )


def _valid_structured_output() -> dict:
    extraction = raw_chunk(
        raw_step(
            local_step_id="one",
            activity="Record complaint",
            block_id="t-b0001",
            snippet="Agent records the complaint.",
        )
    )
    return extraction.model_dump(mode="json")


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


@pytest.mark.parametrize(
    ("mutate", "expected_code", "expected_category", "expected_field"),
    [
        (
            lambda value: value["process_name"].pop("rationale"),
            "field-required",
            "field-validation",
            "process_name.rationale",
        ),
        (
            lambda value: value["process_name"].update(
                {"knowledge_state": "unsupported-state"}
            ),
            "invalid-enum",
            "field-validation",
            "process_name.knowledge_state",
        ),
        (
            lambda value: value["steps"][0].update({"local_step_id": 7}),
            "incorrect-type",
            "field-validation",
            "steps[].local_step_id",
        ),
    ],
)
def test_real_sdk_parser_reports_sanitised_field_validation(
    mutate: Callable[[dict], object],
    expected_code: str,
    expected_category: str,
    expected_field: str,
) -> None:
    output = deepcopy(_valid_structured_output())
    mutate(output)

    def handler(request: object) -> object:
        return _mock_http_response(
            request, _structured_output_payload(json.dumps(output))
        )

    provider = _real_sdk_provider(handler)
    with pytest.raises(ExtractionProviderInvalidOutput) as exc_info:
        provider.extract_chunk(_request())

    error = exc_info.value
    feedback = error._sanitised_repair_feedback
    assert any(f"code={expected_code}" in item for item in feedback)
    assert any(f"category={expected_category}" in item for item in feedback)
    assert any(f"field={expected_field}" in item for item in feedback)
    assert "unsupported-state" not in str(feedback)
    assert "Agent records" not in str(feedback)
    assert error.request_id == "req_mock"
    assert error.__cause__ is None
    assert error.__context__ is None


def test_real_sdk_parser_reports_sanitised_semantic_validator_failure() -> None:
    output = deepcopy(_valid_structured_output())
    output["steps"][0]["activity"]["confidence"] = 0.91

    def handler(request: object) -> object:
        return _mock_http_response(
            request, _structured_output_payload(json.dumps(output))
        )

    provider = _real_sdk_provider(handler)
    with pytest.raises(ExtractionProviderInvalidOutput) as exc_info:
        provider.extract_chunk(_request())

    feedback = exc_info.value._sanitised_repair_feedback
    assert feedback == (
        "structured-output;code=known-confidence-forbidden;"
        "category=semantic-validation;validation_type=model-validator;"
        "field=steps[].activity;status=completed",
    )
    assert "0.91" not in str(feedback)
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_real_sdk_parser_reports_malformed_json_without_raw_output() -> None:
    malformed = '{"process_name":"sensitive-provider-value"'

    def handler(request: object) -> object:
        return _mock_http_response(
            request, _structured_output_payload(malformed)
        )

    provider = _real_sdk_provider(handler)
    with pytest.raises(ExtractionProviderInvalidOutput) as exc_info:
        provider.extract_chunk(_request())

    error = exc_info.value
    assert error._sanitised_repair_feedback == (
        "structured-output;code=malformed-json;category=malformed-json;"
        "validation_type=malformed-json;status=completed",
    )
    assert "sensitive-provider-value" not in str(error.__dict__)


def test_real_sdk_parser_detects_incomplete_truncated_response_before_parsing() -> None:
    payload = _structured_output_payload('{"process_name":')
    payload["status"] = "incomplete"
    payload["incomplete_details"] = {"reason": "max_output_tokens"}

    def handler(request: object) -> object:
        return _mock_http_response(request, payload)

    provider = _real_sdk_provider(handler)
    with pytest.raises(ExtractionProviderInvalidOutput) as exc_info:
        provider.extract_chunk(_request())

    error = exc_info.value
    assert error._sanitised_repair_feedback == (
        "structured-output;code=response-incomplete-max-output-tokens;"
        "category=incomplete-output;validation_type=incomplete;"
        "status=incomplete;incomplete_reason=max_output_tokens",
    )
    assert error.request_id == "req_mock"


def test_real_sdk_parser_detects_refusal_without_retaining_text() -> None:
    payload = _structured_output_payload("")
    payload["output"][0]["content"] = [
        {"type": "refusal", "refusal": "sensitive refusal explanation"}
    ]

    def handler(request: object) -> object:
        return _mock_http_response(request, payload)

    provider = _real_sdk_provider(handler)
    with pytest.raises(ExtractionProviderRefusal) as exc_info:
        provider.extract_chunk(_request())

    assert "sensitive refusal explanation" not in str(exc_info.value)
    assert exc_info.value.request_id == "req_mock"


def test_real_sdk_parser_classifies_other_sdk_response_validation() -> None:
    payload = _structured_output_payload(json.dumps(_valid_structured_output()))
    payload["output"] = ["unexpected-sdk-response-item"]

    def handler(request: object) -> object:
        return _mock_http_response(request, payload)

    provider = _real_sdk_provider(handler)
    with pytest.raises(ExtractionProviderInvalidOutput) as exc_info:
        provider.extract_chunk(_request())

    feedback = exc_info.value._sanitised_repair_feedback
    assert feedback == (
        "structured-output;code=sdk-response-parsing-failed;"
        "category=sdk-response-parsing;"
        "validation_type=parser;status=completed",
    )
    assert "unexpected-sdk-response-item" not in str(exc_info.value.__dict__)


def test_real_sdk_parser_classifies_sdk_response_model_validation() -> None:
    payload = _structured_output_payload(json.dumps(_valid_structured_output()))
    payload.pop("model")

    def handler(request: object) -> object:
        return _mock_http_response(request, payload)

    provider = _real_sdk_provider(handler, strict_response_validation=True)
    with pytest.raises(ExtractionProviderInvalidOutput) as exc_info:
        provider.extract_chunk(_request())

    feedback = exc_info.value._sanitised_repair_feedback
    assert feedback == (
        "structured-output;code=sdk-response-validation-failed;"
        "category=sdk-response-parsing;"
        "validation_type=sdk-response-validation;status=completed",
    )


def test_real_sdk_parser_feedback_guides_only_the_existing_single_repair() -> None:
    ingestion = ingest_raw_text("Agent records the complaint.")
    assert ingestion.document is not None
    invalid = deepcopy(_valid_structured_output())
    invalid["steps"][0]["activity"]["confidence"] = 0.73
    valid = _valid_structured_output()
    request_bodies: list[dict] = []

    def handler(request: object) -> object:
        request_bodies.append(json.loads(request.content))
        output = invalid if len(request_bodies) == 1 else valid
        return _mock_http_response(
            request, _structured_output_payload(json.dumps(output))
        )

    provider = _real_sdk_provider(handler)
    result = ProcessExtractionService(provider).extract(ingestion.document)

    assert result.status is ExtractionStatus.SUCCESS
    assert len(request_bodies) == 2
    repair_prompt = request_bodies[1]["input"][1]["content"]
    assert "code=known-confidence-forbidden" in repair_prompt
    assert "category=semantic-validation" in repair_prompt
    assert "field=steps[].activity" in repair_prompt
    assert "0.73" not in repair_prompt


def test_failed_repair_surfaces_only_sanitised_diagnostic_metadata() -> None:
    ingestion = ingest_raw_text("Agent records the complaint.")
    assert ingestion.document is not None
    invalid = deepcopy(_valid_structured_output())
    invalid["steps"][0]["activity"]["confidence"] = 0.62
    calls = 0

    def handler(request: object) -> object:
        nonlocal calls
        calls += 1
        return _mock_http_response(
            request, _structured_output_payload(json.dumps(invalid))
        )

    provider = _real_sdk_provider(handler)
    result = ProcessExtractionService(provider).extract(ingestion.document)

    assert result.status is ExtractionStatus.FAILED
    assert calls == 2
    issue = result.issues[0]
    assert issue.code == "provider-invalid-structured-output"
    assert issue.field_path == "steps[].activity"
    assert "code=known-confidence-forbidden" in issue.message
    assert "category=semantic-validation" in issue.message
    assert "0.62" not in issue.message
    assert "Agent records" not in issue.message
