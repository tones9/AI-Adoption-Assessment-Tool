"""The Decision Continuation Workspace is a continuation decision page.

Layer 1 - the current official decision, whether anything is required, and the
three options - must be readable before anything is opened.  Baseline, lineage,
hashes and run identifiers stay reachable behind the canonical technical
control.

Scope note: the controlled reassessment report rendered for a completed run is
paired with ``controlled_reassessment_report.py``, which this stage may not
modify, so vocabulary assertions address the page above that report.
"""

from __future__ import annotations

import pathlib
import sqlite3

from ai_adoption_engine.presentation.components.technical_details import (
    TECHNICAL_DETAILS_LABEL,
)
from tests.fakes.m2_reassessment import package_ready_m2_baseline
from tests.ui.test_decision_continuation_ui import (
    _completed_m2_successor,
    _dcw_app,
    _package_ready_m1_baseline,
    _package_ready_m2_successor_without_comparison,
)


def _mark_run_stale(database: pathlib.Path, run_id: str) -> None:
    """Drive a run into a terminal stage exactly as the lifecycle test does."""

    connection = sqlite3.connect(database)
    connection.execute(
        "UPDATE reassessment_runs SET stage='STALE' WHERE run_id=?", (run_id,)
    )
    connection.commit()
    connection.close()


# Widget state is not page text: AppTest exposes a selectbox's raw option value,
# while the reader sees the formatted label.  Buttons are asserted through
# ``app.button`` instead.
_WIDGETS = {
    "Button",
    "Checkbox",
    "DateInput",
    "DownloadButton",
    "FileUploader",
    "Multiselect",
    "NumberInput",
    "Radio",
    "Selectbox",
    "SelectSlider",
    "Slider",
    "TextArea",
    "TextInput",
    "TimeInput",
    "Toggle",
}


def _split_layers(app) -> tuple[list[str], list[str]]:
    """Return (visible-by-default text, text behind the technical control)."""

    layer_one: list[str] = []
    layer_two: list[str] = []

    def collect(block, sink: list[str]) -> None:
        for element in getattr(block, "children", {}).values():
            if getattr(element, "type", None) == "expander":
                target = (
                    layer_two
                    if getattr(element, "label", "") == TECHNICAL_DETAILS_LABEL
                    else sink
                )
                collect(element, target)
                continue
            if hasattr(element, "children"):
                collect(element, sink)
                continue
            if type(element).__name__ in _WIDGETS:
                continue
            value = str(getattr(element, "value", "") or "").strip()
            if value:
                sink.append(value)

    collect(app.main, layer_one)
    return layer_one, layer_two


def _before_controlled_report(layer_one: list[str]) -> str:
    """The part of the page this stage owns."""

    for index, line in enumerate(layer_one):
        if line == "Controlled reassessment decision report":
            return "\n".join(layer_one[:index])
    return "\n".join(layer_one)


def _m2_app(tmp_path, monkeypatch):
    repository, assessment_id = package_ready_m2_baseline(tmp_path)
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(repository.path))
    return _dcw_app(assessment_id)


def _m1_app(tmp_path, monkeypatch):
    repository, assessment_id = _package_ready_m1_baseline(tmp_path)
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(repository.path))
    return _dcw_app(assessment_id)


# ---------------------------------------------------------------------------
# A. The current decision comes first
# ---------------------------------------------------------------------------


def test_page_opens_with_the_current_official_decision(tmp_path, monkeypatch) -> None:
    app = _m2_app(tmp_path, monkeypatch)
    assert not app.exception

    layer_one, layer_two = _split_layers(app)
    headings = [item.value for item in app.subheader]
    assert headings[:5] == [
        "Your current official decision",
        "What your decision covers",
        "What this page is for",
        "Do you need to do anything?",
        "Your options",
    ]
    assert layer_one[1].startswith("Current official decision · ")
    assert (
        "This is the decision produced from the evidence that has already been "
        "reviewed and approved."
    ) in "\n".join(layer_one)
    # The internal vocabulary never leads the page.
    assert "active formal baseline" not in "\n".join(layer_one)
    assert layer_two, "technical lineage must still be rendered"


def test_decision_summary_is_the_package_projection_not_a_second_system(
    tmp_path, monkeypatch
) -> None:
    from ai_adoption_engine.presentation.decision_narrative import (
        build_package_narrative,
    )
    from ai_adoption_engine.persistence.sqlite import SQLiteAssessmentRepository
    from ai_adoption_engine.workspace.models import ArtifactType

    repository, assessment_id = package_ready_m2_baseline(tmp_path)
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(repository.path))
    workspace = SQLiteAssessmentRepository(repository.path).load_workspace(assessment_id)
    package = workspace.active_artifacts[ArtifactType.DECISION_PACKAGE_RESULT].payload.package
    narrative = build_package_narrative(package)

    layer_one, _ = _split_layers(_dcw_app(assessment_id))
    visible = "\n".join(layer_one)

    assert narrative.headline in visible
    for line in narrative.outcome_groups:
        assert line in visible


# ---------------------------------------------------------------------------
# B. Continuation is optional
# ---------------------------------------------------------------------------


def test_the_user_is_told_they_can_stop_here(tmp_path, monkeypatch) -> None:
    app = _m2_app(tmp_path, monkeypatch)
    layer_one, _ = _split_layers(app)
    visible = "\n".join(layer_one)

    assert (
        "No. The decision above is complete and stays your official decision."
        in visible
    )
    assert "Option A — Keep the current decision" in visible
    assert (
        "You can stop here. Nothing else is required and nothing changes" in visible
    )
    assert "No action is needed to choose this option." in visible
    assert "Everything on this page is optional." in visible

    # Option A is stated, never faked as a transaction.
    labels_seen = [item.label for item in app.button]
    assert "Continue with current recommendation" not in labels_seen
    for label in labels_seen:
        assert "keep" not in label.lower()


# ---------------------------------------------------------------------------
# C. GRW M1 cannot change the decision
# ---------------------------------------------------------------------------


def test_m1_is_presented_as_non_decision_affecting(tmp_path, monkeypatch) -> None:
    app = _m1_app(tmp_path, monkeypatch)
    layer_one, _ = _split_layers(app)
    visible = "\n".join(layer_one)

    assert "Option B — Add preliminary context" in visible
    assert (
        "This cannot change the decision above. It does not change the assessment "
        "criteria, the checks, the scores, the recommendation, the priority, or "
        "the Decision Package."
    ) in visible
    assert "Add preliminary context" in [item.label for item in app.button]
    assert (
        "Opens the Gap resolution page, where you write the answer and a reviewer "
        "records what it may be used for."
    ) in visible

    lowered = visible.lower()
    for implication in ("reassessment will", "new recommendation", "updates the decision"):
        assert implication not in lowered


# ---------------------------------------------------------------------------
# D. GRW M2 is controlled, separate, and not a promise
# ---------------------------------------------------------------------------


def test_m2_states_requirements_separateness_and_no_guarantee(
    tmp_path, monkeypatch
) -> None:
    app = _m2_app(tmp_path, monkeypatch)
    layer_one, _ = _split_layers(app)
    visible = "\n".join(layer_one)

    assert "Option C — Controlled reassessment" in visible
    assert "A reviewed supporting document" in visible
    assert "A reviewed resolution of the open question" in visible
    assert "Explicit approval to reassess" in visible
    assert (
        "a separate successor Decision Package is created next to the decision "
        "above. The decision above is not replaced and not edited."
    ) in visible
    assert (
        "Supplying more evidence does not guarantee a different recommendation."
        in visible
    )
    assert "Review controlled reassessment" in [item.label for item in app.button]


def test_m2_absence_is_explained_without_offering_the_route(
    tmp_path, monkeypatch
) -> None:
    app = _m1_app(tmp_path, monkeypatch)
    layer_one, _ = _split_layers(app)
    visible = "\n".join(layer_one)

    assert (
        "Option C — Controlled reassessment is not available for this decision."
        in visible
    )
    assert "What this route requires" not in visible
    assert "Review controlled reassessment" not in [item.label for item in app.button]


# ---------------------------------------------------------------------------
# E. Technical traceability preserved but collapsed
# ---------------------------------------------------------------------------


def test_lineage_and_identifiers_stay_behind_the_canonical_control(
    tmp_path, monkeypatch
) -> None:
    from ai_adoption_engine.presentation.context import decision_continuation_service

    repository, assessment_id = package_ready_m2_baseline(tmp_path)
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(repository.path))
    view = decision_continuation_service().open(assessment_id)
    baseline = view.baseline

    layer_one, layer_two = _split_layers(_dcw_app(assessment_id))
    technical = "\n".join(layer_two)
    visible = _before_controlled_report(layer_one)

    for token in (
        baseline.package_id,
        baseline.package.artifact_id,
        baseline.package.payload_sha256,
        baseline.approved_review.artifact_id,
        baseline.integrated_assessment.artifact_id,
        baseline.policy_id,
        baseline.policy_fingerprint,
        baseline.package_completeness,
        baseline.assessment_id,
    ):
        assert token in technical, token
        assert token not in visible, token

    assert {item.label for item in _dcw_app(assessment_id).expander} == {
        TECHNICAL_DETAILS_LABEL
    }


# ---------------------------------------------------------------------------
# F. Every action names its consequence
# ---------------------------------------------------------------------------


def test_every_action_states_what_it_does(tmp_path, monkeypatch) -> None:
    consequences = {
        "Add preliminary context": "Opens the Gap resolution page",
        "Review controlled reassessment": "Opens the Reassessment page",
        "Resume controlled reassessment": "Opens the Reassessment page at the step",
    }
    for builder in (_m1_app, _m2_app):
        app = builder(tmp_path / builder.__name__, monkeypatch)
        layer_one, _ = _split_layers(app)
        visible = "\n".join(layer_one)
        for button in app.button:
            assert button.label in consequences, button.label
            assert consequences[button.label] in visible, button.label


# ---------------------------------------------------------------------------
# G. Persisted run behaviour is unchanged
# ---------------------------------------------------------------------------


def test_resumable_run_still_resumes_and_terminal_run_still_does_not(
    tmp_path, monkeypatch
) -> None:
    repository, assessment_id, run_id = _package_ready_m2_successor_without_comparison(
        tmp_path / "resumable"
    )
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(repository.path))
    app = _dcw_app(assessment_id)
    layer_one, layer_two = _split_layers(app)

    assert "Previous reassessments" in layer_one
    assert "Resume controlled reassessment" in [item.label for item in app.button]
    assert (
        "Opens the Reassessment page at the step this record reached."
        in "\n".join(layer_one)
    )
    assert run_id in "\n".join(layer_two)
    assert run_id not in _before_controlled_report(layer_one)

    _mark_run_stale(repository.path, run_id)
    stopped = _dcw_app(assessment_id)
    stopped_layer_one, _ = _split_layers(stopped)
    assert "Resume controlled reassessment" not in [
        item.label for item in stopped.button
    ]
    assert (
        "This reassessment record is complete or stopped and is available for "
        "inspection only." in "\n".join(stopped_layer_one)
    )


# ---------------------------------------------------------------------------
# H. Successor and comparison stay neutral
# ---------------------------------------------------------------------------


def test_successor_and_comparison_use_neutral_language(tmp_path, monkeypatch) -> None:
    repository, assessment_id, _ = _completed_m2_successor(tmp_path)
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(repository.path))
    layer_one, _ = _split_layers(_dcw_app(assessment_id))
    visible = _before_controlled_report(layer_one)

    assert (
        "A separate reassessment was produced using additional approved evidence."
        in visible
    )
    assert (
        "This separate decision sits alongside your current official decision. It "
        "does not replace it and the decision above is unchanged." in visible
    )
    assert "How the two decisions compare" in visible
    assert (
        "A difference between the two is not a measured outcome, a Return on "
        "Investment (ROI) result, a deployment approval, or evidence that adoption "
        "succeeded." in visible
    )

    for sentence in visible.split("."):
        lowered = sentence.lower()
        for framing in ("improved", "better", "upgraded", "successful"):
            assert framing not in lowered, sentence
