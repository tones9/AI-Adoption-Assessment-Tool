"""Deterministic HTML projection of one completed controlled reassessment."""

from __future__ import annotations

from html import escape

from ai_adoption_engine.application.decision_continuation import (
    DecisionContinuationControlledReport,
)


def _human(value: str | None) -> str:
    if value is None:
        return "Not present"
    return value.replace("_", " ").replace("-", " ").title()


def _criterion_value(value: int | None, knowledge_state: str) -> str:
    rendered = "Unknown" if value is None else str(value)
    return f"{rendered} ({_human(knowledge_state)})"


def _paragraph(label: str, value: str) -> str:
    return f"<p><strong>{escape(label)}:</strong> {escape(value)}</p>"


def _optional_paragraph(label: str, value: str | None) -> str:
    return _paragraph(label, value) if value else ""


def render_controlled_reassessment_report_html(
    report: DecisionContinuationControlledReport,
) -> str:
    """Render persisted human-reviewed values without changing canonical artifacts."""

    baseline_rationale = "".join(
        f"<li>{escape(item)}</li>" for item in report.baseline_rationale
    )
    successor_rationale = "".join(
        f"<li>{escape(item)}</li>" for item in report.successor_rationale
    )
    gates = "".join(
        "<div class='comparison-item'>"
        f"<h3>{escape(_human(item.gate))}</h3>"
        + _paragraph("Baseline status", _human(item.baseline_status))
        + _optional_paragraph("Baseline rationale", item.baseline_rationale)
        + _paragraph("Successor status", _human(item.successor_status))
        + _optional_paragraph("Successor rationale", item.successor_rationale)
        + "</div>"
        for item in report.gate_differences
    )
    if not gates:
        gates = "<p>No gate difference was recorded.</p>"
    lineage = "".join(
        "<li>"
        f"<strong>{escape(item.label)}</strong>: {escape(item.artifact_id)} "
        f"(revision {item.artifact_revision})<br>"
        f"SHA-256: <code>{escape(item.payload_sha256)}</code>"
        "</li>"
        for item in report.lineage
    )
    evidence = report.evidence
    change = report.approved_change
    categories = ", ".join(_human(item) for item in report.comparison_categories)

    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Controlled Reassessment Decision Report</title>
<style>
body{font-family:Arial,sans-serif;color:#17211f;max-width:980px;margin:40px auto;padding:0 24px;line-height:1.55}
h1{font-size:2rem;border-bottom:4px solid #1f5a54;padding-bottom:12px}h2{margin-top:32px;color:#1f5a54}
h3{font-size:1.05rem;margin:16px 0 6px}.meta,.notice{background:#edf1ee;padding:16px;border-radius:8px}
.notice{border-left:5px solid #a35f00}.comparison-item{margin:12px 0;padding:12px 16px;border-left:3px solid #c7d3cf}
blockquote{background:#f5f7f6;border-left:4px solid #70847d;margin:12px 0;padding:12px 16px;white-space:pre-wrap}
code{overflow-wrap:anywhere}li{margin:8px 0}details{margin-top:24px;color:#46514e;font-size:.9rem}
@media print{body{margin:0}section,.comparison-item{break-inside:avoid}}
</style></head><body>""" + (
        "<h1>Controlled Reassessment Decision Report</h1>"
        f"<div class='meta'><strong>Activity:</strong> {escape(report.current_activity)}<br>"
        f"<strong>Reviewed field:</strong> {escape(report.field_name)}<br>"
        f"<strong>Reassessment run:</strong> {escape(report.run_id)}</div>"
        "<p class='notice'>This report records a separate decision after approved additional evidence. "
        "The original baseline remains unchanged. Recommendation movement is not a measured outcome, "
        "ROI result, deployment approval, or evidence of adoption success.</p>"
        "<section id='baseline-summary'><h2>1. Original baseline decision</h2>"
        + _paragraph("Baseline package", report.baseline_package_id)
        + _paragraph(
            "Baseline data-readiness value",
            _criterion_value(report.baseline_value, report.baseline_knowledge_state),
        )
        + _paragraph("Baseline recommendation", _human(report.baseline_recommendation))
        + (f"<ul>{baseline_rationale}</ul>" if baseline_rationale else "")
        + "<p><strong>The baseline Decision Package remains unchanged and is not overwritten by this successor.</strong></p>"
        "</section>"
        "<section id='approved-change'><h2>2. Approved controlled change</h2>"
        + _paragraph("Approved reason for reassessment", change.approval_reason)
        + _paragraph("Exact approved change", change.exact_change)
        + _paragraph("Instrument mapping rationale", change.mapping_rationale)
        + _paragraph("Retained uncertainty", change.retained_uncertainty)
        + "</section>"
        "<section id='evidence-basis'><h2>3. Approved evidence basis</h2>"
        + _paragraph("Document", evidence.filename)
        + _paragraph("Source", evidence.source_label)
        + _paragraph("Document SHA-256", evidence.content_sha256)
        + _paragraph(
            "Locator",
            f"Lines {evidence.line_start}-{evidence.line_end}; characters "
            f"{evidence.start_offset}-{evidence.end_offset}",
        )
        + f"<blockquote>{escape(evidence.exact_excerpt)}</blockquote>"
        + _paragraph("Source authority", evidence.source_authority)
        + _paragraph("Scope", evidence.scope_statement)
        + _paragraph("Period or limitation", evidence.period_statement)
        + _paragraph("Evidence-review rationale", evidence.semantic_rationale)
        + _paragraph("Limitations retained", evidence.limitations)
        + _paragraph("Conflict status", _human(evidence.conflict_status))
        + _paragraph("Conflict rationale", evidence.conflict_rationale)
        + _optional_paragraph("Reconciliation", evidence.reconciliation_statement)
        + _optional_paragraph("Applicability", evidence.applicability_statement)
        + "</section>"
        "<section id='successor-comparison'><h2>4. Separate successor comparison</h2>"
        + _paragraph("Successor package", report.successor_package_id)
        + _paragraph(
            "Successor data-readiness value",
            _criterion_value(report.successor_value, report.successor_knowledge_state),
        )
        + _paragraph("Successor recommendation", _human(report.successor_recommendation))
        + (f"<ul>{successor_rationale}</ul>" if successor_rationale else "")
        + "<h3>Relevant gate differences</h3>"
        + gates
        + _paragraph("Recorded comparison categories", categories)
        + f"<p class='notice'>{escape(report.neutral_explanation)}</p>"
        + "</section>"
        "<details><summary>5. Technical lineage appendix</summary>"
        + _paragraph("Changed field path", change.changed_field_path)
        + _paragraph("Supporting document ID", evidence.document_id)
        + f"<ul>{lineage}</ul></details>"
        "</body></html>"
    )
