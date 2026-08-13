from ai_adoption_engine.models.review import ExplicitApproval, InformationOrigin
from ai_adoption_engine.review.approval import approve_review
from tests.fakes.review import FIXED_TIME, candidate_result, review_service


def test_fake_provider_candidate_to_human_review_to_approved_process() -> None:
    extraction = candidate_result()
    service = review_service()
    review = service.start_review(extraction)

    service.correct_assertion(
        review,
        review.process_name,
        "process.name",
        "Customer complaint handling",
        rationale="Reviewer confirmed the canonical process name.",
    )
    service.resolve_unknown(
        review,
        review.process_objective,
        "process.objective",
        "Record and review customer complaints.",
        rationale="Process owner supplied the objective.",
    )
    for step in review.steps:
        service.accept_assertion(
            review, step.activity, f"steps.{step.candidate_step_id}.activity"
        )
        service.retain_unknown(
            review,
            step.criteria[0].assertion,
            f"steps.{step.candidate_step_id}.criteria.repetition",
        )
    actor = service.add_human_collection_item(
        review,
        review.steps[0].actors,
        "steps.record.actors",
        "Service agent",
        rationale="Confirmed by the reviewer.",
    )
    first_step_id = review.steps[0].candidate_step_id
    service.select_primary_actor(
        review,
        first_step_id,
        "Service agent",
        rationale="Primary responsibility confirmed.",
    )
    service.accept_step_order(review)

    result = approve_review(
        review,
        ExplicitApproval(
            approval_statement="APPROVE CURRENT-STATE PROCESS",
            approved_at=FIXED_TIME,
            rationale="Current-state process representation accepted.",
        ),
    )
    assert result.approved is not None
    approved = result.approved
    assert approved.business_process.name == "Customer complaint handling"
    assert [step.activity for step in approved.business_process.steps] == [
        "Record complaint",
        "Review complaint",
    ]
    assert approved.business_process.steps[0].actor == "Service agent"
    assert actor.origin is InformationOrigin.HUMAN_SUPPLIED
    assert actor.evidence == []
    assert approved.review.original_candidate == extraction.candidate
    assert approved.review.events
