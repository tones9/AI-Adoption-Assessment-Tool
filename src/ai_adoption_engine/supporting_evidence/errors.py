"""Customer-safe typed failures for explicit supporting-evidence services."""

from __future__ import annotations

from typing import Any


class SupportingEvidenceServiceError(RuntimeError):
    code = "supporting-evidence-error"

    def __init__(self, message: str, *, result: Any | None = None) -> None:
        super().__init__(message)
        self.result = result


class SupportingEvidenceLineageError(SupportingEvidenceServiceError):
    code = "invalid-or-stale-formal-lineage"


class SupportingEvidenceUnsupportedFileError(SupportingEvidenceServiceError):
    code = "unsupported-file"


class SupportingEvidenceUnsafePdfError(SupportingEvidenceServiceError):
    code = "unsafe-pdf"


class SupportingEvidenceEncryptedPdfError(SupportingEvidenceServiceError):
    code = "encrypted-pdf"


class SupportingEvidenceMalformedPdfError(SupportingEvidenceServiceError):
    code = "malformed-pdf"


class SupportingEvidenceUnreadablePdfError(SupportingEvidenceServiceError):
    code = "unreadable-or-scanned-pdf"


class SupportingEvidenceInvalidTextError(SupportingEvidenceServiceError):
    code = "invalid-text"


class SupportingEvidenceLimitError(SupportingEvidenceServiceError):
    code = "supporting-evidence-limit"


class SupportingEvidenceDuplicateSourceError(SupportingEvidenceServiceError):
    code = "duplicate-original-process-document"


class SupportingEvidenceRequestConflictError(SupportingEvidenceServiceError):
    code = "conflicting-request-token"


class SupportingEvidenceConsentRequiredError(SupportingEvidenceServiceError):
    code = "provider-consent-required"


class SupportingEvidenceProviderFailure(SupportingEvidenceServiceError):
    code = "supporting-evidence-provider-failure"

    def __init__(
        self,
        message: str,
        *,
        provider_code: str,
        result: Any | None = None,
    ) -> None:
        super().__init__(message, result=result)
        self.provider_code = provider_code


class SupportingEvidenceInvalidProviderOutputError(
    SupportingEvidenceProviderFailure
):
    code = "invalid-provider-output"


class SupportingEvidenceCitationError(SupportingEvidenceServiceError):
    code = "unresolved-or-ambiguous-citation"


class SupportingEvidenceConcurrentAttemptError(SupportingEvidenceServiceError):
    code = "concurrent-or-stale-attempt"


class SupportingEvidenceFinalizationError(SupportingEvidenceServiceError):
    code = "persistence-finalization-failed"


class SupportingEvidenceInterruptedError(SupportingEvidenceServiceError):
    code = "supporting-evidence-work-interrupted"

    def __init__(self, message: str, *, pending: Any) -> None:
        super().__init__(message)
        self.pending = pending


class SupportingEvidenceUnknownProposalError(SupportingEvidenceServiceError):
    code = "unknown-supporting-evidence-proposal"


class SupportingEvidenceStaleProposalError(SupportingEvidenceServiceError):
    code = "stale-or-historical-proposal"


class SupportingEvidenceInvalidReviewerError(SupportingEvidenceServiceError):
    code = "invalid-reviewer-declaration"


class SupportingEvidenceInvalidReviewError(SupportingEvidenceServiceError):
    code = "invalid-review-action-or-classification"


class SupportingEvidenceMissingFactLinkError(SupportingEvidenceServiceError):
    code = "missing-documented-fact-link"


class SupportingEvidenceInvalidReferenceError(SupportingEvidenceServiceError):
    code = "stale-or-invalid-reviewed-evidence-reference"


class SupportingEvidenceInsufficientConflictError(SupportingEvidenceServiceError):
    code = "insufficient-conflict-references"


class SupportingEvidenceStaleRevisionError(SupportingEvidenceServiceError):
    code = "stale-expected-review-revision"


class SupportingEvidenceConcurrentReviewError(SupportingEvidenceServiceError):
    code = "concurrent-review"


class SupportingEvidenceInvalidMappingError(SupportingEvidenceServiceError):
    code = "invalid-formal-input-mapping"


class SupportingEvidenceStaleMappingError(SupportingEvidenceServiceError):
    code = "stale-formal-input-mapping"


class SupportingEvidenceIncompletePreparationError(SupportingEvidenceServiceError):
    code = "incomplete-formal-input-preparation"

    def __init__(self, message: str, *, blockers: tuple[str, ...]) -> None:
        super().__init__(message)
        self.blockers = blockers


class SupportingEvidenceStaleCandidateSetError(SupportingEvidenceServiceError):
    code = "stale-formal-input-candidate-set"


class SupportingEvidenceConcurrentPreparationError(SupportingEvidenceServiceError):
    code = "concurrent-formal-input-preparation"
