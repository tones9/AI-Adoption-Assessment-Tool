import json
from datetime import timedelta

import pytest
from pydantic import ValidationError

from ai_adoption_engine.models.candidate_process import (
    CandidateAssertion,
    CandidateDependency,
)
from ai_adoption_engine.models.enums import KnowledgeState
from ai_adoption_engine.models.extraction import (
    ExtractionIssue,
    ExtractionIssueSeverity,
)
from ai_adoption_engine.models.review import (
    InformationOrigin,
    ReviewDisposition,
    ReviewedDependency,
    reviewed_assertion,
)
from tests.fakes.review import FIXED_TIME, candidate_result, review_service


def test_candidate_starts_as_review_session_not_validated_process() -> None:
    session = review_service().start_review(candidate_result())
    assert session.original_candidate.candidate_status.value.startswith("CANDIDATE")
    assert not hasattr(session, "business_process")
    assert session.events == []


def test_known_assertion_is_accepted_without_changing_document_provenance() -> None:
    service = review_service()
    session = service.start_review(candidate_result())
    original_evidence = session.process_name.evidence
    service.accept_assertion(session, session.process_name, "process.name")
    assert session.process_name.disposition is ReviewDisposition.ACCEPTED
    assert session.process_name.origin is InformationOrigin.DOCUMENT_SUPPORTED
    assert session.process_name.evidence == original_evidence


def test_accepted_inference_remains_identifiable_as_model_inference() -> None:
    service = review_service()
    session = service.start_review(candidate_result())
    support = session.steps[0].activity.evidence
    session.process_description = session.process_description.model_copy(
        update={
            "original": CandidateAssertion[str](
                value="Complaints are logged before review.",
                knowledge_state="inferred",
                rationale="Synthesised from the ordered activities.",
                evidence=support,
                confidence=0.72,
            ),
            "value": "Complaints are logged before review.",
            "knowledge_state": KnowledgeState.INFERRED,
            "origin": InformationOrigin.MODEL_INFERRED,
            "rationale": "Synthesised from the ordered activities.",
            "evidence": support,
            "confidence": 0.72,
        }
    )
    service.accept_assertion(
        session, session.process_description, "process.description"
    )
    assert session.process_description.origin is InformationOrigin.MODEL_INFERRED
    assert session.process_description.knowledge_state is KnowledgeState.INFERRED
    assert session.process_description.confidence == 0.72


def test_correction_retains_original_but_clears_document_evidence() -> None:
    service = review_service()
    session = service.start_review(candidate_result())
    original = session.process_name.original
    service.correct_assertion(
        session,
        session.process_name,
        "process.name",
        "Customer complaint handling",
        rationale="Reviewer supplied the governed process name.",
    )
    assert session.process_name.original == original
    assert session.process_name.value == "Customer complaint handling"
    assert session.process_name.origin is InformationOrigin.HUMAN_SUPPLIED
    assert session.process_name.evidence == []
    assert json.loads(session.events[-1].before_snapshot)["evidence"]


def test_source_backed_correction_retains_trusted_document_evidence() -> None:
    service = review_service()
    session = service.start_review(candidate_result())
    evidence = session.process_name.evidence
    service.correct_assertion(
        session,
        session.process_name,
        "process.name",
        "Complaint handling process",
        rationale="Corrected to match the source heading.",
        origin=InformationOrigin.DOCUMENT_SUPPORTED,
        evidence=evidence,
    )
    assert session.process_name.origin is InformationOrigin.DOCUMENT_SUPPORTED
    assert session.process_name.evidence == evidence


def test_assertion_can_be_rejected_without_erasing_original() -> None:
    service = review_service()
    session = service.start_review(candidate_result())
    activity = session.steps[0].activity
    service.reject_assertion(
        session, activity, "steps.record.activity", rationale="Duplicate activity"
    )
    assert activity.retained is False
    assert activity.disposition is ReviewDisposition.REJECTED
    assert activity.original.value == "Record complaint"


def test_unknown_can_be_human_resolved_without_fabricated_document_evidence() -> None:
    service = review_service()
    session = service.start_review(candidate_result())
    assertion = session.steps[0].description
    service.resolve_unknown(
        session,
        assertion,
        "steps.record.description",
        "Capture the complaint in the case record.",
        rationale="Confirmed during process-owner review.",
    )
    assert assertion.knowledge_state is KnowledgeState.KNOWN
    assert assertion.origin is InformationOrigin.HUMAN_SUPPLIED
    assert assertion.evidence == []
    assert assertion.original.knowledge_state is KnowledgeState.UNKNOWN


def test_unknown_can_be_intentionally_retained() -> None:
    service = review_service()
    session = service.start_review(candidate_result())
    signal = session.steps[0].capability_signals[0].assertion
    service.retain_unknown(
        session, signal, "steps.record.capability.reads_unstructured_documents"
    )
    assert signal.disposition is ReviewDisposition.UNKNOWN_RETAINED
    assert signal.value is None


def test_human_collection_item_has_human_origin_and_no_document_evidence() -> None:
    service = review_service()
    session = service.start_review(candidate_result())
    actor = service.add_human_collection_item(
        session,
        session.steps[0].actors,
        "steps.record.actors",
        "Service agent",
        rationale="Confirmed by the process owner.",
    )
    assert actor.origin is InformationOrigin.HUMAN_SUPPLIED
    assert actor.evidence == []
    assert actor.original.value is None


def test_steps_can_be_reordered_then_explicitly_accepted() -> None:
    service = review_service()
    session = service.start_review(candidate_result())
    record_id, review_id = [step.candidate_step_id for step in session.steps]
    service.reorder_steps(session, [review_id, record_id], rationale="Corrected order")
    assert [(step.candidate_step_id, step.sequence) for step in session.steps] == [
        (review_id, 1),
        (record_id, 2),
    ]
    assert session.order_accepted is False
    service.accept_step_order(session)
    assert session.order_accepted is True


def test_dependency_target_can_be_corrected_with_an_audit_event() -> None:
    service = review_service()
    session = service.start_review(candidate_result())
    source = session.steps[1].activity.original
    dependency = CandidateDependency(
        target_label=CandidateAssertion[str](
            value="Record complaint",
            knowledge_state="known",
            rationale="Directly stated in the source.",
            evidence=source.evidence,
        ),
        relationship=CandidateAssertion[str](
            value="follows",
            knowledge_state="inferred",
            rationale="Derived from source order.",
            evidence=source.evidence,
            confidence=0.8,
        ),
    )
    session.steps[1].dependencies.append(
        ReviewedDependency(
            original=dependency,
            target_label=reviewed_assertion(dependency.target_label),
            relationship=reviewed_assertion(dependency.relationship),
        )
    )
    target_id = session.steps[0].candidate_step_id
    service.correct_dependency(
        session,
        session.steps[1].candidate_step_id,
        0,
        target_id,
        rationale="Reviewer resolved the target step.",
    )
    assert session.steps[1].dependencies[0].target_candidate_step_id == target_id
    assert session.events[-1].action.value == "correct-dependency"


def test_step_removal_is_controlled_and_audited() -> None:
    service = review_service()
    session = service.start_review(candidate_result())
    removed = session.steps[1]
    service.remove_step(
        session, removed.candidate_step_id, rationale="Duplicate extracted step."
    )
    assert removed.retained is False
    assert session.order_accepted is False
    assert json.loads(session.events[-1].before_snapshot)["original"]


def test_review_events_are_immutable() -> None:
    service = review_service()
    session = service.start_review(candidate_result())
    service.accept_assertion(session, session.process_name, "process.name")
    with pytest.raises(ValidationError, match="frozen"):
        session.events[0].occurred_at = FIXED_TIME + timedelta(days=1)


def test_only_structural_extraction_issues_become_blocking_conflicts() -> None:
    result = candidate_result()
    result.issues.extend(
        [
            ExtractionIssue(
                severity=ExtractionIssueSeverity.WARNING,
                code="ordering-conflict",
                message="Conflicting explicit ordering requires review.",
            ),
            ExtractionIssue(
                severity=ExtractionIssueSeverity.ERROR,
                code="snippet-not-found",
                message="Assessment evidence could not be resolved.",
                field_path="steps[0].characteristics.repetition",
            ),
        ]
    )
    session = review_service().start_review(result)
    assert [item.code for item in session.conflicts] == ["ordering-conflict"]
    assert len(session.extraction_issues) == 2
