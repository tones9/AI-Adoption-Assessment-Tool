"""The Decision Package is the delivered decision, not a generator console.

Layer 1 is asserted structurally: the decision, its reason, its meaning, the
next action and the limitations must all be readable before anything is opened,
and package identifiers must not be.

The deterministic report projection rendered under "Supporting decision
detail" is decision-first as well: its business layer carries no raw internal
tokens, and identifiers, planning origins and engine rationale stay behind the
canonical technical control.  The future-state, roadmap and governance tabs
keep their frozen Stage 4 presentation.
"""

from __future__ import annotations

from html import unescape

from streamlit.testing.v1 import AppTest

from ai_adoption_engine.decision_support import DecisionSupportPackageService
from ai_adoption_engine.persistence.sqlite import SQLiteAssessmentRepository
from ai_adoption_engine.presentation.components.technical_details import (
    TECHNICAL_DETAILS_LABEL,
)
from ai_adoption_engine.presentation.pages.decision_package import (
    OPPORTUNITY_PORTFOLIO,
    PACKAGE_SECTIONS,
    _SECTION_NAV_STYLES,
)
from ai_adoption_engine.presentation.report_view import build_report_view
from ai_adoption_engine.workspace.models import (
    ArtifactType,
    ExecutionMode,
    WorkflowStage,
)
from tests.fakes.decision_support import sample_integrated_assessment
from tests.fakes.review import approved_review


def _package_app(tmp_path, monkeypatch):
    path = tmp_path / "package-decision-first.db"
    monkeypatch.setenv("AI_ADOPTION_ENGINE_DB_PATH", str(path))
    repository = SQLiteAssessmentRepository(path)
    assessment = repository.create_assessment("Package first", ExecutionMode.OFFLINE_DEMO)
    approval = repository.save_artifact_and_advance(
        assessment.assessment_id,
        ArtifactType.APPROVED_REVIEW,
        approved_review(),
        artifact_schema_version="phase4-v0.1",
        stage=WorkflowStage.APPROVED,
    )
    integrated = sample_integrated_assessment()
    integrated_ref = repository.save_artifact_and_advance(
        assessment.assessment_id,
        ArtifactType.INTEGRATED_ASSESSMENT_RESULT,
        integrated,
        artifact_schema_version="phase5-v0.1",
        stage=WorkflowStage.ASSESSED,
        parent_artifact_id=approval.artifact_id,
    )
    generated = DecisionSupportPackageService().generate(integrated)
    repository.save_artifact_and_advance(
        assessment.assessment_id,
        ArtifactType.DECISION_PACKAGE_RESULT,
        generated,
        artifact_schema_version="phase6-v0.1",
        stage=WorkflowStage.PACKAGE_READY,
        parent_artifact_id=integrated_ref.artifact_id,
    )
    app = AppTest.from_string(
        "import streamlit as st\n"
        f"st.session_state.selected_assessment_id = {assessment.assessment_id!r}\n"
        "from ai_adoption_engine.presentation.pages.decision_package import render\n"
        "render()",
        default_timeout=90,
    ).run()
    return app, generated.package


def _text(element) -> str:
    value = str(
        getattr(element, "value", "") or getattr(element, "label", "") or ""
    )
    if value.lstrip().startswith("<style>"):
        return ""
    return unescape(value)


def _split_layers(app) -> tuple[list[str], list[str]]:
    """Return (visible-by-default text, text behind a technical expander)."""

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
            value = _text(element).strip()
            if value:
                sink.append(value)

    collect(app.main, layer_one)
    return layer_one, layer_two


def _decision_header(layer_one: list[str]) -> list[str]:
    """Return only the block this stage owns: the header, before the report."""

    end = layer_one.index("Supporting decision detail")
    return layer_one[:end]


def _select_section(app: AppTest, section: str) -> AppTest:
    return app.segmented_control[0].set_value(section).run()


def _all_section_layers(app: AppTest) -> tuple[list[str], list[str]]:
    visible: list[str] = []
    technical: list[str] = []
    for section in PACKAGE_SECTIONS:
        app = _select_section(app, section)
        layer_one, layer_two = _split_layers(app)
        visible.extend(layer_one)
        technical.extend(layer_two)
    return visible, technical


# ---------------------------------------------------------------------------
# Decision-first hierarchy
# ---------------------------------------------------------------------------


def test_package_leads_with_the_decision_not_the_generator(tmp_path, monkeypatch) -> None:
    app, package = _package_app(tmp_path, monkeypatch)
    assert not app.exception

    layer_one, _ = _split_layers(app)
    header = _decision_header(layer_one)
    joined = "\n".join(header)

    assert "Decision package generated from the saved assessment result." not in "\n".join(
        layer_one
    )
    assert app.title[0].value == "Decision Package"
    assert tuple(app.segmented_control[0].options) == PACKAGE_SECTIONS
    assert f"Decision Package · {package.current_state.process_name}" in header

    headings = [item.value for item in app.subheader]
    assert headings == [
        "Decision summary",
        "Supporting decision detail",
        "Executive summary",
        "Process assessed",
    ]
    for label in (
        "Why this decision was reached",
        "What this means",
        "What happens next",
        "Risks and limitations",
    ):
        assert label in joined
    assert "mixed result" in joined


def test_package_navigation_has_six_sticky_sections_and_one_technical_control_each(
    tmp_path, monkeypatch
) -> None:
    app, _ = _package_app(tmp_path, monkeypatch)
    assert tuple(app.segmented_control[0].options) == PACKAGE_SECTIONS

    for section in PACKAGE_SECTIONS:
        app = _select_section(app, section)
        assert not app.exception
        assert sum(
            item.label == TECHNICAL_DETAILS_LABEL for item in app.expander
        ) == 1

    assert 'data-testid="stLayoutWrapper"' in _SECTION_NAV_STYLES
    assert "position: sticky" in _SECTION_NAV_STYLES
    assert '[role="radiogroup"]' in _SECTION_NAV_STYLES
    assert "overflow-x: auto" in _SECTION_NAV_STYLES


def test_limitations_are_readable_before_any_technical_detail(
    tmp_path, monkeypatch
) -> None:
    app, package = _package_app(tmp_path, monkeypatch)
    layer_one, _ = _split_layers(app)
    header = _decision_header(layer_one)

    assert package.roi_statement in header
    for limitation in (
        "This package is decision support. It does not approve deployment or implementation.",
        "The decision policy used is provisional and is not academically validated.",
        "The proposed future-state workflow is a proposal. Nothing in it has been deployed.",
        "This package provides no legal conclusion, no security approval and no judgement that anything is ready for deployment.",
    ):
        assert limitation in header

    limitations_index = layer_one.index(package.roi_statement)
    supporting_index = layer_one.index("Supporting decision detail")
    assert limitations_index < supporting_index


# ---------------------------------------------------------------------------
# Wording safeguards
# ---------------------------------------------------------------------------


def test_investigate_further_stays_evidence_bounded(tmp_path, monkeypatch) -> None:
    app, _ = _package_app(tmp_path, monkeypatch)
    header = "\n".join(_decision_header(_split_layers(app)[0]))

    assert (
        "the available evidence does not establish whether the data this activity "
        "relies on is ready for AI use"
    ) in header
    lowered = header.lower()
    for claim in (
        "ai is unsuitable",
        "not suitable for ai",
        "data is poor",
        "data is not ready",
        "data quality",
        "accuracy threshold",
    ):
        assert claim not in lowered


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in text.replace("\n", " ").split(".") if part.strip()]


def test_no_unsupported_positive_claim_in_the_decision_header(
    tmp_path, monkeypatch
) -> None:
    """Ban unsupported positive claims, never the vocabulary itself.

    "no judgement that anything is ready for deployment" is a required
    limitation; "ready for deployment" as an assertion is not.  The test
    therefore checks the sentence around each sensitive phrase for a negator,
    exactly as the ROI rule requires.
    """

    app, _ = _package_app(tmp_path, monkeypatch)
    header = "\n".join(_decision_header(_split_layers(app)[0])).lower()

    for claim in (
        "will improve",
        "will reduce",
        "will increase",
        "proven suitable",
        "proven",
        "guaranteed",
        "best practice",
    ):
        assert claim not in header

    negators = ("no ", "not ", "never", "does not", "outside this product")
    for sensitive in (
        "ready for deployment",
        "safe to deploy",
        "approve deployment",
        "approval to deploy",
        "implementation",
    ):
        for sentence in _sentences(header):
            if sensitive in sentence:
                assert any(word in sentence for word in negators), sentence

    # The limitation itself must be stated, so the term is not banned outright.
    assert "return on investment (roi)" in header


def test_no_package_identifiers_in_the_decision_header(tmp_path, monkeypatch) -> None:
    app, package = _package_app(tmp_path, monkeypatch)
    header = "\n".join(_decision_header(_split_layers(app)[0]))

    for token in (
        package.package_id,
        package.source.policy.policy_id,
        package.source.policy.decision_policy_fingerprint,
        package.source.lineage.validated_process_fingerprint,
        package.source.integrated_assessment_run_id,
        package.completeness.value,
        "DERIVED_PLANNING_GUIDANCE",
        "ASSESSMENT_FINDING",
    ):
        assert token not in header


# ---------------------------------------------------------------------------
# Technical preservation
# ---------------------------------------------------------------------------


def test_identifiers_and_provenance_remain_behind_the_canonical_control(
    tmp_path, monkeypatch
) -> None:
    app, package = _package_app(tmp_path, monkeypatch)
    _, layer_two = _all_section_layers(app)
    technical = "\n".join(layer_two)

    for token in (
        package.package_id,
        package.package_schema_version,
        package.completeness.value,
        package.source.policy.policy_id,
        package.source.policy.decision_policy_fingerprint,
        package.source.lineage.validated_process_fingerprint,
        package.source.integrated_assessment_run_id,
        package.current_state.review_id,
        package.current_state.approval_event_id,
        package.current_state.source_document_id,
    ):
        assert token in technical

    for statement in package.methodology.disclosure_statements:
        assert statement in technical

    # Planning-origin tokens and internal step IDs moved out of the report body.
    assert "DERIVED_PLANNING_GUIDANCE" in technical
    assert "ASSESSMENT_FINDING" in technical
    assert any("Internal step ID" in line for line in layer_two)
    assert any(
        line.startswith("Step ") and "Origin" in line for line in layer_two
    )


def test_report_body_layer_one_is_business_facing(tmp_path, monkeypatch) -> None:
    """The portfolio section carries no raw internal tokens outside Layer 2."""

    app, _ = _package_app(tmp_path, monkeypatch)
    app = _select_section(app, OPPORTUNITY_PORTFOLIO)
    layer_one, layer_two = _split_layers(app)
    body = "\n".join(layer_one)

    for token in (
        "AUTOMATE=",
        "COMPLETE_WITH_INFORMATION_GAPS",
        "INVESTIGATE_FURTHER",
        "DO_NOT_RECOMMEND",
        "Investigate Further",
        "Do Not Recommend",
        "NEEDS_CONFIRMATION",
        "AI_ENABLED_EXECUTION",
        "QUALIFYING_OPPORTUNITY",
        "ASSESSMENT_FINDING",
        "DERIVED_PLANNING_GUIDANCE",
    ):
        assert token not in body, token

    assert "Recommendation: More information needed" in body
    assert "Recommendation: Not recommended" in body

    technical = "\n".join(layer_two)
    assert "Engine rationale:" in technical
    assert "Recommendation mode: DO_NOT_RECOMMEND" in technical


def test_package_semantics_are_unchanged_by_presentation(tmp_path, monkeypatch) -> None:
    app, package = _package_app(tmp_path, monkeypatch)
    layer_one, layer_two = _all_section_layers(app)
    everything = "\n".join(layer_one + layer_two)

    # Every authoritative report value remains reachable in one of the six
    # sections; sectioning relocates content and does not delete it.
    for section in build_report_view(package):
        assert section.title in everything
        for block in section.blocks:
            if block.heading:
                assert block.heading in everything
            for paragraph in block.paragraphs:
                assert paragraph in everything
            for bullet in block.bullets:
                assert bullet in everything
            if block.origin:
                assert block.origin.value in "\n".join(layer_two)
            for detail in block.technical_details:
                assert detail in "\n".join(layer_two)

    assert everything.count("Reason / basis:") == len(package.portfolio.items)
    assert everything.count("Next action:") == len(package.portfolio.items)
    assert "PROPOSED / NOT DEPLOYED" in everything
    assert "GO / REVISE / STOP" in everything
    assert "does not claim legal compliance" in everything
    assert any(
        item.label == "Download print-friendly HTML report"
        for item in _select_section(app, PACKAGE_SECTIONS[0]).download_button
    )


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


def test_continuation_is_offered_as_optional_with_a_named_consequence(
    tmp_path, monkeypatch
) -> None:
    app, _ = _package_app(tmp_path, monkeypatch)
    header = "\n".join(_decision_header(_split_layers(app)[0]))

    labels_seen = [item.label for item in app.button]
    assert "Review optional evidence-continuation paths" in labels_seen
    assert "Continue decision" not in labels_seen

    assert "This Decision Package is a complete decision. You can act on it now." in header
    assert (
        "They are optional and they do not change this Decision Package." in header
        or "No evidence continuation is required for this decision." in header
    )
