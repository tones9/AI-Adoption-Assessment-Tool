"""Deterministic, print-friendly HTML rendering of Phase 6 report content.

The exported report tells the same story as the in-app Decision Package: it
opens with the business decision projected by ``decision_narrative`` and keeps
identifiers, fingerprints and planning-origin tokens inside ``details``
elements labelled with the canonical ``Technical reasoning and evidence``
control.  Nothing authoritative is removed; technical values are relocated.
"""

from __future__ import annotations

from html import escape

from ai_adoption_engine.models.decision_support import DecisionSupportPackage
from ai_adoption_engine.presentation.components.technical_details import (
    TECHNICAL_DETAILS_LABEL,
)
from ai_adoption_engine.presentation.decision_narrative import (
    build_package_narrative,
)
from ai_adoption_engine.presentation.report_view import (
    ReportViewBlock,
    build_report_view,
)


def render_report_html(package: DecisionSupportPackage) -> str:
    """Render a business-facing view without mutating canonical package records."""

    narrative = build_package_narrative(package)
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
h3{font-size:1.05rem;margin:20px 0 6px}.context{color:#46514e;font-size:.9rem}
.headline{font-size:1.25rem;font-weight:700}.prologue p{margin:8px 0}
.report-item{margin:12px 0 18px;padding:12px 16px;border-left:3px solid #c7d3cf}
.origin{font-size:.72rem;font-weight:700;letter-spacing:.03em;background:#e3e9e6;padding:3px 6px;border-radius:4px}
.label{font-weight:700}li{margin:8px 0}details{margin-top:8px;color:#46514e;font-size:.86rem}
.technical-appendix{margin-top:32px}
@media print{body{margin:0}.no-print{display:none}section{break-inside:avoid}.report-item{break-inside:avoid}}
</style></head><body>""" + (
        "<h1>AI Adoption Decision Support Report</h1>"
        + _render_prologue(narrative)
        + "<h2>Supporting decision detail</h2>"
        + "<p>The sections below are the full record of this decision.</p>"
        + sections
        + _render_technical_appendix(narrative)
        + "</body></html>"
    )


def _render_prologue(narrative) -> str:
    """Open with the same Layer 1 the Decision Package page shows."""

    parts = [
        "<div class='prologue'>",
        f"<p class='context'>Decision Package · {escape(narrative.process_name)}</p>",
        "<h2>Decision summary</h2>",
        f"<p class='headline'>{escape(narrative.headline)}</p>",
        f"<p>{escape(narrative.completeness_statement)}</p>",
    ]
    for heading, lines in (
        ("Why this decision was reached", narrative.why),
        ("What this means", narrative.what_this_means),
        ("What happens next", narrative.next_action),
        ("Risks and limitations", narrative.limitations),
    ):
        if not lines:
            continue
        parts.append(f"<h2>{escape(heading)}</h2>")
        parts.extend(f"<p>{escape(line)}</p>" for line in lines)
    parts.append("</div>")
    return "".join(parts)


def _render_technical_appendix(narrative) -> str:
    """Keep every reproducibility identifier reachable, later and collapsed."""

    return (
        "<details class='technical-appendix'>"
        f"<summary>{escape(TECHNICAL_DETAILS_LABEL)}</summary><ul>"
        + "".join(
            f"<li>{escape(line)}</li>" for line in narrative.technical_reference
        )
        + "</ul></details>"
    )


def _render_block(block: ReportViewBlock) -> str:
    heading = f"<h3>{escape(block.heading)}</h3>" if block.heading else ""
    paragraphs = "".join(f"<p>{_labelled_text(item)}</p>" for item in block.paragraphs)
    bullets = (
        "<ul>" + "".join(f"<li>{escape(item)}</li>" for item in block.bullets) + "</ul>"
        if block.bullets
        else ""
    )
    technical = ""
    if block.origin or block.technical_details:
        origin = (
            f"<p class='origin'>Origin: {escape(block.origin.value)}</p>"
            if block.origin
            else ""
        )
        detail_list = (
            "<ul>"
            + "".join(f"<li>{escape(item)}</li>" for item in block.technical_details)
            + "</ul>"
            if block.technical_details
            else ""
        )
        technical = (
            f"<details><summary>{escape(TECHNICAL_DETAILS_LABEL)}</summary>"
            + origin
            + detail_list
            + "</details>"
        )
    return (
        "<div class='report-item'>"
        + heading
        + paragraphs
        + bullets
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
