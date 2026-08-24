"""The Decision Report reads as a business decision document.

Portfolio Version 1 Decision Experience: the report projection and the exported
HTML open with the package narrative decision, keep structured gaps and
limitations in evidence-bounded business wording, and relocate — never remove —
identifiers, fingerprints, planning origins and engine rationale into the
canonical technical layer.

The authoritative ``DecisionReportContent`` contract (13 sections, enum order)
is asserted unchanged.
"""

from __future__ import annotations

import re
from html import escape

import pytest

from ai_adoption_engine.decision_support import DecisionSupportPackageService
from ai_adoption_engine.models.decision_support import ReportSectionId
from ai_adoption_engine.presentation.decision_narrative import (
    build_package_narrative,
)
from ai_adoption_engine.presentation.report_html import render_report_html
from ai_adoption_engine.presentation.report_view import build_report_view
from tests.fakes.decision_support import sample_integrated_assessment


@pytest.fixture(scope="module")
def package():
    generated = DecisionSupportPackageService().generate(sample_integrated_assessment())
    assert generated.status == "success"
    return generated.package


@pytest.fixture(scope="module")
def view(package):
    return build_report_view(package)


@pytest.fixture(scope="module")
def html(package):
    return render_report_html(package)


def _visible(html: str) -> str:
    """The report as a reader sees it before expanding any technical section."""

    return re.sub(r"<details.*?</details>", "", html, flags=re.S)


def _layer_one_text(view) -> str:
    """Headings, paragraphs and bullets — everything outside technical detail."""

    parts: list[str] = []
    for section in view:
        parts.append(section.title)
        for block in section.blocks:
            if block.heading:
                parts.append(block.heading)
            parts.extend(block.paragraphs)
            parts.extend(block.bullets)
    return "\n".join(parts)


def _layer_two_text(view) -> str:
    return "\n".join(
        detail
        for section in view
        for block in section.blocks
        for detail in block.technical_details
    )


# ---------------------------------------------------------------------------
# A. Decision-first opening
# ---------------------------------------------------------------------------


def test_report_view_opens_with_the_package_decision(package, view) -> None:
    narrative = build_package_narrative(package)
    first = view[0]

    assert first.section_id is ReportSectionId.EXECUTIVE_SUMMARY
    assert first.blocks[0].paragraphs[0] == narrative.headline
    assert first.blocks[0].paragraphs[1] == narrative.completeness_statement
    # The raw count statement is preserved, but as technical detail only.
    counts_statement = next(
        detail
        for detail in first.blocks[0].technical_details
        if "AUTOMATE=" in detail
    )
    assert counts_statement.startswith("Source statement: ")
    assert not any("AUTOMATE=" in text for text in first.blocks[0].paragraphs)


def test_html_report_opens_with_the_decision_before_any_section(package, html) -> None:
    narrative = build_package_narrative(package)

    headline_at = html.index(narrative.headline)
    assert headline_at < html.index("<section")
    assert html.index("Decision summary") < html.index("Supporting decision detail")
    assert html.index("Supporting decision detail") < html.index("<section")
    # No fingerprint or identifier before the decision.
    prologue = html[:headline_at]
    assert package.source.policy.decision_policy_fingerprint not in prologue
    assert package.source.lineage.validated_process_fingerprint not in prologue
    assert package.package_id not in prologue


def test_html_prologue_matches_the_in_app_projection(package, html) -> None:
    narrative = build_package_narrative(package)
    visible = _visible(html)

    for heading in (
        "Decision summary",
        "Why this decision was reached",
        "What this means",
        "What happens next",
        "Risks and limitations",
    ):
        assert f"<h2>{heading}</h2>" in visible
    for line in (
        narrative.headline,
        narrative.completeness_statement,
        *narrative.why,
        *narrative.what_this_means,
        *narrative.next_action,
        *narrative.limitations,
    ):
        assert escape(line) in visible


# ---------------------------------------------------------------------------
# B. Missing information stays evidence-bounded
# ---------------------------------------------------------------------------


def test_structured_gaps_are_rendered_in_business_wording(view) -> None:
    gaps = next(
        section
        for section in view
        if section.section_id is ReportSectionId.MISSING_INFORMATION
    )
    bullets = [bullet for block in gaps.blocks for bullet in block.bullets]

    assert (
        "Data readiness: the available evidence does not establish whether the "
        "data this activity relies on is ready for AI use."
    ) in bullets
    assert (
        "Implementation complexity: this is recorded as an assumption and still "
        "requires confirmation."
    ) in bullets
    # The replaced authoritative messages remain reachable as technical detail.
    technical = _layer_two_text(view)
    assert "Source record: data_readiness is unknown and remains visible." in technical
    assert any("implementation_complexity is inferred" in line for line in technical.splitlines())


def test_unknown_gaps_are_not_turned_into_invented_sub_gaps(view, html) -> None:
    layer_one = _layer_one_text(view).lower()
    visible = _visible(html).lower()

    for invented in (
        "data is not ready",
        "data is poor",
        "data quality",
        "accuracy threshold",
        "exception-handling information",
    ):
        assert invented not in layer_one
        assert invented not in visible


# ---------------------------------------------------------------------------
# C. Limitations remain prominent
# ---------------------------------------------------------------------------


def test_limitations_are_visible_without_expanding_anything(package, html) -> None:
    visible = _visible(html)

    assert package.roi_statement in visible
    assert (
        "This package is decision support. It does not approve deployment or "
        "implementation."
    ) in visible
    assert (
        "The proposed future-state workflow is a proposal. Nothing in it has "
        "been deployed."
    ) in visible
    assert (
        "This package provides no legal conclusion, no security approval and "
        "no judgement that anything is ready for deployment."
    ) in visible


# ---------------------------------------------------------------------------
# D. Vocabulary: raw internal tokens live in the technical layer
# ---------------------------------------------------------------------------


def test_raw_internal_tokens_do_not_appear_in_the_visible_report(package, html) -> None:
    visible = _visible(html)

    for token in (
        "COMPLETE_WITH_INFORMATION_GAPS",
        "INVESTIGATE_FURTHER",
        "DO_NOT_RECOMMEND",
        "Investigate Further",
        "Do Not Recommend",
        "ASSESSMENT_FINDING",
        "DERIVED_PLANNING_GUIDANCE",
        "NEEDS_CONFIRMATION",
        "AI_ENABLED_EXECUTION",
        "QUALIFYING_OPPORTUNITY",
        "(HIGH)",
        "AUTOMATE=",
        package.package_id,
        package.source.policy.decision_policy_fingerprint,
        package.source.lineage.validated_process_fingerprint,
        package.source.integrated_assessment_run_id,
    ):
        assert token not in visible, token


def test_business_labels_replace_raw_recommendation_tokens(view) -> None:
    portfolio = next(
        section
        for section in view
        if section.section_id is ReportSectionId.OPPORTUNITY_PORTFOLIO
    )
    recommendations = [
        paragraph
        for block in portfolio.blocks
        for paragraph in block.paragraphs
        if paragraph.startswith("Recommendation: ")
    ]

    assert "Recommendation: More information needed" in recommendations
    assert "Recommendation: Not recommended" in recommendations
    assert not any("INVESTIGATE" in item for item in recommendations)
    # The reason line restates the persisted deciding check, not engine prose.
    reasons = [
        paragraph
        for block in portfolio.blocks
        for paragraph in block.paragraphs
        if paragraph.startswith("Reason / basis: ")
    ]
    assert (
        "Reason / basis: The Technical fit check could not be completed because "
        "the available evidence does not establish whether the data this "
        "activity relies on is ready for AI use."
    ) in reasons


# ---------------------------------------------------------------------------
# E. Technical completeness: everything remains reachable
# ---------------------------------------------------------------------------


def test_reproducibility_values_remain_reachable_in_the_html(package, html) -> None:
    narrative = build_package_narrative(package)

    for line in narrative.technical_reference:
        assert line in html
    # Planning origins, step identifiers and engine rationale are relocated,
    # not removed.
    assert "Origin: ASSESSMENT_FINDING" in html
    assert "Origin: DERIVED_PLANNING_GUIDANCE" in html
    assert "Internal step ID:" in html
    assert "Engine rationale:" in html
    for item in package.portfolio.items:
        assert item.step_id in html


def test_engine_rationale_is_preserved_verbatim_in_the_technical_layer(
    package, view
) -> None:
    technical = _layer_two_text(view)
    portfolio = next(
        section
        for section in view
        if section.section_id is ReportSectionId.OPPORTUNITY_PORTFOLIO
    )
    rationale_lines = [
        detail
        for block in portfolio.blocks
        for detail in block.technical_details
        if detail.startswith("Engine rationale: ")
    ]
    assert len(rationale_lines) == len(package.portfolio.items)
    assert "Recommendation mode: INVESTIGATE_FURTHER" in technical
    assert "Recommendation mode: DO_NOT_RECOMMEND" in technical


# ---------------------------------------------------------------------------
# F. Section integrity: the 13-section contract is untouched
# ---------------------------------------------------------------------------


def test_all_thirteen_sections_remain_present_in_enum_order(package, view, html) -> None:
    assert [section.section_id for section in view] == list(ReportSectionId)
    assert [
        section.section_id for section in package.report_content.sections
    ] == list(ReportSectionId)
    for section_id in ReportSectionId:
        assert f"<section id='{section_id.value}'>" in html


# ---------------------------------------------------------------------------
# G. HTML determinism and consistency
# ---------------------------------------------------------------------------


def test_html_report_remains_deterministic(package) -> None:
    assert render_report_html(package) == render_report_html(package)


# ---------------------------------------------------------------------------
# H. No unsupported positive claims
# ---------------------------------------------------------------------------


def test_visible_report_makes_no_unsupported_positive_claim(html) -> None:
    """Ban unsupported positive claims, never the vocabulary of limitations.

    "not guaranteed implementation advice" is a required disclosure; a bare
    "guaranteed" assertion is not.  Sensitive phrases are therefore checked
    for a negator in their sentence, exactly as the ROI rule requires.
    """

    visible = _visible(html).lower()

    for claim in (
        "will improve",
        "will reduce",
        "will increase",
        "costs will fall",
        "roi will increase",
        "proven suitable",
        "proven roi",
        "best practice",
    ):
        assert claim not in visible, claim

    text = re.sub(r"<[^>]+>", " ", visible)
    sentences = [part.strip() for part in text.split(".") if part.strip()]
    negators = ("no ", "not ", "never", "does not", "outside this product")
    for sensitive in (
        "guaranteed",
        "safe to deploy",
        "deployment ready",
        "ready for deployment",
    ):
        for sentence in sentences:
            if sensitive in sentence:
                assert any(word in sentence for word in negators), sentence

    # The ROI limitation must be stated; the token itself is not banned.
    assert "return on investment (roi)" in visible
