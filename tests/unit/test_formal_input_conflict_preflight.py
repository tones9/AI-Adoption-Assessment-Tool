"""Regression tests for the read-only Slice 6 conflict preflight exposure.

``preflight_conflicts`` must reuse the exact Slice 2 projection path: every
conflict it reports is exactly the alternative tuple ``project`` demands, and it
never projects, selects, mutates, or reports a false conflict.
"""

from __future__ import annotations

from ai_adoption_engine.formal.input_adapter import (
    FormalFourGateInputAdapter,
    FormalInputConflictPreflight,
)
from ai_adoption_engine.models.enums import CriterionName
from ai_adoption_engine.models.formal_assessment import (
    FORMAL_ASSESSMENT_RUN_STORE_ID,
    FormalInputConflictResolution,
    FormalValueOrigin,
)
from ai_adoption_engine.models.formal_assessment_adapter import (
    FORMAL_FOUR_GATE_INPUT_ADAPTER_RULES,
    FormalInputAdapterFailure,
    FormalInputAdapterFailureCode,
    FormalInputAdapterSuccess,
)
from ai_adoption_engine.models.formal_evidence import (
    CriterionFormalTarget,
    FormalTargetKind,
)
from tests.unit.test_formal_input_adapter import (
    NOW,
    approved_review,
    approved_with_known,
    formal_lineage,
    make_authorization,
    make_bundle,
    make_fact_entry,
    make_resolution,
    project_supporting,
    request,
    reviewer,
    run_lineage,
)


TARGET = CriterionFormalTarget(
    kind=FormalTargetKind.CRITERION,
    criterion=CriterionName.BUSINESS_VALUE,
)


def _preflight(approved, candidate, readiness, reviews, resolutions=()):
    return FormalFourGateInputAdapter().preflight_conflicts(
        authorization=make_authorization(
            approved, candidate=candidate, readiness=readiness, resolutions=resolutions
        ),
        approved_review=approved,
        candidate_set=candidate,
        readiness=readiness,
        supporting_reviews=reviews,
    )


def _resolution_from(alternatives, approved, *, selected_value):
    selected = next(item for item in alternatives if item.value == selected_value)
    return FormalInputConflictResolution(
        schema_version="formal-input-conflict-resolution.v0.1",
        store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
        resolution_id="resolution-preflight",
        lineage=formal_lineage(approved),
        run_lineage=run_lineage(),
        activity_id=alternatives[0].activity_id,
        target=alternatives[0].target,
        alternatives=alternatives,
        selected_value=selected.value,
        selected_knowledge_state=selected.knowledge_state,
        selected_confidence=selected.confidence,
        reviewer=reviewer(),
        explicit_human_selection=True,
        rationale="Human selected the effective value for this exact run.",
        resolved_at=NOW,
        request=request("resolve-preflight"),
    )


def test_process_only_has_no_preflight_conflicts() -> None:
    approved = approved_review()
    result = FormalFourGateInputAdapter().preflight_conflicts(
        authorization=make_authorization(approved),
        approved_review=approved,
        candidate_set=None,
        readiness=None,
        supporting_reviews=(),
    )
    assert result == FormalInputConflictPreflight(conflicts=())


def test_filled_unknown_and_identical_values_are_not_false_conflicts() -> None:
    filled = approved_review()
    candidate, readiness, reviews = make_bundle(
        filled, (make_fact_entry(filled, index=1, target=TARGET, value=4),)
    )
    assert _preflight(filled, candidate, readiness, reviews).conflicts == ()

    corroborated = approved_with_known(CriterionName.BUSINESS_VALUE, 4)
    candidate, readiness, reviews = make_bundle(
        corroborated, (make_fact_entry(corroborated, index=1, target=TARGET, value=4),)
    )
    assert _preflight(corroborated, candidate, readiness, reviews).conflicts == ()


def test_known_source_conflict_matches_projection_alternatives_exactly() -> None:
    approved = approved_with_known(CriterionName.BUSINESS_VALUE, 3)
    candidate, readiness, reviews = make_bundle(
        approved, (make_fact_entry(approved, index=1, target=TARGET, value=5),)
    )
    preflight = _preflight(approved, candidate, readiness, reviews)
    assert isinstance(preflight, FormalInputConflictPreflight)
    (alternatives,) = preflight.conflicts
    expected = make_resolution(
        FormalFourGateInputAdapter(), approved, candidate, readiness, reviews, selected_value=5
    ).alternatives
    assert alternatives == expected
    assert [item.origin for item in alternatives] == [
        FormalValueOrigin.APPROVED_PROCESS,
        FormalValueOrigin.SUPPORTING_MAPPING,
    ]
    # A resolution built purely from preflight output is accepted by ``project``.
    resolution = _resolution_from(alternatives, approved, selected_value=5)
    projected = project_supporting(approved, candidate, readiness, reviews, (resolution,))
    assert isinstance(projected, FormalInputAdapterSuccess)
    assert projected.projection.engine_input.steps[0].characteristics.business_value.value == 5


def test_supporting_vs_supporting_and_corroborated_conflicts() -> None:
    unknown = approved_review()
    entries = (
        make_fact_entry(unknown, index=1, target=TARGET, value=3),
        make_fact_entry(unknown, index=2, target=TARGET, value=5),
    )
    candidate, readiness, reviews = make_bundle(unknown, entries)
    (alternatives,) = _preflight(unknown, candidate, readiness, reviews).conflicts
    assert {item.origin for item in alternatives} == {FormalValueOrigin.SUPPORTING_MAPPING}
    assert {item.value for item in alternatives} == {3, 5}

    known = approved_with_known(CriterionName.BUSINESS_VALUE, 3)
    entries = (
        make_fact_entry(known, index=1, target=TARGET, value=3),
        make_fact_entry(known, index=2, target=TARGET, value=5),
    )
    candidate, readiness, reviews = make_bundle(known, entries)
    (alternatives,) = _preflight(known, candidate, readiness, reviews).conflicts
    assert alternatives[0].origin is FormalValueOrigin.CORROBORATED
    assert alternatives == make_resolution(
        FormalFourGateInputAdapter(), known, candidate, readiness, reviews, selected_value=3
    ).alternatives


def test_already_resolved_conflicts_are_not_reported_again() -> None:
    approved = approved_with_known(CriterionName.BUSINESS_VALUE, 3)
    candidate, readiness, reviews = make_bundle(
        approved, (make_fact_entry(approved, index=1, target=TARGET, value=5),)
    )
    resolution = make_resolution(
        FormalFourGateInputAdapter(), approved, candidate, readiness, reviews, selected_value=3
    )
    assert _preflight(approved, candidate, readiness, reviews, (resolution,)).conflicts == ()


def test_preflight_never_mutates_inputs_or_rules_and_fails_closed() -> None:
    approved = approved_with_known(CriterionName.BUSINESS_VALUE, 3)
    candidate, readiness, reviews = make_bundle(
        approved, (make_fact_entry(approved, index=1, target=TARGET, value=5),)
    )
    authorization = make_authorization(approved, candidate=candidate, readiness=readiness)
    before = (
        approved.model_dump(mode="json"),
        candidate.model_dump(mode="json"),
        readiness.model_dump(mode="json"),
        authorization.model_dump(mode="json"),
    )
    adapter = FormalFourGateInputAdapter()
    adapter.preflight_conflicts(
        authorization=authorization,
        approved_review=approved,
        candidate_set=candidate,
        readiness=readiness,
        supporting_reviews=reviews,
    )
    assert (
        approved.model_dump(mode="json"),
        candidate.model_dump(mode="json"),
        readiness.model_dump(mode="json"),
        authorization.model_dump(mode="json"),
    ) == before
    assert adapter.rules == FORMAL_FOUR_GATE_INPUT_ADAPTER_RULES

    failure = adapter.preflight_conflicts(
        authorization=authorization,
        approved_review=None,
        candidate_set=candidate,
        readiness=readiness,
        supporting_reviews=reviews,
    )
    assert isinstance(failure, FormalInputAdapterFailure)
    assert failure.projection is None

    unresolved = project_supporting(approved, candidate, readiness, reviews)
    assert isinstance(unresolved, FormalInputAdapterFailure)
    assert unresolved.errors[0].code is FormalInputAdapterFailureCode.UNRESOLVED_CONFLICT
