"""Phase 9A-0a — the evidence-boundary tests that should have existed.

These tests characterise the boundary between Phase 4 review and Phase 1 assessment
for *criterion* values, which no existing test covers. The unit suite exercises all
four recommendation modes, but it does so against hand-authored fixtures
(``data/sample_processes/synthetic_customer_complaint_process.json``) whose criteria
already carry ``evidence_ids``. Nothing verified that the review pipeline can actually
produce such a state.

Two layers are covered. Both pass as of Fix 0; before Fix 0 the second was a strict
``xfail`` and is retained here as the regression guard for that defect:

``test_document_supported_criterion_survives_projection_and_reaches_the_engine``
    Domain layer. Passed before Fix 0 and is unchanged by it. ``correct_assertion``
    with ``origin=DOCUMENT_SUPPORTED`` already worked; the PORT-002 operator script
    used it. This test pins that capability so it cannot regress, and it established
    that Fix 0 was a presentation-layer change only. It asserts provenance and the
    absence of an evidence blockage — never a particular recommendation.

``test_review_ui_can_produce_an_evidence_backed_criterion``
    Product surface. Failed before Fix 0: the review page called the service without
    an ``origin``, so every value a reviewer supplied became ``HUMAN_SUPPLIED`` and its
    evidence was stripped during projection. Fix 0 added an origin selector and an
    evidence picker for gate-material criteria, which this test now drives. Its
    assertions are unchanged from the failing version.

Empirical basis, recorded 2026-08-15 in ``docs/phase9a-decision-review-v0.1.md``:
43 ideal criterion values supplied through the real ``ProcessReviewService`` projected
with ``evidence_ids=[]`` and produced ``INVESTIGATE_FURTHER`` on all four activities.

Neither test modifies production code, policy, schema, taxonomy or Phase 8 artefacts.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from streamlit.testing.v1 import AppTest
from streamlit.util import calc_hash

from ai_adoption_engine.decision.engine import AssessmentEngine
from ai_adoption_engine.decision.policy import load_policy
from ai_adoption_engine.models.enums import KnowledgeState, RecommendationMode
from ai_adoption_engine.models.review import (
    ExplicitApproval,
    InformationOrigin,
    ProcessReviewSession,
)
from ai_adoption_engine.persistence.sqlite import SQLiteAssessmentRepository
from ai_adoption_engine.review.approval import approve_review
from ai_adoption_engine.workspace.composition import build_workspace_service
from ai_adoption_engine.workspace.demo_extraction import demo_text
from ai_adoption_engine.workspace.models import ArtifactType, ExecutionMode


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "config" / "decision_policy.v0.2.json"

# Values chosen so that, if the evidence requirement is satisfied, every gate passes
# and the step is eligible for a positive recommendation.
IDEAL_CRITERIA = {
    "repetition": 5,
    "predictability": 5,
    "data_readiness": 5,
    "ai_capability_fit": 5,
    "business_value": 5,
    "human_judgement_requirement": 0,
    "risk_consequence": 0,
    "residual_risk_with_human_oversight": 0,
    "implementation_complexity": 0,
    "conventional_solution_fit": 0,
}


def _demo_review(path: Path) -> tuple[object, str, ProcessReviewSession]:
    """Build an offline-demo assessment and open a real review session."""

    repository = SQLiteAssessmentRepository(path)
    assessment = repository.create_assessment(
        "Phase 9A evidence boundary", ExecutionMode.OFFLINE_DEMO
    )
    service = build_workspace_service(path)
    service.ingest_upload(assessment.assessment_id, raw_text=demo_text())
    service.extract(assessment.assessment_id)
    session = service.start_review(assessment.assessment_id)
    return service, assessment.assessment_id, session


def _document_evidence(session: ProcessReviewSession, step) -> list:
    """Resolved Phase 2 evidence belonging to this document, for reuse in a correction."""

    for assertion in (step.description, step.activity):
        if assertion.evidence:
            return list(assertion.evidence)
    raise AssertionError("The demo step carries no resolved document evidence")


def test_document_supported_criterion_survives_projection_and_reaches_the_engine(
    tmp_path,
) -> None:
    """Domain layer: an evidenced criterion must keep its evidence through projection.

    Expected to PASS before Fix 0. Its purpose is to prove the defect is confined to
    the presentation layer, and to prevent regression of the path Fix 0 will expose.

    This is a provenance and projection test. It deliberately does **not** assert a
    particular recommendation. Whatever the policy decides once it can actually see the
    criteria is a policy outcome, not a provenance result, and asserting a specific mode
    here would couple a plumbing test to threshold semantics.

    Observed on 2026-08-15: with all ten criteria evidenced but no capability signal set
    to true, the engine returns ``DO_NOT_RECOMMEND`` at ``technical_fit`` via
    ``gates.py:175`` (``not capabilities``) — a substantive judgement, not an evidence
    blockage. Recorded in ``docs/phase9a-decision-review-v0.1.md`` §1.4.
    """

    service, assessment_id, session = _demo_review(tmp_path / "domain.db")
    review = service.review_service
    target = session.steps[0]
    evidence = _document_evidence(session, target)

    review.accept_assertion(session, session.process_name, "process.name")
    for step in session.steps:
        review.accept_assertion(
            session, step.activity, f"steps.{step.candidate_step_id}.activity"
        )
        # A dependency with no resolved target would block approval for reasons
        # unrelated to this test.
        for index, dependency in enumerate(step.dependencies):
            if dependency.target_candidate_step_id is None:
                review.reject_dependency(
                    session,
                    step.candidate_step_id,
                    index,
                    rationale="Unresolved dependency target; out of scope for this test.",
                )

    for characteristic in target.criteria:
        review.correct_assertion(
            session,
            characteristic.assertion,
            f"steps.{target.candidate_step_id}.criteria.{characteristic.name.value}",
            IDEAL_CRITERIA[characteristic.name.value],
            rationale="The source document states this operating characteristic.",
            origin=InformationOrigin.DOCUMENT_SUPPORTED,
            evidence=evidence,
        )
    review.correct_assertion(
        session,
        target.human_accountability_required,
        f"steps.{target.candidate_step_id}.human_accountability_required",
        False,
        rationale="The source document states this operating characteristic.",
        origin=InformationOrigin.DOCUMENT_SUPPORTED,
        evidence=evidence,
    )
    review.accept_step_order(session)

    result = approve_review(
        session,
        ExplicitApproval(
            approval_statement="APPROVE CURRENT-STATE PROCESS",
            approved_at=datetime.now(UTC),
            rationale="Phase 9A evidence-boundary characterisation.",
        ),
    )
    assert result.approved is not None, [item.model_dump() for item in result.errors]

    projected = next(
        step
        for step in result.approved.business_process.steps
        if step.step_id == target.candidate_step_id
    )

    # The point of the test: evidence must survive the Phase 4 -> Phase 1 projection.
    for name in IDEAL_CRITERIA:
        criterion = projected.characteristics.criterion(name)
        assert criterion.value == IDEAL_CRITERIA[name], name
        assert criterion.knowledge_state is KnowledgeState.KNOWN, name
        assert criterion.evidence_ids, f"{name} lost its evidence during projection"

    assessment = AssessmentEngine(load_policy(POLICY_PATH)).assess(
        result.approved.business_process
    )
    outcome = next(
        item
        for item in assessment.step_assessments
        if item.step_id == target.candidate_step_id
    )

    # The engine must no longer be blocked by missing evidence anywhere.
    for gate in outcome.gate_results:
        assert "no evidence reference" not in gate.rationale, (
            f"{gate.gate.value} still reports an evidence blockage: {gate.rationale}"
        )

    # An evidence-blocked step always stops at INVESTIGATE_FURTHER. Reaching any other
    # mode is the proof that the criteria were actually read and judged.
    assert outcome.recommendation_mode is not RecommendationMode.INVESTIGATE_FURTHER, (
        "The engine did not reach a substantive decision despite evidenced criteria"
    )

    # Policy outcome, recorded rather than asserted as desirable: with every criterion
    # evidenced but no capability signal true, map_capabilities returns [] and
    # gates.py:175 declines on "no mapped capability", not on missing evidence.
    technical_fit = next(
        gate for gate in outcome.gate_results if gate.gate.value == "technical_fit"
    )
    assert technical_fit.material_criteria, "technical_fit must cite its material criteria"
    assert "capabilit" in technical_fit.rationale.lower(), (
        "technical_fit should now decline on capability grounds, not evidence grounds: "
        f"{technical_fit.rationale}"
    )


def test_review_ui_can_produce_an_evidence_backed_criterion(tmp_path, monkeypatch) -> None:
    """Product surface: a reviewer must be able to evidence a criterion through the UI.

    This test failed before Fix 0 — the review page called the Phase 4 service without
    an ``origin``, so every reviewer-supplied criterion became ``HUMAN_SUPPLIED`` and
    its evidence was stripped during projection. It now drives the origin selector and
    evidence picker added by Fix 0.

    The assertions are unchanged from the failing version: a reviewer working only
    through the product must be able to reach a state where a document-supported
    criterion carries evidence.
    """

    path = tmp_path / "ui.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    repository = SQLiteAssessmentRepository(path)
    _, assessment_id, session = _demo_review(path)
    step_id = session.steps[0].candidate_step_id
    field_path = f"steps.{step_id}.criteria[3]"  # ai_capability_fit

    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30)
    app.session_state["selected_assessment_id"] = assessment_id
    app._page_hash = calc_hash("review")
    app.run()
    assert not app.exception
    app = app.selectbox(key="selected-review-step").select(step_id).run()

    def widget(collection, prefix: str):
        return next(item for item in collection if item.key and item.key.startswith(prefix))

    app = widget(app.selectbox, f"action-{field_path}-").select("Resolve unknown").run()
    app = widget(app.number_input, f"value-{field_path}-").set_value(5).run()

    origin = widget(app.selectbox, f"origin-{field_path}-")
    document_supported = next(
        option for option in origin.options if option.startswith("Document supported")
    )
    app = origin.select(document_supported).run()

    citations = widget(app.multiselect, f"evidence-{field_path}-")
    assert citations.options, "The step must offer at least one resolved citation"
    app = citations.select(citations.options[0]).run()

    app = (
        widget(app.text_input, f"rationale-{field_path}-")
        .input("The source document states this operating characteristic.")
        .run()
    )
    app = widget(app.button, f"apply-{field_path}-").click().run()
    assert not app.exception

    persisted: ProcessReviewSession = repository.load_active_artifact(
        assessment_id, ArtifactType.REVIEW_SESSION
    ).payload
    supplied = next(
        step for step in persisted.steps if step.candidate_step_id == step_id
    ).criteria[3].assertion

    assert supplied.value == 5
    assert supplied.origin is InformationOrigin.DOCUMENT_SUPPORTED, (
        "The UI produced a criterion the decision engine will discard: origin is "
        f"{supplied.origin.value}, so projection strips its evidence."
    )
    assert supplied.evidence, "A reviewer-supplied criterion must be able to cite evidence"
