"""Sanitised errors exposed by provider-neutral extraction boundaries."""


class ExtractionProviderError(RuntimeError):
    code = "provider-error"


class ExtractionProviderTimeout(ExtractionProviderError):
    code = "provider-timeout"


class ExtractionProviderRefusal(ExtractionProviderError):
    code = "provider-refusal"


class ExtractionProviderConfigurationError(ExtractionProviderError):
    code = "provider-configuration-error"
