from __future__ import annotations

import re

import pytest

from ai_adoption_engine.models.four_gate_assessment import OutcomeCode
from ai_adoption_engine.models.four_gate_decision_support import (
    FourGateInformationGapKind,
    FourGateReportSectionId,
)
from ai_adoption_engine.presentation import labels
from ai_adoption_engine.presentation.contracts import (
    UnsupportedPresentationContract,
    phase5_presentation_contract,
    phase6_presentation_contract,
)
from ai_adoption_engine.presentation.four_gate_narrative import (
    build_four_gate_package_narrative,
    build_four_gate_process_narrative,
)
from ai_adoption_engine.presentation.report_html import render_report_html
from ai_adoption_engine.presentation.report_view import build_report_view
from tests.unit.test_four_gate_decision_support_package import (
    _integrated,
    _package,
)


@pytest.mark.parametrize(
    ("scenario", "outcome"),
    [
        ("no_change", OutcomeCode.NO_CHANGE_JUSTIFIED),
        ("ai_automation", OutcomeCode.AI_AUTOMATION),
        ("ai_assisted", OutcomeCode.AI_ASSISTED_WORK),
        ("conventional", OutcomeCode.CONVENTIONAL_AUTOMATION),
        ("process_improvement", OutcomeCode.PROCESS_IMPROVEMENT_FIRST),
        ("human_led", OutcomeCode.KEEP_HUMAN_LED),
        ("discovery", OutcomeCode.DISCOVERY_REQUIRED),
    ],
)
def test_all_seven_outcomes_have_consistent_narrative_view_and_html(
    scenario,
    outcome,
) -> None:
    integrated = _integrated(scenario)
    package = _package(scenario)
    process_narrative = build_four_gate_process_narrative(integrated)
    package_narrative = build_four_gate_package_narrative(package)
    view = build_report_view(package)
    html = render_report_html(package)
    label = labels.four_gate_outcome_label(outcome.value)

    assert process_narrative.activities[0].outcome_code == outcome.value
    assert process_narrative.activities[0].outcome_label == label
    assert label in process_narrative.headline
    assert label in package_narrative.headline
    assert label in html
    assert [section.section_id for section in view] == list(
        FourGateReportSectionId
    )
    assert len(view) == 13
    portfolio = next(
        section
        for section in view
        if section.section_id
        is FourGateReportSectionId.ACTIVITY_DECISION_PORTFOLIO
    )
    assert f"Final decision: {label}" in portfolio.blocks[0].paragraphs
    assert len(process_narrative.activities[0].gates) == 4


def test_path_specific_gaps_and_not_evaluated_meaning_are_preserved() -> None:
    process_first = _package("process_improvement")
    view = build_report_view(process_first)
    missing = next(
        section
        for section in view
        if section.section_id is FourGateReportSectionId.MISSING_INFORMATION
    )
    by_heading = {block.heading: block.bullets for block in missing.blocks}
    assert by_heading["Active decision blockers"] == (
        "No gaps in this classification.",
    )
    assert any("repetition" in item for item in by_heading["Contextual information"])
    visible = "\n".join(
        text
        for section in view
        for block in section.blocks
        for text in (*block.paragraphs, *block.bullets)
    )
    assert "established Gate 2 blocker(s): data_readiness" in visible
    assert "missing information caused" not in visible.lower()

    process_narrative = build_four_gate_process_narrative(
        _integrated("no_change")
    )
    gates = process_narrative.activities[0].gates
    assert [gate.was_reached for gate in gates] == [True, False, False, False]
    assert all(
        gate.status_label
        == "Not evaluated — an earlier gate determined the path"
        for gate in gates[1:]
    )


def test_outcome_wording_guards_are_unambiguous() -> None:
    no_change = build_four_gate_package_narrative(_package("no_change"))
    assert "human-led" not in " ".join(no_change.why).lower()

    conventional = build_four_gate_package_narrative(_package("conventional"))
    conventional_text = " ".join(conventional.why)
    assert "AI fit" not in conventional_text
    assert "missing" not in conventional_text.lower()

    veto_package = _package("safety_veto")
    veto = build_four_gate_package_narrative(veto_package)
    result_veto = build_four_gate_process_narrative(
        _integrated("safety_veto")
    ).activities[0]
    veto_text = " ".join((veto.headline, *veto.why))
    assert "AI was selected as the Gate 3 candidate" in veto_text
    assert "rejected by the Gate 4 safety veto" in veto_text
    assert "sole final recommendation" in veto_text
    assert result_veto.reason_statement == (
        veto_package.portfolio.items[0].final_recommendation
    )
    assert "final decision: AI Automation" not in render_report_html(veto_package)


def test_discovery_section_contains_only_active_blockers() -> None:
    package = _package("discovery")
    view = build_report_view(package)
    discovery = next(
        section
        for section in view
        if section.section_id is FourGateReportSectionId.DISCOVERY_REQUIRED
    )
    discovery_text = " ".join(
        text
        for block in discovery.blocks
        for text in (*block.paragraphs, *block.bullets)
    )
    active_messages = {
        gap.message
        for gap in package.missing_information
        if gap.kind is FourGateInformationGapKind.ACTIVE_DECISION_BLOCKER
    }
    other_messages = {
        gap.message
        for gap in package.missing_information
        if gap.kind is not FourGateInformationGapKind.ACTIVE_DECISION_BLOCKER
    }
    assert active_messages
    assert all(message in discovery_text for message in active_messages)
    assert all(message not in discovery_text for message in other_messages)


def test_html_is_deterministic_escaped_and_keeps_disclosures() -> None:
    package = _package("ai_automation")
    first = render_report_html(package)
    assert first == render_report_html(package)
    assert "provisional" in first.lower()
    assert "not academically validated" in first.lower()
    assert "decision support only" in first.lower()
    assert "Nothing in it has been deployed" in first
    assert package.source.policy.decision_policy_fingerprint in first
    assert re.search(r"<section id='executive-summary'>", first)


def test_unknown_phase6_contract_fails_closed() -> None:
    package = _package().model_copy(
        update={"package_schema_version": "phase6-v9"}
    )
    with pytest.raises(UnsupportedPresentationContract):
        phase6_presentation_contract(package)
    with pytest.raises(UnsupportedPresentationContract):
        build_report_view(package)
    with pytest.raises(UnsupportedPresentationContract):
        render_report_html(package)


def test_unknown_phase5_contract_fails_closed() -> None:
    integrated = _integrated()
    metadata = integrated.metadata.model_copy(
        update={"integration_schema_version": "phase5-v9"}
    )
    unsupported = integrated.model_copy(update={"metadata": metadata})
    with pytest.raises(UnsupportedPresentationContract):
        phase5_presentation_contract(unsupported)
    with pytest.raises(UnsupportedPresentationContract):
        build_four_gate_process_narrative(unsupported)
