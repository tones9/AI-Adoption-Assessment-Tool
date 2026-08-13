from ai_adoption_engine.models.candidate_process import (
    CandidateAssertion,
    CandidateDependency,
)
from ai_adoption_engine.models.review import (
    ExplicitApproval,
    ReviewConflict,
    ReviewedDependency,
    reviewed_assertion,
)
from ai_adoption_engine.review.approval import approve_review
from tests.fakes.review import FIXED_TIME, candidate_result, review_service


def _reviewed_session():
    service = review_service()
    session = service.start_review(candidate_result())
    service.accept_assertion(session, session.process_name, "process.name")
    for step in session.steps:
        service.accept_assertion(
            session, step.activity, f"steps.{step.candidate_step_id}.activity"
        )
    service.accept_step_order(session)
    return service, session


def _approval() -> ExplicitApproval:
    return ExplicitApproval(
        approval_statement="APPROVE CURRENT-STATE PROCESS",
        approved_at=FIXED_TIME,
        rationale="The process owner confirmed the current-state representation.",
    )


def test_explicit_approval_is_required() -> None:
    _, session = _reviewed_session()
    result = approve_review(session, None)
    assert result.approved is None
    assert {item.code for item in result.errors} == {"explicit-approval-required"}


def test_unknown_assessment_values_do_not_block_process_approval() -> None:
    _, session = _reviewed_session()
    result = approve_review(session, _approval())
    assert result.errors == []
    assert result.approved is not None
    step = result.approved.business_process.steps[0]
    assert step.characteristics.repetition.value is None
    assert step.characteristics.capability_signals.creates_new_content.value is None
    assert result.approved.business_process.description is None
    assert step.actor is None


def test_open_structural_conflict_blocks_approval() -> None:
    _, session = _reviewed_session()
    session.conflicts.append(
        ReviewConflict(
            conflict_id="conflict-order",
            code="ambiguous-order",
            message="Two retained steps have irreconcilable ordering.",
            blocking=True,
            field_path="process.steps.order",
        )
    )
    result = approve_review(session, _approval())
    assert result.approved is None
    assert "unresolved-structural-conflict" in {item.code for item in result.errors}


def test_unconfirmed_activity_blocks_conversion() -> None:
    _, session = _reviewed_session()
    session.steps[0].activity.disposition = "unreviewed"
    result = approve_review(session, _approval())
    assert "step-activity-unconfirmed" in {item.code for item in result.errors}


def test_unresolved_dependency_blocks_until_human_correction() -> None:
    service, session = _reviewed_session()
    evidence = session.steps[1].activity.evidence
    original = CandidateDependency(
        target_label=CandidateAssertion[str](
            value="Record complaint",
            knowledge_state="known",
            rationale="Directly stated.",
            evidence=evidence,
        ),
        relationship=CandidateAssertion[str](
            value="follows",
            knowledge_state="inferred",
            rationale="Derived from order.",
            evidence=evidence,
            confidence=0.8,
        ),
    )
    session.steps[1].dependencies.append(
        ReviewedDependency(
            original=original,
            target_label=reviewed_assertion(original.target_label),
            relationship=reviewed_assertion(original.relationship),
        )
    )
    blocked = approve_review(session, _approval())
    assert "invalid-retained-dependency" in {item.code for item in blocked.errors}

    service.correct_dependency(
        session,
        session.steps[1].candidate_step_id,
        0,
        session.steps[0].candidate_step_id,
        rationale="Reviewer resolved the dependency target.",
    )
    approved = approve_review(session, _approval())
    assert approved.approved is not None


def test_approved_record_preserves_candidate_audit_and_source_evidence() -> None:
    service, session = _reviewed_session()
    service.resolve_unknown(
        session,
        session.process_description,
        "process.description",
        "A reviewer-supplied process summary.",
        rationale="Confirmed in the review meeting.",
    )
    result = approve_review(session, _approval())
    assert result.approved is not None
    approved = result.approved
    assert approved.review.original_candidate == session.original_candidate
    assert approved.review.events[-1].action.value == "approve"
    assert approved.review.process_description.evidence == []
    assert approved.business_process.description == "A reviewer-supplied process summary."
    assert all(
        reference.provenance != "human-supplied"
        for reference in approved.business_process.evidence
    )
    assert approved.business_process.steps[0].activity == "Record complaint"
    assert approved.business_process.steps[0].evidence_ids
    reference = approved.business_process.evidence[0]
    assert reference.source_locator
    assert reference.supporting_snippet in {
        "Complaint handling",
        "Agent records the complaint.",
        "Manager reviews the complaint.",
    }


def test_invalid_final_phase1_model_blocks_conversion() -> None:
    _, session = _reviewed_session()
    assertion = session.steps[0].criteria[0].assertion
    assertion.value = 9
    assertion.knowledge_state = "known"
    result = approve_review(session, _approval())
    assert result.approved is None
    assert "invalid-phase1-projection" in {item.code for item in result.errors}
