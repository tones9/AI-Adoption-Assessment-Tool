from __future__ import annotations

from copy import deepcopy

from ai_adoption_engine.presentation.review_journey import build_review_journey
from ai_adoption_engine.presentation.review_progress import approval_errors
from tests.fakes.review import candidate_result, review_service


def _review():
    service = review_service()
    return service, service.start_review(candidate_result())


def test_journey_queue_is_the_real_phase4_preflight_in_the_same_order() -> None:
    _, session = _review()

    view = build_review_journey(session)

    assert [(item.field_path, item.field_label) for item in view.required_items] == [
        (item.field_path, item.field_label) for item in view.progress.outstanding
    ]
    assert [(error.code, error.field_path) for error in view.approval_errors] == [
        (error.code, error.field_path) for error in approval_errors(session)
    ]
    assert view.default_focus_item_id == view.required_items[0].item_id
    assert not any("criteria" in (item.field_path or "") for item in view.required_items)


def test_journey_preserves_valid_focus_or_falls_back_to_first_real_blocker() -> None:
    _, session = _review()
    first = build_review_journey(session)

    assert (
        build_review_journey(session, selected_item_id=first.required_items[-1].item_id)
        .default_focus_item_id
        == first.required_items[-1].item_id
    )
    assert (
        build_review_journey(session, selected_item_id="stale-ui-bookmark")
        .default_focus_item_id
        == first.required_items[0].item_id
    )


def test_journey_keeps_provenance_and_unknowns_descriptive_without_mutation() -> None:
    service, session = _review()
    service.correct_assertion(
        session,
        session.process_description,
        "process.description",
        "Reviewer-supplied description",
        rationale="Synthetic review correction.",
    )
    service.retain_unknown(
        session,
        session.steps[0].criteria[0].assertion,
        f"steps.{session.steps[0].candidate_step_id}.criteria[0]",
    )
    before = deepcopy(session.model_dump(mode="json"))

    view = build_review_journey(session)

    assert view.audit.corrections == ("process.description",)
    assert "process.description" in view.audit.human_supplied_fields
    assert any(group.count for group in view.unknown_groups)
    assert view.audit.retained_unknowns == (
        f"steps.{session.steps[0].candidate_step_id}.criteria[0]",
    )
    assert session.model_dump(mode="json") == before


def test_journey_does_not_promote_optional_unknown_items_to_blockers() -> None:
    _, session = _review()
    view = build_review_journey(session)

    assert view.unknown_groups
    blocker_paths = {item.field_path for item in view.required_items}
    assert all("criteria" not in (path or "") for path in blocker_paths)
