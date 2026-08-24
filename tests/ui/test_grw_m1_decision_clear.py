"""Preliminary context (GRW Milestone 1) must read as a business page.

Milestone 1 is non-decision-affecting.  A reader who opens nothing must be able
to answer, in about ten seconds: why am I here, what am I being asked, why might
answering help, can this change my decision, and what happens next.  The formal
six-part unchanged effect, the raw evidence class, the reviewer's raw decision
and every identifier stay reachable behind the canonical technical control.

These tests assert the layering, not the Engine: no M1 semantics are exercised
here beyond what the page renders from the persisted record.
"""

from __future__ import annotations

import pytest

from ai_adoption_engine.grw.models import (
    GrwAdmissibilityEffect,
    GrwEvidenceClass,
    GrwReviewDecision,
)
from ai_adoption_engine.presentation.components.technical_details import (
    TECHNICAL_DETAILS_LABEL,
)
from ai_adoption_engine.presentation.pages.gap_resolution import (
    NO_DECISION_CHANGE,
    PAGE_PURPOSE,
    PAGE_PURPOSE_ANSWERED,
    USE_OF_ANSWER,
)
from tests.ui.test_grw_m1 import _ready_page


ANSWER = "Usually around 18,000–22,000 tickets per month."


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


def _submitted(app):
    app = app.text_area[0].input(ANSWER).run()
    return next(item for item in app.button if item.label == "Submit answer").click().run()


def _reviewed(app, review_label: str):
    app = _submitted(app)
    app = app.text_input[0].input("UI reviewer").run()
    app = app.text_area[0].input("Useful workload context only.").run()
    app = app.selectbox[0].select(review_label).run()
    return next(item for item in app.button if item.label == "Record review").click().run()


def _states(tmp_path_factory, monkeypatch):
    """Render the four M1 states a reader can actually reach."""

    states = {}
    fresh, _, _ = _ready_page(tmp_path_factory.mktemp("fresh"), monkeypatch)
    states["fresh"] = fresh
    awaiting, _, _ = _ready_page(tmp_path_factory.mktemp("awaiting"), monkeypatch)
    states["awaiting_review"] = _submitted(awaiting)
    for key, label in (
        ("reviewed_preliminary", "Accept as preliminary understanding"),
        ("reviewed_recorded_only", "Accept as recorded only"),
        ("reviewed_rejected", "Reject"),
    ):
        app, _, _ = _ready_page(tmp_path_factory.mktemp(key), monkeypatch)
        states[key] = _reviewed(app, label)
    return states


@pytest.fixture(scope="module")
def m1_states(tmp_path_factory):
    monkeypatch = pytest.MonkeyPatch()
    try:
        yield _states(tmp_path_factory, monkeypatch)
    finally:
        monkeypatch.undo()


# ---------------------------------------------------------------------------
# A. Orientation
# ---------------------------------------------------------------------------


def test_orientation_is_readable_without_opening_anything(m1_states) -> None:
    layer_one, _ = _split_layers(m1_states["fresh"])
    text = "\n".join(layer_one)
    assert "Add preliminary context" in text
    assert "What this page is for" in text
    assert PAGE_PURPOSE in layer_one
    for heading in (
        "Your current decision does not change",
        "The question",
        "Your answer",
    ):
        assert heading in layer_one
    # The purpose stops offering to answer once the question has been answered.
    answered, _ = _split_layers(m1_states["reviewed_preliminary"])
    assert PAGE_PURPOSE_ANSWERED in answered
    assert PAGE_PURPOSE not in answered


def test_every_state_states_what_happens_next(m1_states) -> None:
    fresh, _ = _split_layers(m1_states["fresh"])
    assert any("does not start a reassessment" in line for line in fresh)
    awaiting, _ = _split_layers(m1_states["awaiting_review"])
    assert any("A reviewer confirms what this answer may be used for" in line for line in awaiting)
    for key in ("reviewed_preliminary", "reviewed_recorded_only", "reviewed_rejected"):
        reviewed, _ = _split_layers(m1_states[key])
        assert "What happens next" in reviewed
        assert any(
            "Your Decision Package is unchanged and remains your official decision" in line
            for line in reviewed
        )


# ---------------------------------------------------------------------------
# B. Non-decision effect
# ---------------------------------------------------------------------------


_FORMAL_EFFECT = (
    "Criterion: unchanged",
    "Assessment gates: unchanged",
    "Recommendation: unchanged",
    "Priority: unchanged",
    "ROI: unchanged",
    "Decision Package: unchanged",
)


def test_plain_english_non_change_leads_every_state(m1_states) -> None:
    for key, app in m1_states.items():
        layer_one, _ = _split_layers(app)
        assert NO_DECISION_CHANGE in layer_one, key
        assert any(
            line.startswith("Decision recorded for this activity: ")
            and line.endswith(". Nothing on this page changes it.")
            for line in layer_one
        ), key


def test_formal_six_part_effect_is_preserved_in_the_technical_layer(m1_states) -> None:
    for key, app in m1_states.items():
        layer_one, layer_two = _split_layers(app)
        for statement in _FORMAL_EFFECT:
            assert statement in layer_two, (key, statement)
            assert statement not in layer_one, (key, statement)
        assert "No successor assessment or Decision Package was generated." in layer_two, key
        # Layer 1 says the same thing once, and says where the proof lives.
        assert any(
            "is recorded under the technical section on this page" in line
            for line in layer_one
        ), key


def test_no_unconditional_sufficiency_claim(m1_states) -> None:
    for key, app in m1_states.items():
        layer_one, layer_two = _split_layers(app)
        text = "\n".join(layer_one + layer_two)
        assert "enough for an initial assessment" not in text, key
        # What replaces it restates the package's recorded completeness.
        assert any(
            line.startswith("This Decision Package is complete and records")
            for line in layer_one
        ), key


# ---------------------------------------------------------------------------
# C. Question integrity
# ---------------------------------------------------------------------------


def test_exact_question_stays_visible_in_every_state(m1_states) -> None:
    question = (
        "About how often is “Record the complaint” performed in a typical month? "
        "A rough range is okay."
    )
    for key, app in m1_states.items():
        layer_one, _ = _split_layers(app)
        assert any(question in line for line in layer_one), key


# ---------------------------------------------------------------------------
# D. Answer integrity
# ---------------------------------------------------------------------------


def test_exact_answer_and_range_are_preserved_verbatim(m1_states) -> None:
    for key in (
        "awaiting_review",
        "reviewed_preliminary",
        "reviewed_recorded_only",
        "reviewed_rejected",
    ):
        layer_one, _ = _split_layers(m1_states[key])
        assert ANSWER in layer_one, key
        assert "Exact customer answer" in layer_one, key


def test_parsed_range_is_never_promoted_to_a_score(m1_states) -> None:
    layer_one, layer_two = _split_layers(m1_states["awaiting_review"])
    assert any(
        "Parsed range candidate only" in line and "is not a criterion score" in line
        for line in layer_one
    )
    assert any("This response is not measured or document-supported evidence." in line for line in layer_one)
    # The parser output itself is authoritative detail, so it stays technical.
    assert any("grw-m1-range-parser" in line for line in layer_two)


# ---------------------------------------------------------------------------
# E. Evidence / review vocabulary
# ---------------------------------------------------------------------------


_RAW_TOKENS = (
    GrwEvidenceClass.OPERATOR_PROVIDED_ESTIMATE.value,
    "DECISION_STRENGTHENING",
    "CANDIDATE_NEEDS_REVIEW",
    "INVESTIGATE_FURTHER",
)


def test_no_raw_enum_appears_in_the_business_layer(m1_states) -> None:
    for key, app in m1_states.items():
        layer_one, _ = _split_layers(app)
        text = "\n".join(layer_one)
        for token in _RAW_TOKENS:
            assert token not in text, (key, token)
    for key, decision, effect in (
        ("reviewed_preliminary", GrwReviewDecision.ACCEPT_PRELIMINARY, GrwAdmissibilityEffect.PRELIMINARY_UNDERSTANDING),
        ("reviewed_recorded_only", GrwReviewDecision.ACCEPT_RECORDED_ONLY, GrwAdmissibilityEffect.RECORDED_ONLY),
        ("reviewed_rejected", GrwReviewDecision.REJECT, GrwAdmissibilityEffect.NONE),
    ):
        layer_one, _ = _split_layers(m1_states[key])
        text = "\n".join(layer_one)
        assert decision.value not in text, key
        assert effect.value not in text, key


def test_business_layer_uses_the_shared_vocabulary(m1_states) -> None:
    layer_one, _ = _split_layers(m1_states["awaiting_review"])
    assert "How it was supplied: An estimate provided by an operator" in layer_one
    for key, decision_label, effect_label in (
        (
            "reviewed_preliminary",
            "Accepted as preliminary understanding",
            "May be used as preliminary understanding only",
        ),
        ("reviewed_recorded_only", "Accepted, recorded only", "Kept on the record only"),
        ("reviewed_rejected", "Rejected", "Not used as an assessment input"),
    ):
        layer_one, _ = _split_layers(m1_states[key])
        assert f"Reviewer's decision: {decision_label}" in layer_one, key
        assert f"What this answer may be used for: {effect_label}" in layer_one, key


def test_authoritative_raw_values_stay_reachable(m1_states) -> None:
    _, layer_two = _split_layers(m1_states["awaiting_review"])
    assert f"Evidence class: {GrwEvidenceClass.OPERATOR_PROVIDED_ESTIMATE.value}" in layer_two
    for key, decision, effect in (
        ("reviewed_preliminary", GrwReviewDecision.ACCEPT_PRELIMINARY, GrwAdmissibilityEffect.PRELIMINARY_UNDERSTANDING),
        ("reviewed_recorded_only", GrwReviewDecision.ACCEPT_RECORDED_ONLY, GrwAdmissibilityEffect.RECORDED_ONLY),
        ("reviewed_rejected", GrwReviewDecision.REJECT, GrwAdmissibilityEffect.NONE),
    ):
        _, layer_two = _split_layers(m1_states[key])
        assert f"Review decision: {decision.value}" in layer_two, key
        assert f"Admissibility effect: {effect.value}" in layer_two, key
        assert any(line.startswith("Reviewed submission SHA-256: ") for line in layer_two), key
        assert any(line.startswith("Recommendation mode: ") for line in layer_two), key


def test_identifiers_and_provenance_are_technical_only(m1_states) -> None:
    for key, app in m1_states.items():
        layer_one, layer_two = _split_layers(app)
        text = "\n".join(layer_one)
        for prefix in ("assessment-", "decision-package-", "candidate-step-", "artifact-"):
            assert prefix not in text, (key, prefix)
        for prefix in ("Baseline package ID: ", "Assessment: ", "Step ID: ", "Question ID: "):
            assert any(line.startswith(prefix) for line in layer_two), (key, prefix)
        assert any(
            line.startswith("Baseline recommendation for this activity: ")
            and "(existing; unchanged by Gap resolution)" in line
            for line in layer_two
        ), key


# ---------------------------------------------------------------------------
# F. Action consequence
# ---------------------------------------------------------------------------


def test_every_action_explains_its_consequence(m1_states) -> None:
    fresh_layer_one, _ = _split_layers(m1_states["fresh"])
    assert [item.label for item in m1_states["fresh"].button] == [
        "Submit answer",
        "Return to decision continuation",
    ]
    assert any(
        "It does not change your current decision and it does not start a reassessment."
        in line
        for line in fresh_layer_one
    )

    awaiting_layer_one, _ = _split_layers(m1_states["awaiting_review"])
    assert [item.label for item in m1_states["awaiting_review"].button] == [
        "Record review",
        "Return to decision continuation",
    ]
    assert any(
        "The current Decision Package stays exactly as it is." in line
        for line in awaiting_layer_one
    )

    for key, app in m1_states.items():
        layer_one, _ = _split_layers(app)
        assert any(
            "Nothing is submitted or discarded." in line for line in layer_one
        ), key


def test_no_reassurance_only_action_exists(m1_states) -> None:
    for key, app in m1_states.items():
        labels_seen = {item.label for item in app.button}
        assert "Continue with current recommendation" not in labels_seen, key
        assert "Acknowledge" not in labels_seen, key


# ---------------------------------------------------------------------------
# G. No overclaim
# ---------------------------------------------------------------------------


_FORBIDDEN = (
    "resolves the information gap",
    "resolves this gap",
    "gap is now resolved",
    "closes the information gap",
    "improves the recommendation",
    "strengthens the recommendation",
    "changes the recommendation",
    "improves the score",
    "changes the score",
    "increases confidence",
    "improves confidence",
    "higher confidence",
    "ready for deployment",
    "ready to deploy",
    "deployment ready",
    "triggers a reassessment",
    "starts a reassessment",
    "will be reassessed",
    "improves the ROI",
    "changes the ROI",
)

_NEGATORS = ("not ", "cannot", "never", "no ", "only if", "unchanged")


def _sentences(lines: list[str]) -> list[str]:
    sentences: list[str] = []
    for line in lines:
        for part in line.replace("\n", " ").split(". "):
            part = part.strip()
            if part:
                sentences.append(part)
    return sentences


def test_business_layer_makes_no_progress_claim(m1_states) -> None:
    for key, app in m1_states.items():
        layer_one, _ = _split_layers(app)
        text = "\n".join(layer_one).lower()
        for phrase in _FORBIDDEN:
            assert phrase.lower() not in text, (key, phrase)
        for absent in ("deploy", "confidence", "accuracy", "safe to automate"):
            assert absent not in text, (key, absent)


def test_reassessment_is_only_mentioned_with_a_negator(m1_states) -> None:
    for key, app in m1_states.items():
        layer_one, _ = _split_layers(app)
        for sentence in _sentences(layer_one):
            lowered = sentence.lower()
            if "reassess" not in lowered:
                continue
            assert any(negator in lowered for negator in _NEGATORS), (key, sentence)


def test_use_of_answer_is_stated_without_promotion(m1_states) -> None:
    layer_one, _ = _split_layers(m1_states["awaiting_review"])
    assert "How this answer will be used" in layer_one
    assert USE_OF_ANSWER in layer_one
    assert "it is not evidence for a formal reassessment" in USE_OF_ANSWER


def test_rejected_answer_is_not_softened(m1_states) -> None:
    layer_one, _ = _split_layers(m1_states["reviewed_rejected"])
    assert "The response was rejected and is not an assessment input." in layer_one
    # ...and the answer itself is still retained verbatim.
    assert ANSWER in layer_one


# ---------------------------------------------------------------------------
# H. Lifecycle regression (presentation-side guard)
# ---------------------------------------------------------------------------


def test_page_renders_the_persisted_record_unmodified(tmp_path, monkeypatch) -> None:
    app, service, assessment_id = _ready_page(tmp_path, monkeypatch)
    app = _reviewed(app, "Accept as preliminary understanding")
    assert not app.exception

    status = service.load_grw_m1_status(assessment_id)
    assert status.submission is not None and status.review is not None
    assert status.submission.answer_text == ANSWER
    assert status.submission.evidence_class is GrwEvidenceClass.OPERATOR_PROVIDED_ESTIMATE
    assert status.review.decision is GrwReviewDecision.ACCEPT_PRELIMINARY
    assert (
        status.review.admissibility_effect
        is GrwAdmissibilityEffect.PRELIMINARY_UNDERSTANDING
    )
    assert status.review.assessment_effect == "NONE"

    layer_one, layer_two = _split_layers(app)
    assert status.submission.answer_text in layer_one
    assert f"Submission ID: {status.submission.submission_id}" in layer_two
    assert f"Review ID: {status.review.review_id}" in layer_two
