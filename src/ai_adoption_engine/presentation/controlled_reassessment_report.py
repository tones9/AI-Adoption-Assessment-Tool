"""One controlled reassessment, told the same way in the app and in the export.

The projection below is the single source of the business story; the Streamlit
page and this module's HTML renderer both consume it, so the two surfaces cannot
describe the same reassessment differently.

Every sentence restates a persisted, human-reviewed field of
``DecisionContinuationControlledReport``.  Nothing here interprets the evidence,
re-runs a comparison, or judges whether the separate successor is better: a
successor is a separate reassessment produced using additional approved
evidence, and that is all this report may say about it.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape

from ai_adoption_engine.application.decision_continuation import (
    DecisionContinuationControlledReport,
)
from ai_adoption_engine.models.enums import RecommendationMode
from ai_adoption_engine.presentation import labels
from ai_adoption_engine.presentation.components.technical_details import (
    TECHNICAL_DETAILS_LABEL,
)


@dataclass(frozen=True)
class ControlledReassessmentNarrative:
    """Business-facing blocks for one completed controlled reassessment."""

    activity: str
    criterion_label: str
    purpose: tuple[str, ...]
    original_decision: tuple[str, ...]
    approved_evidence: tuple[str, ...]
    evidence_excerpt: str
    input_change: tuple[str, ...]
    unchanged: tuple[str, ...]
    successor_decision: tuple[str, ...]
    comparison: tuple[str, ...]
    gate_differences: tuple[str, ...]
    limitations: tuple[str, ...]
    technical: tuple[str, ...]

    def business_lines(self) -> tuple[str, ...]:
        """Return exactly the Layer 1 text, excluding the technical appendix."""

        return (
            *self.purpose,
            *self.original_decision,
            *self.approved_evidence,
            *self.input_change,
            *self.unchanged,
            *self.successor_decision,
            *self.comparison,
            *self.gate_differences,
            *self.limitations,
        )


def _gate_status(value: str | None, recommendation: str) -> str:
    """Name one side's recorded check status for that side's own outcome.

    A ``failed`` check on a side whose recommendation is ``INVESTIGATE_FURTHER``
    stopped because a required fact was never established, and must not be read
    as a negative finding.  ``recommendation`` is the persisted recommendation
    for that side of the comparison; nothing here reads a rationale string or
    recomputes a gate.
    """

    if not value:
        return "Not recorded"
    return labels.gate_status_label(
        value,
        outcome_unestablished=recommendation
        == RecommendationMode.INVESTIGATE_FURTHER.value,
    )


def build_controlled_reassessment_narrative(
    report: DecisionContinuationControlledReport,
) -> ControlledReassessmentNarrative:
    """Project one persisted controlled reassessment into business language."""

    criterion = labels.criterion_label(report.field_name)
    before = labels.criterion_value_display(
        report.baseline_value, report.baseline_knowledge_state
    )
    after = labels.criterion_value_display(
        report.successor_value, report.successor_knowledge_state
    )
    change = report.approved_change
    evidence = report.evidence

    unchanged = []
    if change.baseline_remains_active:
        unchanged.append(
            "Your original Decision Package was not rewritten. It remains exactly "
            "as it was recorded."
        )
    unchanged.extend(
        (
            f"Only {criterion.lower()} was allowed to change. Every other "
            "assessment input stayed as it was.",
            "The assessment method and the decision policy did not change.",
            "The approved evidence was not used to make any wider claim about "
            "this process.",
        )
    )

    approved_evidence = [
        f"Document: {evidence.filename}",
        f"Source: {evidence.source_label}",
        f"Source authority: {evidence.source_authority}",
        f"Scope of the evidence: {evidence.scope_statement}",
        f"Period or limitation: {evidence.period_statement}",
        f"Why the reviewer accepted it: {evidence.semantic_rationale}",
        f"Limitations kept on the record: {evidence.limitations}",
        "Relationship to the original evidence: "
        + labels.human_label(evidence.conflict_status),
        f"Reviewer's note on that relationship: {evidence.conflict_rationale}",
        f"It was approved to address one recorded question only: {criterion}.",
    ]
    if evidence.reconciliation_statement:
        approved_evidence.append(
            f"How the reviewer reconciled it: {evidence.reconciliation_statement}"
        )
    if evidence.applicability_statement:
        approved_evidence.append(
            f"Why it applies to this activity: {evidence.applicability_statement}"
        )

    technical = [
        f"Reassessment run: {report.run_id}",
        f"Reviewed field: {report.field_name}",
        f"Changed field path: {change.changed_field_path}",
        f"Baseline package ID: {report.baseline_package_id}",
        f"Baseline recorded value: {report.baseline_value} "
        f"({report.baseline_knowledge_state})",
        f"Baseline recommendation: {report.baseline_recommendation}",
        f"Successor package ID: {report.successor_package_id}",
        f"Successor recorded value: {report.successor_value} "
        f"({report.successor_knowledge_state})",
        f"Successor recommendation: {report.successor_recommendation}",
        f"Supporting document ID: {evidence.document_id}",
        f"Document SHA-256: {evidence.content_sha256}",
        f"Locator: lines {evidence.line_start}-{evidence.line_end}; characters "
        f"{evidence.start_offset}-{evidence.end_offset}",
        f"Conflict status: {evidence.conflict_status}",
        "Comparison categories: " + ", ".join(report.comparison_categories),
    ]
    technical.extend(
        f"Baseline engine rationale: {item}" for item in report.baseline_rationale
    )
    technical.extend(
        f"Successor engine rationale: {item}" for item in report.successor_rationale
    )
    for gate in report.gate_differences:
        technical.append(
            f"Gate {gate.gate}: {gate.baseline_status} -> {gate.successor_status}"
        )
        if gate.baseline_rationale:
            technical.append(f"Gate {gate.gate} baseline rationale: {gate.baseline_rationale}")
        if gate.successor_rationale:
            technical.append(
                f"Gate {gate.gate} successor rationale: {gate.successor_rationale}"
            )
    technical.extend(
        f"{item.label}: {item.artifact_id} (revision {item.artifact_revision}) "
        f"SHA-256: {item.payload_sha256}"
        for item in report.lineage
    )

    return ControlledReassessmentNarrative(
        activity=report.current_activity,
        criterion_label=criterion,
        purpose=(
            "This report records a separate reassessment of one activity, made "
            "after additional evidence was reviewed and approved.",
            f"Activity: {report.current_activity}",
        ),
        original_decision=(
            "This was your original official decision for this activity.",
            "Recommendation: "
            + labels.recommendation_label(report.baseline_recommendation),
            f"{criterion}: {before}",
        ),
        approved_evidence=tuple(approved_evidence),
        evidence_excerpt=evidence.exact_excerpt,
        input_change=(
            f"The approved evidence changed the recorded {criterion.lower()} "
            f"assessment from \u201c{before}\u201d to \u201c{after}\u201d.",
            f"Approved reason for reassessing: {change.approval_reason}",
            f"Exact approved change: {change.exact_change}",
            f"How the evidence was mapped to that value: {change.mapping_rationale}",
            f"Uncertainty that remains: {change.retained_uncertainty}",
        ),
        unchanged=tuple(unchanged),
        successor_decision=(
            "A separate reassessment was produced using the approved evidence "
            "above.",
            "Recommendation: "
            + labels.recommendation_label(report.successor_recommendation),
            f"{criterion}: {after}",
            "This is a separate decision. It sits alongside your original "
            "decision and does not replace it.",
        ),
        comparison=(
            "Original decision: "
            + labels.recommendation_label(report.baseline_recommendation)
            + " · Separate reassessment: "
            + labels.recommendation_label(report.successor_recommendation),
            report.neutral_explanation,
        ),
        gate_differences=tuple(
            f"{labels.gate_name_label(gate.gate)}: "
            f"{_gate_status(gate.baseline_status, report.baseline_recommendation)}"
            f" \u2192 "
            f"{_gate_status(gate.successor_status, report.successor_recommendation)}"
            for gate in report.gate_differences
        )
        or ("No difference between the assessment checks was recorded.",),
        limitations=(
            "This reassessment reflects only the additional approved evidence "
            "described above.",
            "It does not approve implementation or deployment.",
            "It does not establish Return on Investment (ROI), predictive "
            "accuracy, or safety.",
            "Your original decision remains the authoritative record for the "
            "evidence it was based on.",
            "A difference between the two decisions is not a measured outcome or "
            "evidence that adoption succeeded.",
        ),
        technical=tuple(technical),
    )


# ---------------------------------------------------------------------------
# HTML export
# ---------------------------------------------------------------------------


def _section(title: str, lines: tuple[str, ...]) -> str:
    return (
        f"<h2>{escape(title)}</h2>"
        + "".join(f"<p>{escape(line)}</p>" for line in lines)
    )


def render_controlled_reassessment_report_html(
    report: DecisionContinuationControlledReport,
) -> str:
    """Render persisted human-reviewed values without changing canonical artifacts."""

    narrative = build_controlled_reassessment_narrative(report)
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Controlled Reassessment Decision Report</title>
<style>
body{font-family:Arial,sans-serif;color:#17211f;max-width:980px;margin:40px auto;padding:0 24px;line-height:1.55}
h1{font-size:2rem;border-bottom:4px solid #1f5a54;padding-bottom:12px}h2{margin-top:32px;color:#1f5a54}
h3{font-size:1.05rem;margin:16px 0 6px}.context{color:#46514e;font-size:.9rem}
blockquote{background:#f5f7f6;border-left:4px solid #70847d;margin:12px 0;padding:12px 16px;white-space:pre-wrap}
code{overflow-wrap:anywhere}li{margin:8px 0}details{margin-top:24px;color:#46514e;font-size:.9rem}
@media print{body{margin:0}section{break-inside:avoid}}
</style></head><body>""" + (
        "<h1>Controlled Reassessment Decision Report</h1>"
        + _section("What this report is", narrative.purpose)
        + _section("Your original decision", narrative.original_decision)
        + _section("What additional evidence was approved", narrative.approved_evidence)
        + f"<blockquote>{escape(narrative.evidence_excerpt)}</blockquote>"
        + _section("What changed in the assessment input", narrative.input_change)
        + _section("What did not change", narrative.unchanged)
        + _section("The separate reassessment decision", narrative.successor_decision)
        + _section("Original decision compared with the reassessment", narrative.comparison)
        + "<h3>Assessment checks</h3>"
        + "".join(f"<p>{escape(line)}</p>" for line in narrative.gate_differences)
        + _section("Limitations", narrative.limitations)
        + f"<details><summary>{escape(TECHNICAL_DETAILS_LABEL)}</summary><ul>"
        + "".join(f"<li>{escape(line)}</li>" for line in narrative.technical)
        + "</ul></details>"
        + "</body></html>"
    )
