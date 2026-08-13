"""Sanitised errors exposed by provider-neutral extraction boundaries."""

from ai_adoption_engine.models.extraction import (
    ProviderErrorCategory,
    ProviderFailureStage,
)


class ExtractionProviderError(RuntimeError):
    code = "provider-error"
    category = ProviderErrorCategory.PROVIDER_ERROR
    default_stage = ProviderFailureStage.PROVIDER_REQUEST

    def __init__(
        self,
        message: str,
        *,
        provider_name: str | None = None,
        requested_model: str | None = None,
        http_status_code: int | None = None,
        request_id: str | None = None,
        sdk_retries_exhausted: bool | None = None,
        failure_stage: ProviderFailureStage | None = None,
    ) -> None:
        super().__init__(message)
        self.provider_name = provider_name
        self.requested_model = requested_model
        self.http_status_code = http_status_code
        self.request_id = request_id
        self.sdk_retries_exhausted = sdk_retries_exhausted
        self.failure_stage = failure_stage or self.default_stage


class ExtractionProviderBadRequest(ExtractionProviderError):
    code = "provider-bad-request"
    category = ProviderErrorCategory.BAD_REQUEST


class ExtractionProviderAuthenticationError(ExtractionProviderError):
    code = "provider-authentication"
    category = ProviderErrorCategory.AUTHENTICATION


class ExtractionProviderPermissionDenied(ExtractionProviderError):
    code = "provider-permission-denied"
    category = ProviderErrorCategory.PERMISSION_DENIED


class ExtractionProviderNotFound(ExtractionProviderError):
    code = "provider-model-or-resource-not-found"
    category = ProviderErrorCategory.MODEL_OR_RESOURCE_NOT_FOUND


class ExtractionProviderRateLimit(ExtractionProviderError):
    code = "provider-rate-limit-or-quota"
    category = ProviderErrorCategory.RATE_LIMIT_OR_QUOTA


class ExtractionProviderConnectionError(ExtractionProviderError):
    code = "provider-connection"
    category = ProviderErrorCategory.CONNECTION


class ExtractionProviderTimeout(ExtractionProviderError):
    code = "provider-timeout"
    category = ProviderErrorCategory.TIMEOUT


class ExtractionProviderServerError(ExtractionProviderError):
    code = "provider-server-error"
    category = ProviderErrorCategory.SERVER_ERROR


class ExtractionProviderRefusal(ExtractionProviderError):
    code = "provider-refusal"
    category = ProviderErrorCategory.REFUSAL
    default_stage = ProviderFailureStage.PROVIDER_RESPONSE


class ExtractionProviderInvalidOutput(ExtractionProviderError):
    code = "provider-invalid-structured-output"
    category = ProviderErrorCategory.INVALID_STRUCTURED_OUTPUT
    default_stage = ProviderFailureStage.SCHEMA_PARSING


class ExtractionProviderConfigurationError(ExtractionProviderError):
    code = "provider-configuration-error"
    category = ProviderErrorCategory.CONFIGURATION
