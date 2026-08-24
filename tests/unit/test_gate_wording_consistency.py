"""One check status, named the same way on every surface.

Assessment Results and the Decision Package already distinguish a check that
was evaluated and not met from a check that stopped because a required fact was
never established.  The controlled reassessment report used to flatten both into
"Not met".  These tests pin the distinction, and pin that it is drawn from the
persisted recommendation rather than from a rationale string.
"""

from __future__ import annotations

import dataclasses

import pytest

from ai_adoption_engine.models.enums import RecommendationMode
from ai_adoption_engine.presentation import labels
from ai_adoption_engine.presentation.controlled_reassessment_report import (
    build_controlled_reassessment_narrative,
)
from ai_adoption_engine.presentation.decision_narrative import (
    portfolio_reason_statement,
)
from tests.ui.test_decision_continuation_ui import _completed_m2_successor


UNESTABLISHED = labels.GATE_STATUS_UNESTABLISHED_LABEL


# ---------------------------------------------------------------------------
# The vocabulary helper
# ---------------------------------------------------------------------------


def test_failed_alone_still_reads_as_a_negative_result() -> None:
    assert labels.gate_status_label("failed") == "Not met"
    assert labels.gate_status_label("failed", outcome_unestablished=False) == "Not met"


def test_failed_on_an_unestablished_outcome_is_not_called_not_met() -> None:
    named = labels.gate_status_label("failed", outcome_unestablished=True)
    assert named == UNESTABLISHED
    assert "not met" not in named.lower()
    assert "could not be completed" in named.lower()
    assert "required evidence was not established" in named.lower()


@pytest.mark.parametrize(
    "status", ["passed", "passed_with_constraints", "not_evaluated"]
)
def test_no_other_status_is_affected_by_the_flag(status: str) -> None:
    assert labels.gate_status_label(status) == labels.gate_status_label(
        status, outcome_unestablished=True
    )
    assert labels.gate_status_label(status) == labels.GATE_STATUS_LABELS[status]


def test_the_persisted_status_translations_are_unchanged() -> None:
    assert labels.GATE_STATUS_LABELS == {
        "passed": "Passed",
        "passed_with_constraints": "Passed with conditions",
        "failed": "Not met",
        "not_evaluated": "Not needed — an earlier check already decided the outcome",
    }


# ---------------------------------------------------------------------------
# The controlled reassessment report
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def controlled_report(tmp_path_factory):
    monkeypatch = pytest.MonkeyPatch()
    try:
        repository, assessment_id, _ = _completed_m2_successor(
            tmp_path_factory.mktemp("gate-wording")
        )
        monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(repository.path))
        from ai_adoption_engine.presentation.context import (
            decision_continuation_service,
        )

        view = decision_continuation_service().open(assessment_id)
        report = next(
            run.controlled_report
            for run in view.m2_runs
            if run.controlled_report is not None
        )
        yield report
    finally:
        monkeypatch.undo()


def test_the_fixture_is_the_case_the_audit_found(controlled_report) -> None:
    """A failed baseline check on an activity the assessment left open."""

    assert controlled_report.baseline_recommendation == (
        RecommendationMode.INVESTIGATE_FURTHER.value
    )
    statuses = {
        gate.gate: (gate.baseline_status, gate.successor_status)
        for gate in controlled_report.gate_differences
    }
    assert statuses["technical_fit"][0] == "failed"


def test_an_unestablished_baseline_check_is_not_rendered_as_not_met(
    controlled_report,
) -> None:
    narrative = build_controlled_reassessment_narrative(controlled_report)
    lines = narrative.gate_differences
    technical_fit = next(line for line in lines if line.startswith("Technical fit:"))
    assert technical_fit.startswith(f"Technical fit: {UNESTABLISHED} →")
    assert "Not met" not in "\n".join(lines)
    # The whole business layer is free of the misleading phrase for this report.
    assert "Not met" not in "\n".join(narrative.business_lines())


def test_a_genuinely_negative_outcome_still_renders_as_not_met(
    controlled_report,
) -> None:
    """The same report, read as a side whose outcome was actually decided."""

    negative = dataclasses.replace(
        controlled_report,
        baseline_recommendation=RecommendationMode.DO_NOT_RECOMMEND.value,
    )
    lines = build_controlled_reassessment_narrative(negative).gate_differences
    technical_fit = next(line for line in lines if line.startswith("Technical fit:"))
    assert technical_fit.startswith("Technical fit: Not met →")
    assert UNESTABLISHED not in technical_fit


def test_each_side_of_the_comparison_is_named_for_its_own_outcome(
    controlled_report,
) -> None:
    """A failed successor check on an unestablished successor reads the same way."""

    swapped = dataclasses.replace(
        controlled_report,
        baseline_recommendation=RecommendationMode.DO_NOT_RECOMMEND.value,
        successor_recommendation=RecommendationMode.INVESTIGATE_FURTHER.value,
        gate_differences=tuple(
            dataclasses.replace(gate, successor_status="failed")
            for gate in controlled_report.gate_differences
        ),
    )
    lines = build_controlled_reassessment_narrative(swapped).gate_differences
    technical_fit = next(line for line in lines if line.startswith("Technical fit:"))
    # Baseline side keeps the negative wording; successor side takes the
    # unestablished wording. The two sides are named independently.
    assert technical_fit == f"Technical fit: Not met → {UNESTABLISHED}"


def test_an_unrecorded_status_is_still_reported_as_not_recorded(
    controlled_report,
) -> None:
    missing = dataclasses.replace(
        controlled_report,
        gate_differences=tuple(
            dataclasses.replace(gate, successor_status=None)
            for gate in controlled_report.gate_differences
        ),
    )
    lines = build_controlled_reassessment_narrative(missing).gate_differences
    assert all(line.endswith("Not recorded") for line in lines)


# ---------------------------------------------------------------------------
# Cross-surface consistency, and traceability
# ---------------------------------------------------------------------------


def test_the_report_reuses_the_verb_phrase_the_other_surfaces_use(
    tmp_path, monkeypatch
) -> None:
    """The report's wording is the one the other surfaces already use.

    The bundled decision-variety fixture has exactly one activity the
    assessment left open, so its Decision Package sentence is the reference
    wording for this situation.
    """

    from tests.integration.test_demo_fixtures import _run_fixture

    _, _, package = _run_fixture(tmp_path, "decision-variety", monkeypatch)
    open_item = next(
        item
        for item in package.portfolio.items
        if item.recommendation_mode is RecommendationMode.INVESTIGATE_FURTHER
    )
    statement = portfolio_reason_statement(open_item)
    assert "could not be completed" in statement.lower()
    assert "not met" not in statement.lower()
    # The controlled report now says the same thing about the same situation.
    assert "could not be completed" in UNESTABLISHED.lower()


def test_raw_gate_tokens_remain_in_the_technical_appendix(controlled_report) -> None:
    narrative = build_controlled_reassessment_narrative(controlled_report)
    technical = "\n".join(narrative.technical)
    for gate in controlled_report.gate_differences:
        assert (
            f"Gate {gate.gate}: {gate.baseline_status} -> {gate.successor_status}"
            in technical
        )
    assert f"Baseline recommendation: {controlled_report.baseline_recommendation}" in technical
    assert f"Successor recommendation: {controlled_report.successor_recommendation}" in technical
    # The raw tokens are absent from the business layer, which is why the
    # business layer needs a careful name for them.
    business = "\n".join(narrative.business_lines())
    assert "failed" not in business
    assert "not_evaluated" not in business


def test_the_projection_changes_no_persisted_value(controlled_report) -> None:
    before = dataclasses.asdict(controlled_report)
    build_controlled_reassessment_narrative(controlled_report)
    assert dataclasses.asdict(controlled_report) == before
