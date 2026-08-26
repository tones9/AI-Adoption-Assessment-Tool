"""The controlled reassessment page must read as a journey, not a stage machine.

M2 is a real controlled evidence process, so its operational detail stays: the
reviewer still chooses the authoritative permission and conflict values, and the
document locator still records exact character offsets.  What these tests pin is
orientation — that a reader who opens nothing can see what the page is for, that
their original Decision Package is untouched, the whole path this process
requires, where this run sits in it, what this step asks, what follows, and what
can be produced only after explicit approval.

Every lifecycle state is built by driving the real service, so nothing here
asserts against a hand-made stage string.  No M2 semantics are exercised beyond
what the page renders from the persisted run.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from ai_adoption_engine.grw.m2.models import (
    M2ConflictStatus,
    M2DocumentLocator,
    M2EvidencePermission,
    M2RunStage,
)
from ai_adoption_engine.grw.m2.service import M2ReassessmentService
from ai_adoption_engine.models.enums import KnowledgeState
from ai_adoption_engine.persistence.reassessment import SQLiteReassessmentRepository
from ai_adoption_engine.presentation.components.technical_details import (
    TECHNICAL_DETAILS_LABEL,
)
from ai_adoption_engine.presentation.pages.reassessment import (
    BASELINE_UNCHANGED,
    DOCUMENT_SCOPE,
    END_STATE,
    JOURNEY,
    NO_GUARANTEE,
    PAGE_PURPOSE,
    _TERMINAL_DETAIL,
)
from tests.fakes.m2_reassessment import package_ready_m2_baseline
from tests.integration.test_grw_m2_m1_lifecycle import _actor


SUPPORTING_DOCUMENT = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "m2_data_readiness_supporting_document.txt"
)


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


def _page(assessment_id: str, run_id: str | None = None) -> AppTest:
    script = (
        "import streamlit as st\n"
        f"st.session_state.selected_assessment_id = {assessment_id!r}\n"
    )
    if run_id is not None:
        script += f"st.session_state.grw_m2_run_id = {run_id!r}\n"
    script += (
        "from ai_adoption_engine.presentation.pages.reassessment import render\n"
        "render()\n"
    )
    return AppTest.from_string(script, default_timeout=60).run()


def _advance(tmp_path, stage: str):
    """Drive the real service to one recorded stage and return its page."""

    repository, assessment_id = package_ready_m2_baseline(tmp_path)
    service = M2ReassessmentService(
        repository, SQLiteReassessmentRepository(repository.path)
    )
    if stage == "NO_RUN":
        return repository, assessment_id, None, service
    run_id, _, _ = service.create_run(assessment_id)
    if stage == "OPEN":
        return repository, assessment_id, run_id, service

    payload = SUPPORTING_DOCUMENT.read_bytes()
    text = payload.decode("utf-8")
    service.submit_supporting_document(
        run_id,
        content_bytes=payload,
        filename=SUPPORTING_DOCUMENT.name,
        source_label="Synthetic service operations manager",
        submitter=_actor("submitter"),
    )
    if stage == "DOCUMENT_SUBMITTED":
        return repository, assessment_id, run_id, service

    permission = (
        M2EvidencePermission.REJECTED
        if stage == "EVIDENCE_REJECTED"
        else M2EvidencePermission.CRITERION_RESOLUTION_AND_GATE_ADMISSIBLE
    )
    service.review_document_evidence(
        run_id,
        reviewer=_actor(),
        locator=M2DocumentLocator(
            start_offset=0,
            end_offset=len(text),
            line_start=1,
            line_end=text.count("\n", 0, len(text)) + 1,
            exact_excerpt=text,
        ),
        scope_statement="The document covers the selected categorisation activity.",
        period_statement="January 2025 onward.",
        source_authority="Synthetic service operations manager",
        semantic_rationale="The fields, access and limits support the M2 M1 instrument anchor.",
        limitations="Text quality limitations remain.",
        conflict_status=M2ConflictStatus.CONSISTENT,
        conflict_rationale="No material conflict identified.",
        permission=permission,
    )
    if stage in {"EVIDENCE_REVIEWED", "EVIDENCE_REJECTED"}:
        return repository, assessment_id, run_id, service

    service.propose_data_readiness_resolution(
        run_id,
        proposed_value=3,
        proposed_knowledge_state=KnowledgeState.KNOWN,
        mapping_rationale="The document meets anchor 3; limitations remain explicit.",
        data_owner=_actor("owner"),
        criterion_reviewer=_actor("criterion reviewer"),
    )
    if stage == "RESOLUTION_PROPOSED":
        return repository, assessment_id, run_id, service
    service.request_reassessment(run_id)
    if stage == "REQUESTED":
        return repository, assessment_id, run_id, service
    service.approve_reassessment(
        run_id,
        approver=_actor("approver"),
        rationale="The exact M2 M1 resolution is approved for a separate successor.",
    )
    if stage == "APPROVED":
        return repository, assessment_id, run_id, service
    service.build_successor_review(run_id)
    if stage == "SUCCESSOR_REVIEW_READY":
        return repository, assessment_id, run_id, service
    service.assess_successor(run_id)
    if stage == "ASSESSED":
        return repository, assessment_id, run_id, service
    service.generate_successor_package(run_id)
    if stage == "PACKAGE_READY":
        return repository, assessment_id, run_id, service
    service.compare(run_id)
    if stage == "COMPARED":
        return repository, assessment_id, run_id, service
    if stage == "STALE":
        connection = sqlite3.connect(repository.path)
        connection.execute(
            "UPDATE reassessment_runs SET stage='STALE' WHERE run_id=?", (run_id,)
        )
        connection.commit()
        connection.close()
        return repository, assessment_id, run_id, service
    raise AssertionError(f"unsupported stage {stage}")


_STATES = (
    "NO_RUN",
    "OPEN",
    "DOCUMENT_SUBMITTED",
    "EVIDENCE_REVIEWED",
    "RESOLUTION_PROPOSED",
    "REQUESTED",
    "APPROVED",
    "SUCCESSOR_REVIEW_READY",
    "ASSESSED",
    "PACKAGE_READY",
    "COMPARED",
    "EVIDENCE_REJECTED",
    "STALE",
)


@pytest.fixture(scope="module")
def lifecycle(tmp_path_factory):
    """Render every reachable lifecycle state once, and reuse the pages."""

    monkeypatch = pytest.MonkeyPatch()
    pages: dict[str, AppTest] = {}
    runs: dict[str, str | None] = {}
    try:
        for stage in _STATES:
            repository, assessment_id, run_id, _ = _advance(
                tmp_path_factory.mktemp(stage.lower()), stage
            )
            monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(repository.path))
            pages[stage] = _page(assessment_id, run_id)
            runs[stage] = run_id
        yield pages, runs
    finally:
        monkeypatch.undo()


def _layer_one(lifecycle, stage: str) -> list[str]:
    return _split_layers(lifecycle[0][stage])[0]


def _layer_two(lifecycle, stage: str) -> list[str]:
    return _split_layers(lifecycle[0][stage])[1]


def test_no_state_raises(lifecycle) -> None:
    for stage, app in lifecycle[0].items():
        assert not app.exception, stage


# ---------------------------------------------------------------------------
# A. Orientation
# ---------------------------------------------------------------------------


def test_purpose_and_question_are_visible_in_every_state(lifecycle) -> None:
    for stage in _STATES:
        layer_one = _layer_one(lifecycle, stage)
        assert "What this page is for" in layer_one, stage
        assert PAGE_PURPOSE in layer_one, stage
        assert any(DOCUMENT_SCOPE in line for line in layer_one), stage


def test_original_decision_is_stated_as_unchanged_in_every_state(lifecycle) -> None:
    for stage in _STATES:
        layer_one = _layer_one(lifecycle, stage)
        assert "Your original decision remains unchanged" in layer_one, stage
        assert BASELINE_UNCHANGED in layer_one, stage
        assert any(
            line.startswith("Decision recorded for this activity: ")
            for line in layer_one
        ), stage


# ---------------------------------------------------------------------------
# B. Lifecycle
# ---------------------------------------------------------------------------


def test_full_required_path_is_visible_in_every_state(lifecycle) -> None:
    assert len(JOURNEY) == 6
    for stage in _STATES:
        text = "\n".join(_layer_one(lifecycle, stage))
        assert "What this process requires" in text, stage
        for step in JOURNEY:
            assert step in text, (stage, step)


def test_journey_uses_six_peer_cells_and_shared_progress_markers(lifecycle) -> None:
    open_page = lifecycle[0]["OPEN"]
    visible = "\n".join(_layer_one(lifecycle, "OPEN"))

    assert len(open_page.get("column")) == 6
    assert "→ 1. Source" in visible
    for step, label in enumerate(
        ("Reviewed", "Resolved", "Approved", "Successor", "Compared"), start=2
    ):
        assert f"• {step}. {label}" in visible
    assert "✗" not in visible

    # Once the successor exists, the active comparison step adds one equal
    # original/successor decision row while the six journey cells remain intact.
    assert len(lifecycle[0]["PACKAGE_READY"].get("column")) == 8


def test_progress_marks_the_step_each_recorded_stage_sits_in(lifecycle) -> None:
    expected = {
        "OPEN": "You are on step 1 of 6.",
        "DOCUMENT_SUBMITTED": "You are on step 2 of 6.",
        "EVIDENCE_REVIEWED": "You are on step 3 of 6.",
        "RESOLUTION_PROPOSED": "You are on step 4 of 6.",
        "REQUESTED": "You are on step 4 of 6.",
        "APPROVED": "You are on step 5 of 6.",
        "SUCCESSOR_REVIEW_READY": "You are on step 5 of 6.",
        "ASSESSED": "You are on step 5 of 6.",
        "PACKAGE_READY": "You are on step 6 of 6.",
        "COMPARED": "All 6 steps of this path were completed.",
        "EVIDENCE_REJECTED": "This reassessment stopped at step 2 of 6.",
        "NO_RUN": "No controlled reassessment is open for this question yet.",
    }
    for stage, caption in expected.items():
        assert caption in _layer_one(lifecycle, stage), stage


def test_current_stage_is_named_in_business_language(lifecycle) -> None:
    expected = {
        "OPEN": "Waiting for supporting document",
        "DOCUMENT_SUBMITTED": "Document submitted — awaiting evidence review",
        "EVIDENCE_REVIEWED": "Evidence reviewed — awaiting criterion resolution",
        "RESOLUTION_PROPOSED": "Resolution recorded — ready to request reassessment",
        "REQUESTED": "Reassessment requested — awaiting approval",
        "APPROVED": "Approved — ready to proceed",
        "SUCCESSOR_REVIEW_READY": "Successor review ready — awaiting assessment",
        "ASSESSED": "Assessed — awaiting Decision Package",
        "PACKAGE_READY": "Decision Package ready — awaiting comparison",
    }
    for stage, label in expected.items():
        layer_one = _layer_one(lifecycle, stage)
        assert "Where you are now" in layer_one, stage
        assert label in layer_one, stage
        assert "This step" in layer_one, stage
        assert "What happens next" in layer_one, stage


def test_no_stage_outside_the_recorded_lifecycle_is_presented(lifecycle) -> None:
    recorded = {stage.value for stage in M2RunStage}
    assert set(_STATES) - {"NO_RUN"} <= recorded


# ---------------------------------------------------------------------------
# C. Document submission
# ---------------------------------------------------------------------------


def test_document_scope_and_intake_limit_are_explained(lifecycle) -> None:
    layer_one = _layer_one(lifecycle, "OPEN")
    assert any(DOCUMENT_SCOPE in line for line in layer_one)
    assert (
        "One .txt document is the only intake this route accepts. Do not include "
        "credentials, secrets, or unnecessary personal data." in layer_one
    )
    assert any(
        "It does not change your decision and it does not start an assessment."
        in line
        for line in layer_one
    )
    text = "\n".join(layer_one).lower()
    for excluded in ("csv", "spreadsheet", "measured data", "database"):
        assert excluded not in text


# ---------------------------------------------------------------------------
# D. Evidence review
# ---------------------------------------------------------------------------


def test_review_choices_are_offered_with_business_labels_over_raw_values() -> None:
    source = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "ai_adoption_engine"
        / "presentation"
        / "pages"
        / "reassessment.py"
    ).read_text(encoding="utf-8")
    # The reviewer still chooses; the submitted value is still the raw enum.
    assert "[item.value for item in M2EvidencePermission]" in source
    assert "[item.value for item in M2ConflictStatus]" in source
    assert "M2EvidencePermission(outcome)" in source
    assert "M2ConflictStatus(conflict)" in source
    assert "format_func=_permission_label" in source
    assert "format_func=_conflict_label" in source
    # No option is pre-selected for the reviewer.
    assert source.count("index=None") == 2


def test_recorded_review_is_restated_in_business_words(lifecycle) -> None:
    for stage in ("EVIDENCE_REVIEWED", "REQUESTED", "COMPARED"):
        layer_one = _layer_one(lifecycle, stage)
        assert "What has been recorded so far" in layer_one, stage
        assert (
            "The evidence review recorded: Admissible for resolving this "
            "question and for the assessment checks." in layer_one
        ), stage
        assert (
            "Relationship to the evidence already reviewed: Consistent with the "
            "evidence already reviewed." in layer_one
        ), stage
        assert "Limitations retained: Text quality limitations remain." in layer_one, stage
    rejected = _layer_one(lifecycle, "EVIDENCE_REJECTED")
    assert (
        "The evidence review recorded: Rejected as evidence for this question."
        in rejected
    )


def test_no_raw_review_enum_appears_in_the_business_layer(lifecycle) -> None:
    tokens = (
        [permission.value for permission in M2EvidencePermission]
        + [conflict.value for conflict in M2ConflictStatus]
        + [stage.value for stage in M2RunStage]
        + ["INVESTIGATE_FURTHER", "DOCUMENT_SUPPORTED"]
    )
    for stage in _STATES:
        text = "\n".join(_layer_one(lifecycle, stage))
        for token in tokens:
            assert token not in text, (stage, token)


def test_reviewed_answer_is_restated_without_reinterpretation(lifecycle) -> None:
    for stage in ("RESOLUTION_PROPOSED", "APPROVED", "COMPARED"):
        assert (
            "Reviewed answer to the open question: 3 out of 5 — confirmed by the "
            "evidence." in _layer_one(lifecycle, stage)
        ), stage


def test_character_offsets_stay_available_and_are_explained(lifecycle) -> None:
    app = lifecycle[0]["DOCUMENT_SUBMITTED"]
    labels_seen = {item.label for item in app.number_input}
    assert {"Excerpt start character", "Excerpt end character"} <= labels_seen
    assert any(
        "as its first and last character position in the stored document" in line
        for line in _layer_one(lifecycle, "DOCUMENT_SUBMITTED")
    )
    # The recorded locator remains reachable, exactly as stored.
    assert any(
        line.startswith("Locator: characters ")
        for line in _layer_two(lifecycle, "EVIDENCE_REVIEWED")
    )


# ---------------------------------------------------------------------------
# E. Approval
# ---------------------------------------------------------------------------


def test_approval_remains_explicit_and_states_its_consequence(lifecycle) -> None:
    app = lifecycle[0]["REQUESTED"]
    assert "Explicitly approve reassessment" in [item.label for item in app.button]
    layer_one = _layer_one(lifecycle, "REQUESTED")
    assert any(
        "You are approving a reassessment that uses the reviewed evidence and "
        "the reviewed resolution recorded above." in line
        for line in layer_one
    )
    assert any(
        "Your original Decision Package is not rewritten; a separate successor "
        "may then be produced." in line
        for line in layer_one
    )
    # Requesting is still a separate recorded step that approves nothing.
    requested = _layer_one(lifecycle, "RESOLUTION_PROPOSED")
    assert any(
        "It approves nothing and produces no successor Decision Package." in line
        for line in requested
    )


def test_approval_is_named_once_recorded(lifecycle) -> None:
    assert (
        "A separate reassessment using this reviewed evidence was approved by "
        "approver." in _layer_one(lifecycle, "APPROVED")
    )


# ---------------------------------------------------------------------------
# F. Successor
# ---------------------------------------------------------------------------


def test_successor_is_described_as_separate_and_neutral(lifecycle) -> None:
    for stage in _STATES:
        text = "\n".join(_layer_one(lifecycle, stage)).lower()
        for word in (
            "improved",
            "better",
            "corrected",
            "upgraded",
            "successful",
            "more accurate",
            "fixes",
        ):
            assert word not in text, (stage, word)
    for stage in ("APPROVED", "SUCCESSOR_REVIEW_READY", "ASSESSED"):
        text = "\n".join(_layer_one(lifecycle, stage))
        assert "separate" in text, stage
    assert END_STATE in _layer_one(lifecycle, "APPROVED")


def test_completed_run_says_the_original_package_was_not_replaced(lifecycle) -> None:
    layer_one = _layer_one(lifecycle, "COMPARED")
    assert "This reassessment is complete" in layer_one
    assert "Comparison complete" in layer_one
    assert any(
        "A separate successor Decision Package and its comparison were "
        "produced, and your original Decision Package remains unchanged." in line
        for line in layer_one
    )
    assert any(
        "shown in Decision continuation" in line for line in layer_one
    )


# ---------------------------------------------------------------------------
# G. Stale / terminal / resume
# ---------------------------------------------------------------------------


def test_terminal_states_are_explained_accurately_and_distinctly(lifecycle) -> None:
    rejected = "\n".join(_layer_one(lifecycle, "EVIDENCE_REJECTED"))
    stale = "\n".join(_layer_one(lifecycle, "STALE"))
    compared = "\n".join(_layer_one(lifecycle, "COMPARED"))
    assert "Stopped — the evidence review did not accept the document" in rejected
    assert "No successor Decision Package was produced" in rejected
    assert "Stopped — this reassessment no longer matches the current decision" in stale
    assert (
        "pinned to a decision that is no longer the current one, so it can be "
        "inspected but not continued" in stale
    )
    # A stopped run is never presented as a failure of the reader's decision.
    for text in (rejected, stale):
        assert "error" not in text.lower()
        assert "your original decision" in text.lower()
    assert "Stopped —" not in compared


def test_every_stopped_state_retains_its_own_explanation() -> None:
    expected_phrases = {
        "EVIDENCE_REJECTED": "rejected as evidence for this question",
        "INSUFFICIENT": "not sufficient for this use",
        "BLOCKED_CONFLICT": "left unresolved",
        "STALE": "no longer the current one",
        "WITHDRAWN": "was withdrawn",
        "FAILED": "did not complete",
    }

    explanations = [_TERMINAL_DETAIL[stage] for stage in expected_phrases]
    assert len(set(explanations)) == len(expected_phrases)
    for stage, phrase in expected_phrases.items():
        assert phrase in _TERMINAL_DETAIL[stage]


def test_terminal_states_offer_no_lifecycle_control(lifecycle) -> None:
    for stage in ("COMPARED", "EVIDENCE_REJECTED", "STALE"):
        app = lifecycle[0][stage]
        assert [item.label for item in app.button] == [
            "Return to decision continuation"
        ], stage
        assert not app.file_uploader, stage
        assert any(
            "available for inspection only" in line
            for line in _layer_one(lifecycle, stage)
        ), stage


def test_in_progress_run_still_offers_exactly_its_own_next_action(lifecycle) -> None:
    expected = {
        "NO_RUN": "Open reassessment",
        "OPEN": "Submit supporting document",
        "DOCUMENT_SUBMITTED": "Record document evidence review",
        "EVIDENCE_REVIEWED": "Record reviewed criterion resolution",
        "RESOLUTION_PROPOSED": "Request reassessment",
        "REQUESTED": "Explicitly approve reassessment",
        "APPROVED": "Create separate successor review",
        "SUCCESSOR_REVIEW_READY": "Run separate successor assessment",
        "ASSESSED": "Generate separate successor Decision Package",
        "PACKAGE_READY": "Compare original and successor",
    }
    for stage, label in expected.items():
        app = lifecycle[0][stage]
        assert [item.label for item in app.button] == [
            label,
            "Return to decision continuation",
        ], stage


# ---------------------------------------------------------------------------
# H. Technical completeness
# ---------------------------------------------------------------------------


def test_identifiers_and_raw_values_stay_reachable(lifecycle) -> None:
    pages, runs = lifecycle
    for stage in _STATES:
        layer_two = _layer_two(lifecycle, stage)
        assert any(line.startswith("Baseline package: ") for line in layer_two), stage
        assert any(line.startswith("Criterion: ") for line in layer_two), stage
        assert any(
            line.startswith("Baseline recommendation: ") for line in layer_two
        ), stage
        run_id = runs[stage]
        if run_id is None:
            continue
        assert f"Separate reassessment run: {run_id}" in layer_two, stage
        assert any(
            line.startswith("Raw lifecycle stage: ") for line in layer_two
        ), stage

    reviewed = _layer_two(lifecycle, "EVIDENCE_REVIEWED")
    assert (
        "Raw evidence permission: CRITERION_RESOLUTION_AND_GATE_ADMISSIBLE" in reviewed
    )
    assert "Raw conflict status: CONSISTENT" in reviewed
    assert any(line.startswith("Document SHA-256: ") for line in reviewed)
    assert any(line.startswith("Document ID: doc-") for line in reviewed)

    completed = _layer_two(lifecycle, "COMPARED")
    assert any(
        line.startswith("Successor Decision Package: ") for line in completed
    )
    assert any(line.startswith("Comparison artifact: ") for line in completed)
    assert any(line.startswith("Lineage · ") for line in completed)
    assert any(line.startswith("Approval artifact: ") for line in completed)


def test_identifiers_do_not_appear_in_the_business_layer(lifecycle) -> None:
    pages, runs = lifecycle
    for stage in _STATES:
        text = "\n".join(_layer_one(lifecycle, stage))
        for prefix in ("decision-package-", "assessment-", "artifact-", "doc-", "m2-"):
            assert prefix not in text, (stage, prefix)
        run_id = runs[stage]
        if run_id is not None:
            assert run_id not in text, stage


# ---------------------------------------------------------------------------
# I. Actions
# ---------------------------------------------------------------------------


_CONSEQUENCES = {
    "Open reassessment": "Starts the controlled path above at step 1.",
    "Submit supporting document": (
        "Stores the document against this reassessment for review."
    ),
    "Record document evidence review": "Records your review of this document.",
    "Record reviewed criterion resolution": (
        "Records the reviewed answer to the open question."
    ),
    "Request reassessment": "Records the request.",
    "Explicitly approve reassessment": (
        "Approves a reassessment that uses the reviewed evidence"
    ),
    "Create separate successor review": (
        "Creates a separate review from the approved evidence."
    ),
    "Run separate successor assessment": (
        "Assesses the separate successor review."
    ),
    "Generate separate successor Decision Package": (
        "Produces a separate successor Decision Package next to your original one."
    ),
    "Compare original and successor": (
        "Records the comparison between the two Decision Packages"
    ),
    "Return to decision continuation": (
        "Goes back to the page listing your decision and its continuation routes."
    ),
}


def test_every_button_states_its_consequence(lifecycle) -> None:
    for stage in _STATES:
        app = lifecycle[0][stage]
        text = "\n".join(_layer_one(lifecycle, stage))
        for button in app.button:
            assert button.label in _CONSEQUENCES, (stage, button.label)
            assert _CONSEQUENCES[button.label] in text, (stage, button.label)


def test_no_internal_phase_label_survives(lifecycle) -> None:
    for stage in _STATES:
        labels_seen = {item.label for item in lifecycle[0][stage].button}
        for internal in ("Run Phase 5 successor assessment", "Generate Phase 6 successor Decision Package"):
            assert internal not in labels_seen, stage
        for label in labels_seen:
            assert "Phase " not in label, (stage, label)


# ---------------------------------------------------------------------------
# J. No unsupported claims
# ---------------------------------------------------------------------------


_FORBIDDEN = (
    "fixes the problem",
    "resolves the problem",
    "more accurate",
    "improved",
    "improves the recommendation",
    "increases confidence",
    "higher confidence",
    "ready for deployment",
    "ready to deploy",
    "roi improved",
    "proves ai suitability",
    "suitable for automation",
    "guarantees",
    "will change the recommendation",
)


def test_business_layer_makes_no_unsupported_claim(lifecycle) -> None:
    for stage in _STATES:
        text = "\n".join(_layer_one(lifecycle, stage)).lower()
        for phrase in _FORBIDDEN:
            assert phrase not in text, (stage, phrase)
        for absent in ("deploy", "confidence", "accuracy", "roi improve"):
            assert absent not in text, (stage, absent)


def test_no_guarantee_of_a_different_recommendation_is_stated(lifecycle) -> None:
    for stage in _STATES:
        assert NO_GUARANTEE in _layer_one(lifecycle, stage), stage
