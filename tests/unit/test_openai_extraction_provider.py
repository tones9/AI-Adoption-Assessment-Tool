from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_adoption_engine.extraction.chunking import plan_chunks
from ai_adoption_engine.extraction.configuration import load_extraction_configuration
from ai_adoption_engine.extraction.errors import (
    ExtractionProviderConfigurationError,
    ExtractionProviderRefusal,
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


def test_openai_adapter_sanitises_timeout_and_authentication_errors() -> None:
    Timeout = type("APITimeoutError", (Exception,), {})
    timeout_provider = OpenAIExtractionProvider(
        load_extraction_configuration(CONFIG_PATH), client=FakeClient(Timeout("secret"))
    )
    with pytest.raises(ExtractionProviderTimeout) as exc_info:
        timeout_provider.extract_chunk(_request())
    assert "secret" not in str(exc_info.value)

    Auth = type("AuthenticationError", (Exception,), {})
    auth_provider = OpenAIExtractionProvider(
        load_extraction_configuration(CONFIG_PATH), client=FakeClient(Auth("key-value"))
    )
    with pytest.raises(ExtractionProviderConfigurationError) as exc_info:
        auth_provider.extract_chunk(_request())
    assert "key-value" not in str(exc_info.value)


def test_provider_output_schema_contains_no_trusted_offsets() -> None:
    schema_text = str(RawChunkExtraction.model_json_schema())
    assert "block_start_offset" not in schema_text
    assert "document_start_offset" not in schema_text
