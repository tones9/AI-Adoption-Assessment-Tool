"""One customer journey, start to finish, through the shipped application.

Hundreds of focused tests prove the parts.  This proves the story: a person
opens a fresh workspace, picks a bundled synthetic document, reviews what the
extraction proposed, approves it, runs the assessment, reads the result, opens
the Decision Package, exports the report — and stops there, because the package
is a complete deliverable.  The optional continuation route is then shown to be
available and to leave the baseline untouched.

Every step drives the real Streamlit pages and the real services.  Nothing about
the decision engine is mocked, and no completed artifact is inserted behind the
application's back.  Each page render is a fresh ``AppTest`` reading persisted
state from SQLite, which is also what a browser refresh does, so persistence is
exercised continuously rather than only in the step that names it.
"""

from __future__ import annotations

import re

from streamlit.testing.v1 import AppTest

from ai_adoption_engine.models.enums import RecommendationMode
from ai_adoption_engine.persistence.reassessment import SQLiteReassessmentRepository
from ai_adoption_engine.persistence.sqlite import SQLiteAssessmentRepository
from ai_adoption_engine.presentation.components.technical_details import (
    TECHNICAL_DETAILS_LABEL,
)
from ai_adoption_engine.presentation.report_html import render_report_html
from ai_adoption_engine.workspace.demo_fixtures import (
    DECISION_VARIETY,
    SYNTHETIC_LABEL,
)
from ai_adoption_engine.workspace.models import ArtifactType, ExecutionMode


#: The release expectation for the bundled decision-variety fixture.  These are
#: fixed outputs, not recomputed here: ``tests/integration/test_demo_fixtures``
#: owns the contract, and this test asserts the customer sees it.
EXPECTED_OUTCOMES = {
    "Sort incoming maintenance requests": RecommendationMode.AUTOMATE,
    "Check the request against the service contract": RecommendationMode.INVESTIGATE_FURTHER,
    "Draft the scheduling note for the field engineer": RecommendationMode.AUGMENT,
    "Approve or refuse a goodwill repair": RecommendationMode.DO_NOT_RECOMMEND,
}

ELIGIBLE_ACTIVITY = "Check the request against the service contract"


def _page(module: str, assessment_id: str) -> AppTest:
    """Render one registered page as a fresh run against persisted state."""

    return AppTest.from_string(
        "import streamlit as st\n"
        f"st.session_state.selected_assessment_id = {assessment_id!r}\n"
        f"from ai_adoption_engine.presentation.pages.{module} import render\n"
        "render()\n",
        default_timeout=120,
    ).run()


def _text(app: AppTest) -> str:
    return "\n".join(
        str(item.value)
        for kind in (
            "title",
            "subheader",
            "header",
            "markdown",
            "caption",
            "info",
            "warning",
            "success",
            "error",
            "text",
        )
        for item in app.get(kind)
    )


_WIDGETS = {
    "Button",
    "Checkbox",
    "DownloadButton",
    "FileUploader",
    "Multiselect",
    "NumberInput",
    "Radio",
    "Selectbox",
    "Slider",
    "TextArea",
    "TextInput",
    "Toggle",
}


def _business_text(app: AppTest) -> str:
    """Return only the text a reader sees without opening anything."""

    lines: list[str] = []

    def collect(block, keep: bool) -> None:
        for element in getattr(block, "children", {}).values():
            if getattr(element, "type", None) == "expander":
                collect(element, keep and element.label != TECHNICAL_DETAILS_LABEL)
                continue
            if hasattr(element, "children"):
                collect(element, keep)
                continue
            if not keep or type(element).__name__ in _WIDGETS:
                continue
            value = str(getattr(element, "value", "") or "").strip()
            if value:
                lines.append(value)

    collect(app.main, True)
    return "\n".join(lines)


def _has_technical_control(app: AppTest) -> bool:
    """Return whether the canonical technical section is offered on the page."""

    found = False

    def walk(block) -> None:
        nonlocal found
        for element in getattr(block, "children", {}).values():
            if getattr(element, "label", None) == TECHNICAL_DETAILS_LABEL:
                found = True
            if hasattr(element, "children"):
                walk(element)

    walk(app.main)
    return found


def _click(app: AppTest, label: str) -> AppTest:
    return next(item for item in app.button if item.label == label).click().run()


def test_portfolio_v1_canonical_customer_journey(tmp_path, monkeypatch) -> None:
    database = tmp_path / "release-journey.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(database))

    # ------------------------------------------------------------------
    # 1. START — a fresh workspace, no frozen evaluation database in sight.
    # ------------------------------------------------------------------
    repository = SQLiteAssessmentRepository(database)
    assessment = repository.create_assessment(
        "Field service request handling", ExecutionMode.OFFLINE_DEMO
    )
    assessment_id = assessment.assessment_id
    assert "evaluation" not in str(database.resolve()).split("/")

    # ------------------------------------------------------------------
    # 2. SOURCE & EXTRACTION — choose the bundled synthetic document, ingest
    #    it, and run the scripted extraction through the page.
    # ------------------------------------------------------------------
    app = _page("source", assessment_id)
    assert not app.exception
    app = app.radio(key="demo-fixture-choice").set_value(DECISION_VARIETY).run()
    source_text = _text(app)
    assert SYNTHETIC_LABEL in source_text
    assert DECISION_VARIETY.summary in source_text

    app = _click(app, "Ingest document")
    assert not app.exception
    assert SYNTHETIC_LABEL in _text(app)

    app = _click(app, "Extract candidate process")
    assert not app.exception

    workspace = repository.load_workspace(assessment_id)
    candidate = workspace.active_artifacts[ArtifactType.CANDIDATE_EXTRACTION_RESULT]
    activities = [
        str(step.activity.value) for step in candidate.payload.candidate.steps
    ]
    assert activities == list(EXPECTED_OUTCOMES)
    assert (
        ArtifactType.APPROVED_REVIEW not in workspace.active_artifacts
    ), "extraction must not produce an approval"

    # ------------------------------------------------------------------
    # 3. GUIDED REVIEW — approval is refused until every required item is
    #    resolved, and the reviewer resolves them through the page itself.
    # ------------------------------------------------------------------
    app = _page("review", assessment_id)
    assert not app.exception
    # Validation is an explicit step of its own: the page does not start one
    # on the reader's behalf.
    assert "CANDIDATE PROCESS — NEEDS VALIDATION" in _text(app)
    assert (
        ArtifactType.REVIEW_SESSION
        not in repository.load_workspace(assessment_id).active_artifacts
    )
    app = _click(app, "Start process validation")
    assert not app.exception

    before_review = _text(app)
    assert "required item" in before_review
    approve_button = next(
        item
        for item in app.button
        if item.label == "Approve current-state process"
    )
    assert approve_button.disabled, "approval must not be offered before review"
    assert re.search(r"Not ready for approval — \d+ required item", before_review)

    confirmations = 0
    for _ in range(20):
        pending = [
            item
            for item in app.button
            if item.label.startswith("Confirm ")
            and "document-supported fact" in item.label
        ]
        if not pending:
            break
        app = _click(app, pending[0].label)
        assert not app.exception
        confirmations += 1
    else:  # pragma: no cover - the fixture has five confirmation scopes
        raise AssertionError("document confirmation did not converge")
    # One confirmation scope for the process and one for each activity: the
    # review was genuinely performed, not skipped by an empty loop.
    assert confirmations >= 1 + len(EXPECTED_OUTCOMES)

    assert any(
        item.label == "Accept current step order" for item in app.button
    ), "step order is a required review item and must be offered"
    app = _click(app, "Accept current step order")
    assert not app.exception

    # The reviewer's actions are persisted, not held in the browser session.
    assert (
        ArtifactType.REVIEW_SESSION
        in repository.load_workspace(assessment_id).active_artifacts
    )

    # Reviewed values keep their provenance: the confirmations are recorded
    # against the extraction's own evidence, not re-sourced.
    session = repository.load_workspace(assessment_id).active_artifacts[
        ArtifactType.REVIEW_SESSION
    ]
    reviewed = [
        characteristic
        for step in session.payload.steps
        for characteristic in step.criteria
        if characteristic.assertion.value is not None
    ]
    assert reviewed, "the fixture's documented criteria must survive review"
    assert all(item.assertion.evidence for item in reviewed)

    # ------------------------------------------------------------------
    # 4. EXPLICIT APPROVAL — a separate, deliberate action.
    # ------------------------------------------------------------------
    app = _page("review", assessment_id)
    ready_text = _text(app)
    assert "Ready for approval — all required review items are complete." in ready_text
    approve_button = next(
        item for item in app.button if item.label == "Approve current-state process"
    )
    assert approve_button.disabled, "approval requires the explicit confirmation"

    approval_workspace = repository.load_workspace(assessment_id)
    assert ArtifactType.APPROVED_REVIEW not in approval_workspace.active_artifacts
    assert (
        ArtifactType.INTEGRATED_ASSESSMENT_RESULT
        not in approval_workspace.active_artifacts
    ), "a completed review is not an approval"

    app = app.checkbox[0].set_value(True).run()
    app = _click(app, "Approve current-state process")
    assert not app.exception
    approved = repository.load_workspace(assessment_id).active_artifacts[
        ArtifactType.APPROVED_REVIEW
    ]
    assert approved.payload.approval.approved_at is not None

    # ------------------------------------------------------------------
    # 5. ASSESSMENT — the real deterministic engine, run from the page.
    # ------------------------------------------------------------------
    app = _page("results", assessment_id)
    assert not app.exception
    app = _click(app, "Run AI-adoption assessment")
    assert not app.exception

    integrated = repository.load_workspace(assessment_id).active_artifacts[
        ArtifactType.INTEGRATED_ASSESSMENT_RESULT
    ]
    produced = {
        step.activity: step.recommendation_mode
        for step in integrated.payload.process_assessment.step_assessments
    }
    assert produced == EXPECTED_OUTCOMES
    # The assessment is pinned to the exact review that was approved.
    assert integrated.payload.lineage.review_id == approved.payload.review.review_id
    assert (
        integrated.payload.lineage.approved_at
        == approved.payload.approval.approved_at
    )

    # ------------------------------------------------------------------
    # 6. RESULTS — the decision, in business language, before any detail.
    # ------------------------------------------------------------------
    app = _page("results", assessment_id)
    assert not app.exception
    visible = _business_text(app)
    assert "Assessment Results ·" in visible
    assert "What we found" in visible
    assert "mixed result" in visible
    for activity in EXPECTED_OUTCOMES:
        assert activity in visible, activity
    assert "Automate" in visible and "Augment" in visible
    assert "More information needed" in visible and "Not recommended" in visible
    # The one real evidence gap is named, and named as evidence.
    assert "Data readiness" in visible
    assert ELIGIBLE_ACTIVITY in visible
    assert (
        "'More information needed' is a statement about the available evidence, "
        "not a judgement about the activity or about AI." in visible
    )
    # Identifiers stay behind the technical control.
    assert assessment_id not in visible
    assert "INVESTIGATE_FURTHER" not in visible

    # ------------------------------------------------------------------
    # 7. DECISION PACKAGE — generated through the page, and final.
    # ------------------------------------------------------------------
    app = _page("decision_package", assessment_id)
    assert not app.exception
    app = _click(app, "Generate decision package")
    assert not app.exception

    package_artifact = repository.load_workspace(assessment_id).active_artifacts[
        ArtifactType.DECISION_PACKAGE_RESULT
    ]
    package = package_artifact.payload.package
    assert package.completeness.value == "COMPLETE_WITH_INFORMATION_GAPS"
    assert {
        item.current_activity: item.recommendation_mode
        for item in package.portfolio.items
    } == EXPECTED_OUTCOMES

    app = _page("decision_package", assessment_id)
    package_visible = _business_text(app)
    assert "Decision summary" in package_visible
    # The user can stop here: the package says so itself.
    assert "This Decision Package is a complete decision. You can act on it now." in (
        package_visible
    )
    assert "They are optional and they do not change this Decision Package." in (
        package_visible
    )
    assert "does not approve deployment or implementation" in package_visible
    # Technical traceability is still reachable, just not in the way: the
    # canonical control is offered, and the package identity is behind it.
    assert _has_technical_control(app)
    assert package.package_id in _text(app)
    assert package.package_id not in package_visible

    # ------------------------------------------------------------------
    # 8. REPORT / EXPORT — the deliverable the user takes away.
    # ------------------------------------------------------------------
    assert [item.label for item in app.download_button] == [
        "Download print-friendly HTML report"
    ]
    html = render_report_html(package)
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert "<script" not in html
    assert "Synthetic Field Service Request Handling" in html
    for activity in EXPECTED_OUTCOMES:
        assert activity in html, activity

    # ------------------------------------------------------------------
    # 9. REFRESH / REOPEN — a new process, a new repository handle, the same
    #    decision.  Nothing is recomputed and nothing is duplicated.
    # ------------------------------------------------------------------
    reopened = SQLiteAssessmentRepository(database).load_workspace(assessment_id)
    reopened_package = reopened.active_artifacts[ArtifactType.DECISION_PACKAGE_RESULT]
    assert reopened_package.artifact_id == package_artifact.artifact_id
    assert reopened_package.artifact_revision == package_artifact.artifact_revision
    assert reopened_package.payload_sha256 == package_artifact.payload_sha256
    assert reopened_package.payload.package.package_id == package.package_id
    assert {
        item.current_activity: item.recommendation_mode
        for item in reopened_package.payload.package.portfolio.items
    } == EXPECTED_OUTCOMES
    assert ArtifactType.APPROVED_REVIEW in reopened.active_artifacts

    app = _page("decision_package", assessment_id)
    assert not app.exception
    assert not [
        item for item in app.button if item.label == "Generate decision package"
    ], "an existing package must not offer to generate a second baseline"

    # ------------------------------------------------------------------
    # 10. OPTIONAL CONTINUATION — offered, never required.
    # ------------------------------------------------------------------
    app = _page("decision_continuation", assessment_id)
    assert not app.exception
    continuation = _business_text(app)
    assert "Your current official decision" in continuation
    assert "Do you need to do anything?" in continuation
    assert (
        "No. The decision above is complete and stays your official decision. "
        "You can act on it now and close this page." in continuation
    )
    assert "Everything on this page is optional." in continuation
    assert "Option A — Keep the current decision" in continuation
    assert "Option C — Controlled reassessment" in continuation
    assert ELIGIBLE_ACTIVITY in continuation
    assert "Review controlled reassessment" in [item.label for item in app.button]

    # The eligible activity is the one the assessment left open, and the route
    # is genuinely open under the existing rules.
    from ai_adoption_engine.grw.m2.service import M2ReassessmentService

    context = M2ReassessmentService(
        repository, SQLiteReassessmentRepository(database)
    ).open_m2_m1_context(assessment_id)
    assert context is not None
    _, gap = context
    assert gap.current_activity == ELIGIBLE_ACTIVITY

    # ------------------------------------------------------------------
    # 11. BASELINE IMMUTABILITY — reading the continuation options changed
    #     nothing, and no successor exists because none was created.
    # ------------------------------------------------------------------
    final = SQLiteAssessmentRepository(database).load_workspace(assessment_id)
    final_package = final.active_artifacts[ArtifactType.DECISION_PACKAGE_RESULT]
    assert final_package.artifact_id == package_artifact.artifact_id
    assert final_package.artifact_revision == package_artifact.artifact_revision
    assert final_package.payload_sha256 == package_artifact.payload_sha256

    from ai_adoption_engine.presentation.context import decision_continuation_service

    view = decision_continuation_service().open(assessment_id)
    assert view.m2_runs == ()
    assert all(run.successor is None for run in view.m2_runs)
