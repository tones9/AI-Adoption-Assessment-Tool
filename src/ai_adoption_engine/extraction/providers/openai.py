"""OpenAI Responses API adapter for strict Phase 3 extraction."""

from __future__ import annotations

from dataclasses import dataclass
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


_SAFE_RESPONSE_STATUSES = {
    "cancelled",
    "completed",
    "failed",
    "in_progress",
    "incomplete",
    "queued",
}
_SAFE_INCOMPLETE_REASONS = {"content_filter", "max_output_tokens"}
_SAFE_SCHEMA_FIELDS = frozenset(
    {
        property_name
        for schema in (
            RawChunkExtraction.model_json_schema(),
        )
        for definition in [schema, *schema.get("$defs", {}).values()]
        for property_name in definition.get("properties", {})
    }
)
_SEMANTIC_INVARIANT_CODES = {
    "Use occurrence or slice_id, not both": "evidence-disambiguator-exclusive",
    "Unknown assertions must use a null value": "unknown-value-must-be-null",
    "Unknown assertions cannot claim evidence": "unknown-evidence-forbidden",
    "Unknown assertions cannot carry confidence": "unknown-confidence-forbidden",
    "Known or inferred assertions require a value": "resolved-value-required",
    "Known or inferred assertions require evidence pointers": "resolved-evidence-required",
    "Inferred assertions require extraction confidence": "inferred-confidence-required",
    "Known assertions do not use model confidence": "known-confidence-forbidden",
    "An unknown collection cannot contain assertions or evidence": (
        "unknown-collection-must-be-empty"
    ),
    "A supported empty collection requires an evidence pointer": (
        "supported-empty-collection-evidence-required"
    ),
    "Raw candidate criterion names must be unique": "criterion-names-unique",
    "Every raw candidate criterion must be represented": "criterion-set-complete",
    "Raw capability signal names must be unique": "capability-signal-names-unique",
    "Every raw capability signal must be represented": (
        "capability-signal-set-complete"
    ),
    "A raw candidate step requires a supported activity": (
        "supported-activity-required"
    ),
}


@dataclass(frozen=True)
class _SafeResponseMetadata:
    status: str | None = None
    incomplete_reason: str | None = None
    refusal_present: bool = False
    request_id: str | None = None


@dataclass(frozen=True)
class _SafeStructuredOutputDiagnostic:
    code: str
    category: str
    validation_type: str
    field_path: str | None = None
    response_status: str | None = None
    incomplete_reason: str | None = None

    def repair_feedback(self) -> str:
        parts = [
            "structured-output",
            f"code={self.code}",
            f"category={self.category}",
            f"validation_type={self.validation_type}",
        ]
        if self.field_path:
            parts.append(f"field={self.field_path}")
        if self.response_status:
            parts.append(f"status={self.response_status}")
        if self.incomplete_reason:
            parts.append(f"incomplete_reason={self.incomplete_reason}")
        return ";".join(parts)

    def summary(self) -> str:
        parts = [
            f"code={self.code}",
            f"category={self.category}",
            f"validation_type={self.validation_type}",
        ]
        if self.field_path:
            parts.append(f"field={self.field_path}")
        if self.response_status:
            parts.append(f"status={self.response_status}")
        if self.incomplete_reason:
            parts.append(f"incomplete_reason={self.incomplete_reason}")
        return ", ".join(parts)


class _OpenAIInvalidStructuredOutput(ExtractionProviderInvalidOutput):
    """Internal diagnostics; only allowlisted values may enter these attributes."""

    def __init__(
        self,
        message: str,
        *,
        diagnostics: tuple[_SafeStructuredOutputDiagnostic, ...],
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self._sanitised_repair_feedback = tuple(
            item.repair_feedback() for item in diagnostics
        )
        self._sanitised_diagnostic_summary = "; ".join(
            item.summary() for item in diagnostics
        )
        self._sanitised_field_path = next(
            (item.field_path for item in diagnostics if item.field_path), None
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

    @staticmethod
    def _safe_field_path(location: tuple[Any, ...] | list[Any]) -> str | None:
        parts: list[str] = []
        for component in location:
            if isinstance(component, int):
                if parts:
                    parts[-1] += "[]"
                continue
            if not isinstance(component, str) or component not in _SAFE_SCHEMA_FIELDS:
                continue
            parts.append(component)
        return ".".join(parts) or None

    @staticmethod
    def _safe_response_metadata(raw_response: Any) -> _SafeResponseMetadata:
        request_id = getattr(raw_response, "request_id", None)
        if not isinstance(request_id, str) or not re.fullmatch(
            r"[A-Za-z0-9._:-]{1,200}", request_id
        ):
            request_id = None
        try:
            payload = raw_response.http_response.json()
        except Exception:
            return _SafeResponseMetadata(request_id=request_id)
        if not isinstance(payload, dict):
            return _SafeResponseMetadata(request_id=request_id)
        status = payload.get("status")
        if status not in _SAFE_RESPONSE_STATUSES:
            status = None
        incomplete_reason = None
        incomplete = payload.get("incomplete_details")
        if isinstance(incomplete, dict):
            candidate_reason = incomplete.get("reason")
            if candidate_reason in _SAFE_INCOMPLETE_REASONS:
                incomplete_reason = candidate_reason
        outputs = payload.get("output", [])
        if not isinstance(outputs, list):
            outputs = []
        refusal_present = False
        for output in outputs:
            if not isinstance(output, dict):
                continue
            contents = output.get("content", [])
            if not isinstance(contents, list):
                continue
            if any(
                isinstance(content, dict) and content.get("type") == "refusal"
                for content in contents
            ):
                refusal_present = True
                break
        return _SafeResponseMetadata(
            status=status,
            incomplete_reason=incomplete_reason,
            refusal_present=refusal_present,
            request_id=request_id,
        )

    @staticmethod
    def _diagnostics_from_validation_error(
        exc: Exception,
        metadata: _SafeResponseMetadata,
    ) -> tuple[_SafeStructuredOutputDiagnostic, ...]:
        try:
            errors = exc.errors(include_url=False, include_input=False)
        except (AttributeError, TypeError):
            errors = []
        diagnostics: list[_SafeStructuredOutputDiagnostic] = []
        seen: set[tuple[str, str | None, str]] = set()
        for error in errors:
            error_type = error.get("type")
            location = error.get("loc", ())
            message = error.get("msg")
            field_path = OpenAIExtractionProvider._safe_field_path(location)
            if error_type == "json_invalid":
                code = "malformed-json"
                category = "malformed-json"
                validation_type = "malformed-json"
            elif error_type == "value_error":
                invariant_message = (
                    message.removeprefix("Value error, ")
                    if isinstance(message, str)
                    else ""
                )
                code = _SEMANTIC_INVARIANT_CODES.get(
                    invariant_message, "semantic-invariant-failed"
                )
                category = "semantic-validation"
                validation_type = "model-validator"
            elif error_type == "missing":
                code = "field-required"
                category = "field-validation"
                validation_type = "missing"
            elif error_type == "extra_forbidden":
                code = "unexpected-field"
                category = "field-validation"
                validation_type = "unexpected-field"
            elif error_type in {"enum", "literal_error"}:
                code = "invalid-enum"
                category = "field-validation"
                validation_type = "enum"
            elif isinstance(error_type, str) and (
                error_type.endswith("_type")
                or "parsing" in error_type
                or error_type.endswith("_from_float")
            ):
                code = "incorrect-type"
                category = "field-validation"
                validation_type = "type"
            elif isinstance(error_type, str) and error_type in {
                "greater_than",
                "greater_than_equal",
                "less_than",
                "less_than_equal",
                "string_too_long",
                "string_too_short",
                "too_long",
                "too_short",
            }:
                code = "constraint-violation"
                category = "field-validation"
                validation_type = "constraint"
            else:
                code = "field-validation-failed"
                category = "field-validation"
                validation_type = "field"
            identity = (code, field_path, validation_type)
            if identity in seen:
                continue
            seen.add(identity)
            diagnostics.append(
                _SafeStructuredOutputDiagnostic(
                    code=code,
                    category=category,
                    validation_type=validation_type,
                    field_path=field_path,
                    response_status=metadata.status,
                    incomplete_reason=metadata.incomplete_reason,
                )
            )
            if len(diagnostics) == 8:
                break
        return tuple(diagnostics) or (
            _SafeStructuredOutputDiagnostic(
                code="sdk-response-parsing-failed",
                category="sdk-response-parsing",
                validation_type="parser",
                response_status=metadata.status,
                incomplete_reason=metadata.incomplete_reason,
            ),
        )

    def _invalid_output_error(
        self,
        message: str,
        diagnostics: tuple[_SafeStructuredOutputDiagnostic, ...],
        *,
        request_id: str | None = None,
    ) -> _OpenAIInvalidStructuredOutput:
        if not isinstance(request_id, str) or not re.fullmatch(
            r"[A-Za-z0-9._:-]{1,200}", request_id
        ):
            request_id = None
        return _OpenAIInvalidStructuredOutput(
            message,
            diagnostics=diagnostics,
            provider_name=self.provider_name,
            requested_model=self.model_name,
            request_id=request_id,
        )

    def _parser_error(
        self,
        exc: Exception,
        metadata: _SafeResponseMetadata,
    ) -> ExtractionProviderError:
        name = type(exc).__name__
        if name == "ContentFilterFinishReasonError":
            return ExtractionProviderRefusal(
                "The OpenAI model refused the extraction request.",
                provider_name=self.provider_name,
                requested_model=self.model_name,
                request_id=metadata.request_id,
            )
        if metadata.status == "incomplete" or name == "LengthFinishReasonError":
            reason = metadata.incomplete_reason
            code = (
                f"response-incomplete-{reason.replace('_', '-')}"
                if reason
                else "response-incomplete"
            )
            return self._invalid_output_error(
                "OpenAI returned incomplete structured output.",
                (
                    _SafeStructuredOutputDiagnostic(
                        code=code,
                        category="incomplete-output",
                        validation_type="incomplete",
                        response_status=metadata.status,
                        incomplete_reason=reason,
                    ),
                ),
                request_id=metadata.request_id,
            )
        if name == "ValidationError":
            return self._invalid_output_error(
                "OpenAI returned schema-invalid structured output.",
                self._diagnostics_from_validation_error(exc, metadata),
                request_id=metadata.request_id,
            )
        if name == "JSONDecodeError":
            return self._invalid_output_error(
                "OpenAI returned malformed structured output.",
                (
                    _SafeStructuredOutputDiagnostic(
                        code="malformed-json",
                        category="malformed-json",
                        validation_type="malformed-json",
                        response_status=metadata.status,
                    ),
                ),
                request_id=metadata.request_id,
            )
        if name == "APIResponseValidationError":
            return self._invalid_output_error(
                "The OpenAI SDK could not parse the provider response.",
                (
                    _SafeStructuredOutputDiagnostic(
                        code="sdk-response-validation-failed",
                        category="sdk-response-parsing",
                        validation_type="sdk-response-validation",
                        response_status=metadata.status,
                    ),
                ),
                request_id=metadata.request_id,
            )
        return self._invalid_output_error(
            "The OpenAI SDK could not parse the structured response.",
            (
                _SafeStructuredOutputDiagnostic(
                    code="sdk-response-parsing-failed",
                    category="sdk-response-parsing",
                    validation_type="parser",
                    response_status=metadata.status,
                ),
            ),
            request_id=metadata.request_id,
        )

    def _parse_structured_response(self, **request_options: Any) -> Any:
        raw_responses = getattr(self._client.responses, "with_raw_response", None)
        if raw_responses is None:
            return self._client.responses.parse(**request_options)
        raw_response = raw_responses.parse(**request_options)
        metadata = self._safe_response_metadata(raw_response)
        if metadata.refusal_present:
            raise ExtractionProviderRefusal(
                "The OpenAI model refused the extraction request.",
                provider_name=self.provider_name,
                requested_model=self.model_name,
                request_id=metadata.request_id,
            )
        if metadata.status == "incomplete":
            raise self._parser_error(RuntimeError("incomplete"), metadata)
        parser_error: ExtractionProviderError | None = None
        try:
            return raw_response.parse()
        except Exception as exc:
            parser_error = self._parser_error(exc, metadata)
        assert parser_error is not None
        raise parser_error

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
        provider_error: ExtractionProviderError | None = None
        try:
            response = self._parse_structured_response(
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
        except ExtractionProviderError:
            raise
        except Exception as exc:
            provider_error = self._sanitised_error(exc)
        if provider_error is not None:
            raise provider_error

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
        validation_error: ExtractionProviderError | None = None
        try:
            extraction = (
                parsed
                if isinstance(parsed, RawChunkExtraction)
                else RawChunkExtraction.model_validate(parsed)
            )
        except Exception as exc:
            response_status = getattr(response, "status", None)
            metadata = _SafeResponseMetadata(
                status=(
                    response_status
                    if response_status in _SAFE_RESPONSE_STATUSES
                    else None
                )
            )
            if type(exc).__name__ == "ValidationError":
                validation_error = self._invalid_output_error(
                    "OpenAI returned semantically invalid structured output.",
                    self._diagnostics_from_validation_error(exc, metadata),
                    request_id=getattr(response, "_request_id", None),
                )
            else:
                validation_error = ExtractionProviderInvalidOutput(
                    "OpenAI returned semantically invalid structured output."
                )
        if validation_error is not None:
            raise validation_error
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
