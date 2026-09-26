from __future__ import annotations

from streamlit.testing.v1 import AppTest

from ai_adoption_engine.decision_support.four_gate_service import (
    FourGateDecisionSupportPackageService,
)
from ai_adoption_engine.models.four_gate_decision_support import (
    FourGateDecisionPackageSuccess,
)
from ai_adoption_engine.persistence.four_gate import FourGatePersistenceAdapter
from ai_adoption_engine.persistence.sqlite import SQLiteAssessmentRepository
from ai_adoption_engine.presentation.components.technical_details import (
    TECHNICAL_DETAILS_LABEL,
)
from ai_adoption_engine.presentation.four_gate_ui import (
    SUCCESSOR_PACKAGE_SECTIONS,
)
from ai_adoption_engine.workspace.models import ExecutionMode
from tests.fakes.review import approved_review
from tests.unit.test_four_gate_decision_support_package import _integrated
from tests.unit.test_four_gate_persistence import _save_approval


def _persisted_successor(tmp_path, monkeypatch, scenario, *, package=False):
    path = tmp_path / f"successor-{scenario}.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    integrated = _integrated(scenario)
    repository = SQLiteAssessmentRepository(path)
    adapter = FourGatePersistenceAdapter(repository)
    assessment = adapter.create_assessment(
        "Successor presentation",
        ExecutionMode.OFFLINE_DEMO,
        policy_fingerprint=integrated.policy.decision_policy_fingerprint,
    )
    approval = _save_approval(repository, assessment.assessment_id, approved_review())
    integrated_reference = adapter.persist_integrated_assessment(
        assessment.assessment_id,
        integrated,
        approved_artifact_id=approval.artifact_id,
    )
    if package:
        generated = FourGateDecisionSupportPackageService().generate(integrated)
        assert isinstance(generated, FourGateDecisionPackageSuccess)
        adapter.persist_decision_package(
            assessment.assessment_id,
            generated,
            integrated_artifact_id=integrated_reference.artifact_id,
        )
    return assessment.assessment_id


def _app(page, assessment_id):
    return AppTest.from_string(
        "import streamlit as st\n"
        f"st.session_state.selected_assessment_id = {assessment_id!r}\n"
        f"from ai_adoption_engine.presentation.pages.{page} import render\n"
        "render()",
        default_timeout=90,
    ).run()


def _text(element) -> str:
    return str(getattr(element, "value", "") or getattr(element, "label", "") or "")


def _layers(app):
    visible = []
    technical = []

    def collect(block, sink):
        for element in getattr(block, "children", {}).values():
            if getattr(element, "type", None) == "expander":
                collect(
                    element,
                    technical
                    if getattr(element, "label", "") == TECHNICAL_DETAILS_LABEL
                    else sink,
                )
            elif hasattr(element, "children"):
                collect(element, sink)
            else:
                value = _text(element).strip()
                if value and not value.startswith("<style>"):
                    sink.append(value)

    collect(app.main, visible)
    return "\n".join(visible), "\n".join(technical)


def test_successor_results_show_four_gates_typed_fields_and_safety_veto(
    tmp_path,
    monkeypatch,
) -> None:
    assessment_id = _persisted_successor(
        tmp_path,
        monkeypatch,
        "safety_veto",
    )
    app = _app("results", assessment_id)
    assert not app.exception
    visible, technical = _layers(app)

    assert "Keep Human-Led is the sole final recommendation" in visible
    assert "AI was selected as the Gate 3 candidate" in visible
    assert "rejected by the Gate 4 safety" in visible
    assert {metric.label for metric in app.metric} == {
        "Activities assessed",
        "No Change Justified",
        "AI Automation",
        "AI-Assisted Work",
        "Conventional Automation",
        "Process Improvement First",
        "Keep Human-Led",
        "Discovery Required",
    }
    for gate in (
        "Gate 1 — Should we change?",
        "Gate 2 — Is it ready?",
        "Gate 3 — Best intervention",
        "Gate 4 — Safe autonomy",
    ):
        assert gate in technical
    for field in (
        "decision_status: COMPLETE",
        "change_disposition: CHANGE_JUSTIFIED",
        "readiness_disposition: READY_FOR_INTERVENTION_SELECTION",
        "selected_intervention_family: AI",
        "autonomy_ceiling: AI_NOT_PERMITTED",
        "outcome_code (derived): KEEP_HUMAN_LED",
    ):
        assert field in technical
    assert "decision_policy.v0.3" not in visible
    assert not any(
        button.label == "Run AI-adoption assessment" for button in app.button
    )


def test_successor_results_separate_context_priority_and_not_evaluated(
    tmp_path,
    monkeypatch,
) -> None:
    assessment_id = _persisted_successor(
        tmp_path,
        monkeypatch,
        "process_improvement",
    )
    app = _app("results", assessment_id)
    assert not app.exception
    visible, technical = _layers(app)

    assert "Process Improvement First" in visible
    assert "Established Gate 2 blocker evidence: Data readiness" in visible
    assert "Contextual information" in visible
    assert "Priority-only information" in visible
    assert "Priority status: Not applicable" in visible
    assert "Active decision blockers" in visible
    assert "No active decision blocker is recorded" in visible
    assert technical.count("Not evaluated — an earlier gate determined the path") == 2


def test_successor_results_keep_incomplete_priority_separate_from_decision(
    tmp_path,
    monkeypatch,
) -> None:
    assessment_id = _persisted_successor(
        tmp_path,
        monkeypatch,
        "priority_incomplete",
    )
    app = _app("results", assessment_id)
    assert not app.exception
    visible, technical = _layers(app)

    assert "AI Automation" in visible
    assert "Priority status: Incomplete" in visible
    assert "Priority-only information" in visible
    assert "repetition" in visible.lower()
    assert "decision_status: COMPLETE" in technical


def test_successor_decision_package_renders_existing_package_without_actions(
    tmp_path,
    monkeypatch,
) -> None:
    assessment_id = _persisted_successor(
        tmp_path,
        monkeypatch,
        "safety_veto",
        package=True,
    )
    app = _app("decision_package", assessment_id)
    assert not app.exception
    visible, technical = _layers(app)

    assert tuple(app.segmented_control[0].options) == SUCCESSOR_PACKAGE_SECTIONS
    assert "Keep Human-Led is the sole final recommendation" in visible
    assert "AI was selected as the Gate 3 candidate" in visible
    assert "rejected by the Gate 4 safety veto" in visible
    assert "phase6-v0.2" in technical
    assert "phase1-v0.4" in technical
    assert "four-gate-framework.v0.1" in technical
    assert not any(button.label == "Generate decision package" for button in app.button)

    app = app.segmented_control[0].set_value("Activity decisions").run()
    visible, technical = _layers(app)
    assert "Final decision: Keep Human-Led" in visible
    assert "selected_intervention_family: AI" in technical
    assert "autonomy_ceiling: AI_NOT_PERMITTED" in technical


def test_successor_package_page_does_not_offer_legacy_generation(
    tmp_path,
    monkeypatch,
) -> None:
    assessment_id = _persisted_successor(
        tmp_path,
        monkeypatch,
        "ai_automation",
    )
    app = _app("decision_package", assessment_id)
    assert not app.exception
    visible, _ = _layers(app)
    assert "explicit non-default successor route" in visible
    assert not any(
        button.label == "Generate decision package" for button in app.button
    )


def test_successor_discovery_package_classifies_gaps_in_separate_groups(
    tmp_path,
    monkeypatch,
) -> None:
    assessment_id = _persisted_successor(
        tmp_path,
        monkeypatch,
        "discovery",
        package=True,
    )
    app = _app("decision_package", assessment_id)
    assert not app.exception
    visible, _ = _layers(app)
    assert "Active decision blockers" in visible
    assert "Contextual information" in visible
    assert "Priority-only information" in visible
    assert "business_value" in visible


def test_successor_process_flow_uses_only_the_derived_outcome_label() -> None:
    workflow = _integrated("no_change")
    generated = FourGateDecisionSupportPackageService().generate(workflow)
    assert isinstance(generated, FourGateDecisionPackageSuccess)
    app = AppTest.from_string(
        "from tests.unit.test_four_gate_decision_support_package import _package\n"
        "from ai_adoption_engine.presentation.components.process_flow import "
        "render_future_state\n"
        "render_future_state(_package('no_change').future_state)",
        default_timeout=90,
    ).run()
    assert not app.exception
    visible, _ = _layers(app)
    assert "Final decision: No Change Justified" in visible
    assert "KEEP_HUMAN_LED" not in visible
