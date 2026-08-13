"""Deterministic, print-friendly HTML rendering of Phase 6 report content."""

from __future__ import annotations

from html import escape

from ai_adoption_engine.models.decision_support import DecisionSupportPackage
from ai_adoption_engine.presentation.report_view import (
    ReportViewBlock,
    build_report_view,
)


def render_report_html(package: DecisionSupportPackage) -> str:
    """Render a business-facing view without mutating canonical package records."""

    sections = "".join(
        f"<section id='{escape(section.section_id.value)}'>"
        f"<h2>{escape(section.title)}</h2>"
        + "".join(_render_block(block) for block in section.blocks)
        + "</section>"
        for section in build_report_view(package)
    )
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Adoption Decision Support Report</title>
<style>
body{font-family:Arial,sans-serif;color:#17211f;max-width:980px;margin:40px auto;padding:0 24px;line-height:1.55}
h1{font-size:2rem;border-bottom:4px solid #1f5a54;padding-bottom:12px}h2{margin-top:32px;color:#1f5a54}
h3{font-size:1.05rem;margin:20px 0 6px}.meta,.notice{background:#edf1ee;padding:16px;border-radius:8px}
.notice{border-left:5px solid #a35f00}.report-item{margin:12px 0 18px;padding:12px 16px;border-left:3px solid #c7d3cf}
.origin{font-size:.72rem;font-weight:700;letter-spacing:.03em;background:#e3e9e6;padding:3px 6px;border-radius:4px}
.label{font-weight:700}li{margin:8px 0}details{margin-top:8px;color:#46514e;font-size:.86rem}
@media print{body{margin:0}.no-print{display:none}section{break-inside:avoid}.report-item{break-inside:avoid}}
</style></head><body>""" + (
        "<h1>AI Adoption Decision Support Report</h1>"
        f"<div class='meta'><strong>Process:</strong> {escape(package.current_state.process_name)}<br>"
        f"<strong>Process fingerprint:</strong> {escape(package.source.lineage.validated_process_fingerprint)}<br>"
        f"<strong>Policy:</strong> {escape(package.source.policy.policy_id)} {escape(package.source.policy.policy_version)}<br>"
        f"<strong>Policy fingerprint:</strong> {escape(package.source.policy.decision_policy_fingerprint)}</div>"
        f"<p class='notice'><strong>{escape(package.future_state.status.value)}</strong><br>"
        f"{escape(package.roi_statement)}</p>"
        + sections
        + "</body></html>"
    )


def _render_block(block: ReportViewBlock) -> str:
    heading = f"<h3>{escape(block.heading)}</h3>" if block.heading else ""
    paragraphs = "".join(f"<p>{_labelled_text(item)}</p>" for item in block.paragraphs)
    bullets = (
        "<ul>" + "".join(f"<li>{escape(item)}</li>" for item in block.bullets) + "</ul>"
        if block.bullets
        else ""
    )
    origin = (
        f"<span class='origin'>{escape(block.origin.value)}</span>"
        if block.origin
        else ""
    )
    technical = (
        "<details><summary>Technical traceability</summary><ul>"
        + "".join(f"<li>{escape(item)}</li>" for item in block.technical_details)
        + "</ul></details>"
        if block.technical_details
        else ""
    )
    return (
        "<div class='report-item'>"
        + heading
        + paragraphs
        + bullets
        + origin
        + technical
        + "</div>"
    )


def _labelled_text(value: str) -> str:
    """Emphasise a known label while escaping all untrusted content."""

    for label in (
        "Recommendation",
        "Reason / basis",
        "Material missing information",
        "Next action",
        "Status",
    ):
        prefix = f"{label}: "
        if value.startswith(prefix):
            return f"<span class='label'>{escape(label)}:</span> {escape(value[len(prefix):])}"
    return escape(value)
