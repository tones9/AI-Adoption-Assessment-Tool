"""OpenAI Responses API adapter for strict Phase 3 extraction."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Callable

from ai_adoption_engine.extraction.configuration import (
    ExtractionConfiguration,
    load_extraction_configuration,
)
from ai_adoption_engine.extraction.errors import (
    ExtractionProviderAuthenticationError,
    ExtractionProviderBadRequest,
    ExtractionProviderConnectionError,
    ExtractionProviderConfigurationError,
    ExtractionProviderError,
    ExtractionProviderInvalidOutput,
    ExtractionProviderNotFound,
    ExtractionProviderPermissionDenied,
    ExtractionProviderRateLimit,
    ExtractionProviderRefusal,
    ExtractionProviderServerError,
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
    def _safe_status_code(exc: Exception) -> int | None:
        value = getattr(exc, "status_code", None)
        return value if isinstance(value, int) and 100 <= value <= 599 else None

    @staticmethod
    def _safe_request_id(exc: Exception) -> str | None:
        value = getattr(exc, "request_id", None)
        if not isinstance(value, str):
            return None
        if not re.fullmatch(r"[A-Za-z0-9._:-]{1,200}", value):
            return None
        return value

    def _sdk_retries_exhausted(self, exc: Exception) -> bool | None:
        request = getattr(exc, "request", None)
        headers = getattr(request, "headers", None)
        if headers is None:
            return None
        try:
            retries_taken = int(headers.get("x-stainless-retry-count"))
        except (TypeError, ValueError):
            return None
        return retries_taken >= self.configuration.sdk_max_retries

    def _sanitised_error(self, exc: Exception) -> ExtractionProviderError:
        name = type(exc).__name__
        status_code = self._safe_status_code(exc)
        details = {
            "provider_name": self.provider_name,
            "requested_model": self.model_name,
            "http_status_code": status_code,
            "request_id": self._safe_request_id(exc),
            "sdk_retries_exhausted": self._sdk_retries_exhausted(exc),
        }
        if name in {"APITimeoutError", "TimeoutError"}:
            return ExtractionProviderTimeout(
                "The OpenAI request timed out.", **details
            )
        if name == "BadRequestError" or status_code == 400:
            return ExtractionProviderBadRequest(
                "OpenAI rejected the configured request.", **details
            )
        if name == "AuthenticationError" or status_code == 401:
            return ExtractionProviderAuthenticationError(
                "OpenAI authentication failed.", **details
            )
        if name == "PermissionDeniedError" or status_code == 403:
            return ExtractionProviderPermissionDenied(
                "OpenAI denied access to the requested operation.", **details
            )
        if name == "NotFoundError" or status_code == 404:
            return ExtractionProviderNotFound(
                "The requested OpenAI model or resource was not found.", **details
            )
        if name == "RateLimitError" or status_code == 429:
            return ExtractionProviderRateLimit(
                "OpenAI rate or quota limits prevented the request.", **details
            )
        if name == "APIConnectionError":
            return ExtractionProviderConnectionError(
                "The OpenAI service could not be reached.", **details
            )
        if name == "InternalServerError" or (
            status_code is not None and status_code >= 500
        ):
            return ExtractionProviderServerError(
                "OpenAI returned a server error.", **details
            )
        if name in {
            "ValidationError",
            "APIResponseValidationError",
            "LengthFinishReasonError",
        }:
            return ExtractionProviderInvalidOutput(
                "OpenAI returned invalid or incomplete structured output.",
                **details,
            )
        return ExtractionProviderError(
            "The OpenAI extraction request failed.", **details
        )

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
