"""Deterministic, print-friendly HTML rendering of Phase 6 report content."""

from __future__ import annotations

from html import escape

from ai_adoption_engine.models.decision_support import DecisionSupportPackage


def render_report_html(package: DecisionSupportPackage) -> str:
    sections: list[str] = []
    for section in package.report_content.sections:
        statements = "".join(
            "<li><span class='origin'>"
            + escape(statement.origin.value)
            + "</span> "
            + escape(statement.text)
            + "</li>"
            for statement in section.statements
        )
        sections.append(
            f"<section id='{escape(section.section_id.value)}'>"
            f"<h2>{escape(section.title)}</h2><ul>{statements}</ul></section>"
        )
    disclosure = "".join(
        f"<li>{escape(item)}</li>"
        for item in package.methodology.disclosure_statements
    )
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Adoption Decision Support Report</title>
<style>
body{font-family:Arial,sans-serif;color:#17211f;max-width:980px;margin:40px auto;padding:0 24px;line-height:1.55}
h1{font-size:2rem;border-bottom:4px solid #1f5a54;padding-bottom:12px}h2{margin-top:32px;color:#1f5a54}
.meta,.notice{background:#edf1ee;padding:16px;border-radius:8px}.notice{border-left:5px solid #a35f00}
.origin{font-size:.72rem;font-weight:700;letter-spacing:.03em;background:#e3e9e6;padding:3px 6px;border-radius:4px}
li{margin:8px 0}@media print{body{margin:0}.no-print{display:none}section{break-inside:avoid}}
</style></head><body>""" + (
        "<h1>AI Adoption Decision Support Report</h1>"
        f"<div class='meta'><strong>Process:</strong> {escape(package.current_state.process_name)}<br>"
        f"<strong>Process fingerprint:</strong> {escape(package.source.lineage.validated_process_fingerprint)}<br>"
        f"<strong>Policy:</strong> {escape(package.source.policy.policy_id)} {escape(package.source.policy.policy_version)}<br>"
        f"<strong>Policy fingerprint:</strong> {escape(package.source.policy.decision_policy_fingerprint)}</div>"
        f"<p class='notice'><strong>{escape(package.future_state.status.value)}</strong><br>"
        f"{escape(package.roi_statement)}</p>"
        + "".join(sections)
        + f"<section><h2>Required methodology disclosure</h2><ul>{disclosure}</ul></section>"
        + "</body></html>"
    )

