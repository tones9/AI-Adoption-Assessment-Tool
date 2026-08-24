"""The controlled reassessment report follows the frozen Decision Experience.

One projection, ``build_controlled_reassessment_narrative``, feeds both the
Decision Continuation Workspace and the downloadable HTML, so the two surfaces
cannot tell different stories about the same reassessment.  These tests assert
the business layer, the neutrality rules, and that every identifier, hash,
locator and engine rationale is still reachable in the technical appendix.
"""

from __future__ import annotations

from html import escape

import pytest

from ai_adoption_engine.application.decision_continuation import (
    DecisionContinuationService,
)
from ai_adoption_engine.grw.m2.service import M2ReassessmentService
from ai_adoption_engine.persistence.reassessment import SQLiteReassessmentRepository
from ai_adoption_engine.presentation.controlled_reassessment_report import (
    build_controlled_reassessment_narrative,
    render_controlled_reassessment_report_html,
)
from ai_adoption_engine.workspace.service import AssessmentWorkspaceService
from tests.integration.test_grw_m2_m1_lifecycle import _full_lifecycle


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    repository, assessment_id, *_ = _full_lifecycle(tmp_path_factory.mktemp("m2"))
    workspace = AssessmentWorkspaceService(
        repository, extraction_service_factory=lambda *_args: None
    )
    view = DecisionContinuationService(
        workspace,
        M2ReassessmentService(repository, SQLiteReassessmentRepository(repository.path)),
    ).open(assessment_id)
    controlled = view.m2_runs[0].controlled_report
    assert controlled is not None
    return controlled


@pytest.fixture(scope="module")
def narrative(report):
    return build_controlled_reassessment_narrative(report)


@pytest.fixture(scope="module")
def html(report):
    return render_controlled_reassessment_report_html(report)


# ---------------------------------------------------------------------------
# A. The original decision comes first and stays untouched
# ---------------------------------------------------------------------------


def test_the_original_decision_is_identified_first(narrative, report) -> None:
    assert narrative.original_decision[0] == (
        "This was your original official decision for this activity."
    )
    assert any("Recommendation: " in line for line in narrative.original_decision)
    assert narrative.purpose[1] == f"Activity: {report.current_activity}"


def test_the_original_package_is_stated_as_unrewritten(narrative) -> None:
    assert (
        "Your original Decision Package was not rewritten. It remains exactly as "
        "it was recorded." in narrative.unchanged
    )
    assert any("Every other assessment input stayed as it was." in line for line in narrative.unchanged)
    assert (
        "The assessment method and the decision policy did not change."
        in narrative.unchanged
    )
    assert (
        "Your original decision remains the authoritative record for the evidence "
        "it was based on." in narrative.limitations
    )


# ---------------------------------------------------------------------------
# B. The approved evidence is exact and nothing is invented
# ---------------------------------------------------------------------------


def test_approved_evidence_shows_exactly_what_was_reviewed(narrative, report) -> None:
    evidence = report.evidence
    joined = "\n".join(narrative.approved_evidence)

    for value in (
        evidence.filename,
        evidence.source_label,
        evidence.source_authority,
        evidence.scope_statement,
        evidence.period_statement,
        evidence.semantic_rationale,
        evidence.limitations,
        evidence.conflict_rationale,
    ):
        assert value in joined, value
    assert narrative.evidence_excerpt == evidence.exact_excerpt
    assert (
        f"It was approved to address one recorded question only: "
        f"{narrative.criterion_label}." in joined
    )


def test_no_sub_facts_are_invented_from_the_document(narrative) -> None:
    business = " ".join(narrative.business_lines()).lower()
    for invented in (
        "data quality",
        "accuracy threshold",
        "exception handling",
        "the data became ready",
        "data is now ready",
    ):
        assert invented not in business


# ---------------------------------------------------------------------------
# C. Criterion values read as business language
# ---------------------------------------------------------------------------


def test_criterion_values_use_business_labels_in_the_business_layer(
    narrative, report
) -> None:
    business = " ".join(narrative.business_lines())

    assert "Not established by the evidence" in business
    assert "3 out of 5 — confirmed by the evidence" in business
    assert "Unknown (Unknown)" not in business
    assert "3 (Known)" not in business
    for token in ("known", "unknown", "inferred"):
        assert f"({token})" not in business

    assert narrative.input_change[0] == (
        "The approved evidence changed the recorded data readiness assessment "
        "from \u201cNot established by the evidence\u201d to \u201c3 out of 5 — "
        "confirmed by the evidence\u201d."
    )


def test_raw_values_and_knowledge_states_stay_in_the_technical_layer(
    narrative, report
) -> None:
    technical = "\n".join(narrative.technical)

    assert f"Baseline recorded value: {report.baseline_value} " in technical
    assert report.baseline_knowledge_state in technical
    assert f"Successor recorded value: {report.successor_value} " in technical
    assert report.successor_knowledge_state in technical
    assert report.baseline_recommendation in technical
    assert report.successor_recommendation in technical


# ---------------------------------------------------------------------------
# D. The successor is separate
# ---------------------------------------------------------------------------


def test_successor_is_presented_as_separate_not_as_a_replacement(narrative) -> None:
    joined = "\n".join(narrative.successor_decision)

    assert (
        "A separate reassessment was produced using the approved evidence above."
        in joined
    )
    assert (
        "This is a separate decision. It sits alongside your original decision "
        "and does not replace it." in joined
    )
    business = " ".join(narrative.business_lines()).lower()
    for rewrite in ("replaces", "supersedes", "overwrites", "instead of the original"):
        assert rewrite not in business


# ---------------------------------------------------------------------------
# E. Comparison neutrality
# ---------------------------------------------------------------------------


def test_comparison_is_neutral_and_deterministic(narrative, report) -> None:
    assert narrative.comparison[0].startswith("Original decision: ")
    assert "Separate reassessment: " in narrative.comparison[0]
    # The authoritative neutral explanation is carried verbatim.
    assert report.neutral_explanation in narrative.comparison

    for line in narrative.gate_differences:
        assert "→" in line or line.startswith("No difference")

    for sentence in " ".join(narrative.business_lines()).split("."):
        lowered = sentence.lower()
        for framing in ("improved", "better", "successful", "upgraded", "corrected"):
            assert framing not in lowered, sentence


# ---------------------------------------------------------------------------
# F. Technical completeness
# ---------------------------------------------------------------------------


def test_every_reproducibility_value_remains_reachable(narrative, report) -> None:
    technical = "\n".join(narrative.technical)

    for token in (
        report.run_id,
        report.field_name,
        report.approved_change.changed_field_path,
        report.baseline_package_id,
        report.successor_package_id,
        report.evidence.document_id,
        report.evidence.content_sha256,
        str(report.evidence.start_offset),
        str(report.evidence.end_offset),
        report.evidence.conflict_status,
    ):
        assert token in technical, token

    for rationale in (*report.baseline_rationale, *report.successor_rationale):
        assert rationale in technical
    for gate in report.gate_differences:
        assert f"Gate {gate.gate}:" in technical
    for item in report.lineage:
        assert item.artifact_id in technical
        assert item.payload_sha256 in technical
    for category in report.comparison_categories:
        assert category in technical


# ---------------------------------------------------------------------------
# G. HTML determinism, escaping, and parity with the in-app surface
# ---------------------------------------------------------------------------


def test_html_is_deterministic_and_carries_the_same_business_lines(
    report, narrative, html
) -> None:
    assert html == render_controlled_reassessment_report_html(report)
    for line in narrative.business_lines():
        assert escape(line) in html, line


def test_html_keeps_the_technical_appendix_after_the_business_layer(
    narrative, html
) -> None:
    body, appendix = html.split("<details>", 1)
    for line in narrative.business_lines():
        assert escape(line) in body
    for line in narrative.technical:
        assert escape(line) in appendix
    assert "Technical reasoning and evidence" in appendix


def test_html_escapes_the_evidence_excerpt(report) -> None:
    from dataclasses import replace

    hostile = "<script>alert('evidence')</script>"
    rendered = render_controlled_reassessment_report_html(
        replace(report, evidence=replace(report.evidence, exact_excerpt=hostile))
    )

    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
