from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ai_adoption_engine.models.formal_evidence import (
    FORMAL_EVIDENCE_FAMILY,
    ReviewerDeclaration,
)
from ai_adoption_engine.supporting_evidence.errors import (
    SupportingEvidenceInvalidReviewerError,
)
from ai_adoption_engine.supporting_evidence.review import (
    ReviewQueueStatus,
    SupportingEvidenceReviewService,
    derive_review_progress,
)


def test_review_progress_counts_only_review_dispositions() -> None:
    progress = derive_review_progress(
        (
            ReviewQueueStatus.ACCEPTED,
            ReviewQueueStatus.CORRECTED,
            ReviewQueueStatus.REJECTED,
            ReviewQueueStatus.UNRESOLVED_UNKNOWN,
            ReviewQueueStatus.UNRESOLVED_CONFLICT,
            ReviewQueueStatus.UNREVIEWED,
        )
    )
    assert progress.total_current_proposals == 6
    assert progress.accepted_proposals == 1
    assert progress.corrected_proposals == 1
    assert progress.rejected_proposals == 1
    assert progress.unresolved_unknowns == 1
    assert progress.unresolved_conflicts == 1
    assert progress.unreviewed_proposals == 1
    assert progress.review_complete is False


def test_zero_or_all_terminal_proposals_are_review_complete_not_formally_ready() -> None:
    assert derive_review_progress(()).review_complete is True
    complete = derive_review_progress(
        (ReviewQueueStatus.REJECTED, ReviewQueueStatus.UNRESOLVED_UNKNOWN)
    )
    assert complete.review_complete is True
    assert not hasattr(complete, "formal_ready")
    assert not hasattr(complete, "evidence_sufficient")


def test_reviewer_validation_preserves_exact_local_declaration() -> None:
    reviewer = ReviewerDeclaration(
        schema_version="reviewer-declaration.v0.1",
        contract_family=FORMAL_EVIDENCE_FAMILY,
        reviewer_display_name="Alex Reviewer",
        declared_organisational_role="Process owner",
        identity_and_authority_locally_declared_not_authenticated=True,
        declared_at=datetime(2026, 10, 4, 15, 0, tzinfo=UTC),
        local_session_identity="local-session",
    )
    assert SupportingEvidenceReviewService._validate_reviewer(reviewer) == reviewer


def test_invalid_reviewer_is_customer_safe() -> None:
    with pytest.raises(SupportingEvidenceInvalidReviewerError) as failure:
        SupportingEvidenceReviewService._validate_reviewer(
            {
                "schema_version": "reviewer-declaration.v0.1",
                "contract_family": FORMAL_EVIDENCE_FAMILY,
                "reviewer_display_name": " ",
                "declared_organisational_role": "Owner",
                "identity_and_authority_locally_declared_not_authenticated": True,
                "declared_at": datetime(2026, 10, 4, 15, 0, tzinfo=UTC),
            }
        )
    assert failure.value.code == "invalid-reviewer-declaration"
    assert "display_name" not in str(failure.value)
