"""OpenAI Responses API adapter for strict Phase 3 extraction."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ai_adoption_engine.extraction.configuration import (
    ExtractionConfiguration,
    load_extraction_configuration,
)
from ai_adoption_engine.extraction.errors import (
    ExtractionProviderConfigurationError,
    ExtractionProviderError,
    ExtractionProviderInvalidOutput,
    ExtractionProviderRefusal,
    ExtractionProviderTimeout,
)
from ai_adoption_engine.extraction.prompting import (
    SYSTEM_PROMPT,
    build_extraction_prompt,
)
from ai_adoption_engine.extraction.providers.base import (
    ExtractionRequest,
    ProviderExtractionResponse,
)
from ai_adoption_engine.models.extraction import (
    ProviderInvocation,
    ProviderUsage,
    RawChunkExtraction,
)


class OpenAIExtractionProvider:
    """Provider adapter; no OpenAI SDK objects escape this class."""

    def __init__(
        self,
        configuration: ExtractionConfiguration,
        *,
        client: Any | None = None,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        if configuration.provider != "openai":
            raise ValueError("OpenAI adapter requires provider='openai'")
        self.configuration = configuration
        self._client = client or self._build_client(client_factory)

    def _build_client(self, client_factory: Callable[..., Any] | None) -> Any:
        if client_factory is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise ExtractionProviderConfigurationError(
                    "The optional OpenAI provider dependency is not installed."
                ) from exc
            client_factory = OpenAI
        try:
            return client_factory(
                timeout=self.configuration.timeout_seconds,
                max_retries=self.configuration.sdk_max_retries,
            )
        except Exception as exc:
            raise ExtractionProviderConfigurationError(
                "The OpenAI client could not be configured."
            ) from exc

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self.configuration.model

    @staticmethod
    def _refusal_text(response: Any) -> str | None:
        for output in getattr(response, "output", []) or []:
            for content in getattr(output, "content", []) or []:
                refusal = getattr(content, "refusal", None)
                if refusal:
                    return str(refusal)
        return None

    @staticmethod
    def _sanitised_error(exc: Exception) -> ExtractionProviderError:
        name = type(exc).__name__
        status_code = getattr(exc, "status_code", None)
        if name in {"APITimeoutError", "TimeoutError"}:
            return ExtractionProviderTimeout("The OpenAI request timed out.")
        if name in {
            "AuthenticationError",
            "PermissionDeniedError",
            "NotFoundError",
        } or status_code in {401, 403, 404}:
            return ExtractionProviderConfigurationError(
                "OpenAI credentials, project access, or model access are invalid."
            )
        if name in {
            "ValidationError",
            "APIResponseValidationError",
            "LengthFinishReasonError",
        }:
            return ExtractionProviderInvalidOutput(
                "OpenAI returned invalid or incomplete structured output."
            )
        return ExtractionProviderError("The OpenAI extraction request failed.")

    def extract_chunk(self, request: ExtractionRequest) -> ProviderExtractionResponse:
        try:
            response = self._client.responses.parse(
                model=self.configuration.model,
                reasoning={"effort": self.configuration.reasoning_effort},
                input=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_extraction_prompt(request)},
                ],
                text_format=RawChunkExtraction,
                tools=[],
                stream=False,
                store=self.configuration.store_responses,
                max_output_tokens=self.configuration.max_output_tokens,
            )
        except Exception as exc:
            raise self._sanitised_error(exc) from exc

        refusal = self._refusal_text(response)
        if refusal is not None:
            raise ExtractionProviderRefusal(
                "The OpenAI model refused the extraction request."
            )
        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise ExtractionProviderInvalidOutput(
                "OpenAI returned no schema-valid extraction output."
            )
        try:
            extraction = (
                parsed
                if isinstance(parsed, RawChunkExtraction)
                else RawChunkExtraction.model_validate(parsed)
            )
        except Exception as exc:
            raise ExtractionProviderInvalidOutput(
                "OpenAI returned semantically invalid structured output."
            ) from exc
        usage = getattr(response, "usage", None)
        return ProviderExtractionResponse(
            extraction=extraction,
            invocation=ProviderInvocation(
                provider_name=self.provider_name,
                requested_model=self.configuration.model,
                effective_model=getattr(response, "model", None),
                request_id=getattr(response, "id", None),
                chunk_id=request.chunk.chunk_id,
                attempt=request.attempt,
                usage=ProviderUsage(
                    input_tokens=getattr(usage, "input_tokens", None),
                    output_tokens=getattr(usage, "output_tokens", None),
                ),
            ),
        )


def build_openai_extraction_service(
    configuration_path: str | Path,
    *,
    client: Any | None = None,
    client_factory: Callable[..., Any] | None = None,
) -> Any:
    """Compose configured OpenAI infrastructure with the provider-neutral service."""

    from ai_adoption_engine.extraction.service import ProcessExtractionService

    configuration = load_extraction_configuration(configuration_path)
    provider = OpenAIExtractionProvider(
        configuration,
        client=client,
        client_factory=client_factory,
    )
    return ProcessExtractionService(
        provider,
        chunking=configuration.chunking_config(),
        schema_version=configuration.schema_version,
        prompt_version=configuration.prompt_version,
        repair_attempts=configuration.repair_attempts,
    )
