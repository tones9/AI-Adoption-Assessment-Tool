"""Assessment Results is a business decision page, not a results console.

These tests assert the Stage 3 hierarchy structurally: what a non-technical
reader sees before opening anything (Layer 1), what stays available behind the
canonical technical control (Layer 2), and that nothing crosses between them.
"""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from ai_adoption_engine.persistence.sqlite import SQLiteAssessmentRepository
from ai_adoption_engine.presentation.components.technical_details import (
    TECHNICAL_DETAILS_LABEL,
)
from ai_adoption_engine.workspace.models import (
    ArtifactType,
    ExecutionMode,
    WorkflowStage,
)
from tests.fakes.decision_support import sample_integrated_assessment
from tests.fakes.review import approved_review


ROOT = Path(__file__).resolve().parents[2]


def _results_app(tmp_path, monkeypatch, *, integrated=None) -> AppTest:
    path = tmp_path / "results-decision-first.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    repository = SQLiteAssessmentRepository(path)
    assessment = repository.create_assessment("Decision first", ExecutionMode.OFFLINE_DEMO)
    approval = repository.save_artifact_and_advance(
        assessment.assessment_id,
        ArtifactType.APPROVED_REVIEW,
        approved_review(),
        artifact_schema_version="phase4-v0.1",
        stage=WorkflowStage.APPROVED,
    )
    repository.save_artifact_and_advance(
        assessment.assessment_id,
        ArtifactType.INTEGRATED_ASSESSMENT_RESULT,
        integrated if integrated is not None else sample_integrated_assessment(),
        artifact_schema_version="phase5-v0.1",
        stage=WorkflowStage.ASSESSED,
        parent_artifact_id=approval.artifact_id,
    )
    return AppTest.from_string(
        "import streamlit as st\n"
        f"st.session_state.selected_assessment_id = {assessment.assessment_id!r}\n"
        "from ai_adoption_engine.presentation.pages.results import render\nrender()",
        default_timeout=60,
    ).run()


def _incomplete_priority_assessment():
    integrated = sample_integrated_assessment()
    payload = integrated.model_dump(mode="json")
    first = payload["process_assessment"]["step_assessments"][0]
    first["priority"] = None
    first["priority_status"] = "incomplete"
    first["priority_missing_criteria"] = ["repetition"]
    return integrated.__class__.model_validate(payload)


def _text(element) -> str:
    return str(getattr(element, "value", "") or getattr(element, "label", "") or "")


def _split_layers(app) -> tuple[list[str], list[str]]:
    """Return (visible-by-default text, text behind a technical expander)."""

    layer_one: list[str] = []
    layer_two: list[str] = []

    def collect(block, sink: list[str]) -> None:
        for element in getattr(block, "children", {}).values():
            if getattr(element, "type", None) == "expander":
                collect(element, layer_two)
                continue
            if hasattr(element, "children"):
                collect(element, sink)
                continue
            value = _text(element).strip()
            if value:
                sink.append(value)

    collect(app.main, layer_one)
    return layer_one, layer_two


# ---------------------------------------------------------------------------
# A. Decision-first hierarchy
# ---------------------------------------------------------------------------


def test_results_leads_with_the_decision_not_the_pipeline(tmp_path, monkeypatch) -> None:
    app = _results_app(tmp_path, monkeypatch)
    assert not app.exception

    layer_one, _ = _split_layers(app)
    joined = "\n".join(layer_one)

    assert "Deterministic assessment completed" not in joined
    assert "not system failures" not in joined

    headings = [item.value for item in app.subheader]
    assert headings == [
        "Decision today",
        "What we found",
        "What information is still needed",
        "What this means",
        "What happens next",
        "Activity-by-activity results",
    ]

    headline_index = next(
        index
        for index, line in enumerate(layer_one)
        if "mixed result" in line
    )
    activities_index = layer_one.index("Activity-by-activity results")
    counts_index = layer_one.index("Supporting numbers")
    assert headline_index < counts_index < activities_index
    assert layer_one[1].startswith("Assessment complete · ")


def test_counts_are_supporting_data_not_the_conclusion(tmp_path, monkeypatch) -> None:
    app = _results_app(tmp_path, monkeypatch)
    layer_one, _ = _split_layers(app)

    headline = next(line for line in layer_one if "mixed result" in line)
    assert not any(character.isdigit() for character in headline)
    assert "Supporting numbers" in layer_one
    assert {item.label for item in app.metric} == {
        "Activities assessed",
        "Automate",
        "Augment",
        "Investigate",
        "Do not recommend",
    }


# ---------------------------------------------------------------------------
# B. INVESTIGATE_FURTHER wording
# ---------------------------------------------------------------------------


def test_investigate_further_is_specific_without_inventing_sub_gaps(
    tmp_path, monkeypatch
) -> None:
    app = _results_app(tmp_path, monkeypatch)
    layer_one, _ = _split_layers(app)
    joined = "\n".join(layer_one)

    assert (
        "More information is needed before an AI adoption recommendation can be "
        "made for this activity."
    ) in joined
    assert (
        "the available evidence does not establish whether the data this activity "
        "relies on is ready for AI use"
    ) in joined

    lowered = joined.lower()
    for invented in ("data quality", "accuracy threshold", "exception handling", "data is poor", "not ready"):
        assert invented not in lowered


# ---------------------------------------------------------------------------
# C. Mixed outcomes are scannable without a detail selector
# ---------------------------------------------------------------------------


def test_every_activity_outcome_is_readable_without_a_selectbox(
    tmp_path, monkeypatch
) -> None:
    app = _results_app(tmp_path, monkeypatch)
    layer_one, _ = _split_layers(app)
    joined = "\n".join(layer_one)

    assert not app.selectbox

    integrated = sample_integrated_assessment()
    for step in integrated.process_assessment.step_assessments:
        assert step.activity in joined

    for outcome in ("**Automate**", "**Augment**", "**More information needed**", "**Not recommended**"):
        assert outcome in joined


# ---------------------------------------------------------------------------
# D. Technical preservation and relocation
# ---------------------------------------------------------------------------


def test_technical_detail_is_preserved_behind_the_canonical_control(
    tmp_path, monkeypatch
) -> None:
    app = _results_app(tmp_path, monkeypatch)
    layer_one, layer_two = _split_layers(app)
    visible = "\n".join(layer_one)
    technical = "\n".join(layer_two)
    integrated = sample_integrated_assessment()

    assert app.expander
    assert {item.label for item in app.expander} == {TECHNICAL_DETAILS_LABEL}

    investigate = next(
        step
        for step in integrated.process_assessment.step_assessments
        if step.recommendation_mode.value == "INVESTIGATE_FURTHER"
    )
    for gate in investigate.gate_results:
        assert gate.rationale in technical
        assert gate.rationale not in visible
    for reason in investigate.reasoning:
        assert reason in technical

    for token in (
        "data_readiness",
        "INVESTIGATE_FURTHER",
        "material_to_recommendation",
        integrated.policy.policy_id,
        integrated.metadata.assessment_run_id,
        investigate.step_id,
    ):
        assert token in technical
        assert token not in visible

    evidence = investigate.evidence[0]
    assert evidence.source_locator in technical
    assert evidence.evidence_id in technical


# ---------------------------------------------------------------------------
# E. Priority stays subordinate
# ---------------------------------------------------------------------------


def test_incomplete_priority_is_explained_and_never_leads(tmp_path, monkeypatch) -> None:
    app = _results_app(
        tmp_path, monkeypatch, integrated=_incomplete_priority_assessment()
    )
    assert not app.exception
    layer_one, _ = _split_layers(app)
    joined = "\n".join(layer_one)

    assert (
        "A priority score could not be calculated because the available evidence "
        "does not establish: Task repetition."
    ) in joined

    card_start = next(
        index
        for index, line in enumerate(layer_one)
        if line.startswith("**1. ")
    )
    outcome_index = next(
        index
        for index, line in enumerate(layer_one[card_start:], start=card_start)
        if line.startswith("**Automate**")
    )
    priority_index = next(
        index
        for index, line in enumerate(layer_one[card_start:], start=card_start)
        if line.startswith("A priority score could not be calculated")
    )
    assert card_start < outcome_index < priority_index


def test_priority_is_hidden_where_it_carries_no_meaning(tmp_path, monkeypatch) -> None:
    app = _results_app(tmp_path, monkeypatch)
    layer_one, _ = _split_layers(app)

    assert "Priority scoring does not apply to this outcome." not in layer_one
    assert any(line.startswith("Priority score ") for line in layer_one)


# ---------------------------------------------------------------------------
# F. No raw technical vocabulary above the business layer
# ---------------------------------------------------------------------------


def test_no_raw_engine_vocabulary_reaches_the_business_layer(
    tmp_path, monkeypatch
) -> None:
    app = _results_app(tmp_path, monkeypatch)
    layer_one, _ = _split_layers(app)
    visible = "\n".join(layer_one)
    integrated = sample_integrated_assessment()

    for token in (
        "AUTOMATE",
        "AUGMENT",
        "DO_NOT_RECOMMEND",
        "INVESTIGATE_FURTHER",
        "technical_fit",
        "risk_and_autonomy",
        "evidence_sufficiency",
        "not_evaluated",
        "passed_with_constraints",
        "priority_status",
        "human_accountability_required",
        "decision_policy",
        integrated.metadata.assessment_run_id,
        integrated.lineage.validated_process_fingerprint,
    ):
        assert token not in visible


def test_next_action_offers_a_named_destination(tmp_path, monkeypatch) -> None:
    app = _results_app(tmp_path, monkeypatch)

    labels = [item.label for item in app.button]
    assert "Open the Decision Package" in labels
    assert not any(label.strip().lower() in {"continue", "continue decision"} for label in labels)
