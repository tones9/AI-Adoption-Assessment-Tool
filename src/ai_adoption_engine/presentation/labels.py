"""Business-facing vocabulary for the presentation layer.

This module is **vocabulary infrastructure only**.  It maps an internal token
to the words a business reader sees.  It must never contain assessment logic,
scoring, policy, or composed interpretation: composing a business statement is
the job of ``decision_narrative``, and the authoritative meaning of every token
belongs to the Engine.

Governed by ``docs/portfolio-v1-decision-experience-design-v0.1.md`` section 7.4
and section 9.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Recommendation mode
# ---------------------------------------------------------------------------

RECOMMENDATION_LABELS: dict[str, str] = {
    "AUTOMATE": "Automate",
    "AUGMENT": "Augment",
    "INVESTIGATE_FURTHER": "More information needed",
    "DO_NOT_RECOMMEND": "Not recommended",
}


def recommendation_label(value: str) -> str:
    """Return a business-facing recommendation label."""
    return RECOMMENDATION_LABELS.get(value, _human(value))


# ---------------------------------------------------------------------------
# Gate status
#
# These are direct translations of the persisted status token.  ``not_evaluated``
# means an earlier check already determined the outcome; it must never be
# rendered as an inability or a failure.
# ---------------------------------------------------------------------------

GATE_STATUS_LABELS: dict[str, str] = {
    "passed": "Passed",
    "passed_with_constraints": "Passed with conditions",
    "failed": "Not met",
    "not_evaluated": "Not needed — an earlier check already decided the outcome",
}

GATE_STATUS_ICONS: dict[str, str] = {
    "passed": "✅",
    "passed_with_constraints": "⚠️",
    "failed": "❌",
    "not_evaluated": "○",
}


def gate_status_label(value: str) -> str:
    """Return a business-facing gate status."""
    return GATE_STATUS_LABELS.get(value, _human(value))


def gate_status_icon(value: str) -> str:
    """Return a visual icon for a gate status."""
    return GATE_STATUS_ICONS.get(value, "·")


# ---------------------------------------------------------------------------
# Gate name
# ---------------------------------------------------------------------------

GATE_NAME_LABELS: dict[str, str] = {
    "evidence_sufficiency": "Evidence sufficiency",
    "technical_fit": "Technical fit",
    "business_value": "Business value",
    "risk_and_autonomy": "Risk and autonomy",
}


def gate_name_label(value: str) -> str:
    """Return a business-facing gate name."""
    return GATE_NAME_LABELS.get(value, _human(value))


# ---------------------------------------------------------------------------
# Criterion name
# ---------------------------------------------------------------------------

CRITERION_LABELS: dict[str, str] = {
    "repetition": "Task repetition",
    "predictability": "Task predictability",
    "data_readiness": "Data readiness",
    "ai_capability_fit": "AI capability fit",
    "human_judgement_requirement": "Human judgement requirement",
    "business_value": "Business value",
    "risk_consequence": "Risk consequence",
    "residual_risk_with_human_oversight": "Residual risk with human oversight",
    "implementation_complexity": "Implementation complexity",
    "conventional_solution_fit": "Conventional solution fit",
    "human_accountability_required": "Human accountability",
}


def criterion_label(value: str) -> str:
    """Return a business-facing criterion name."""
    return CRITERION_LABELS.get(value, _human(value))


# ---------------------------------------------------------------------------
# Criterion subject
#
# A noun phrase that completes "the available evidence does not establish ...".
# It is a restatement of the criterion name and nothing more: it must never
# enumerate sub-facts that the Engine does not record separately.
# ---------------------------------------------------------------------------

CRITERION_SUBJECTS: dict[str, str] = {
    "repetition": "how often this activity is repeated",
    "predictability": "how predictable this activity is",
    "data_readiness": "whether the data this activity relies on is ready for AI use",
    "ai_capability_fit": "whether an AI capability fits this activity",
    "human_judgement_requirement": "how much human judgement this activity requires",
    "business_value": "the business value of changing this activity",
    "risk_consequence": "the consequence if this activity goes wrong",
    "residual_risk_with_human_oversight": (
        "how much risk would remain if a person oversaw the activity"
    ),
    "implementation_complexity": "how complex a change to this activity would be",
    "conventional_solution_fit": (
        "whether a conventional, non-AI solution would fit this activity"
    ),
    "human_accountability_required": (
        "whether a person must remain accountable for this activity"
    ),
}


def criterion_subject(value: str) -> str:
    """Return the noun phrase describing what a criterion records."""
    return CRITERION_SUBJECTS.get(value, f"the {_human(value).lower()} of this activity")


# ---------------------------------------------------------------------------
# Knowledge state
# ---------------------------------------------------------------------------

KNOWLEDGE_STATE_LABELS: dict[str, str] = {
    "known": "Confirmed by the evidence",
    "inferred": "Assumed, not confirmed",
    "unknown": "Not established by the evidence",
}


def knowledge_state_label(value: str) -> str:
    """Return a business-facing knowledge state."""
    return KNOWLEDGE_STATE_LABELS.get(value, _human(value))


# ---------------------------------------------------------------------------
# Priority status and band
# ---------------------------------------------------------------------------

PRIORITY_STATUS_LABELS: dict[str, str] = {
    "complete": "Complete",
    "incomplete": "Incomplete",
    "not_applicable": "Not applicable",
}


def priority_status_label(value: str) -> str:
    """Return a business-facing priority status."""
    return PRIORITY_STATUS_LABELS.get(value, _human(value))


PRIORITY_BAND_LABELS: dict[str, str] = {
    "HIGH": "High",
    "MEDIUM": "Medium",
    "LOW": "Low",
}


def priority_band_label(value: str) -> str:
    """Return a business-facing priority band."""
    return PRIORITY_BAND_LABELS.get(value, _human(value))


# ---------------------------------------------------------------------------
# Package completeness
#
# ``COMPLETE`` records only that no material information gap was found.  It is
# not a readiness claim of any wider kind.
# ---------------------------------------------------------------------------

COMPLETENESS_LABELS: dict[str, str] = {
    "COMPLETE": "No material information gaps",
    "COMPLETE_WITH_INFORMATION_GAPS": "Material information gaps remain",
}


def completeness_label(value: str) -> str:
    """Return a business-facing completeness status."""
    return COMPLETENESS_LABELS.get(value, _human(value))


# ---------------------------------------------------------------------------
# Human-role confirmation status
# ---------------------------------------------------------------------------

ROLE_CONFIRMATION_LABELS: dict[str, str] = {
    "NEEDS_CONFIRMATION": "the organisational assignment still needs confirmation",
}


def role_confirmation_label(value: str) -> str:
    """Return a business-facing role-confirmation status."""
    return ROLE_CONFIRMATION_LABELS.get(value, _human(value))


# ---------------------------------------------------------------------------
# Adoption roadmap status
# ---------------------------------------------------------------------------

ROADMAP_STATUS_LABELS: dict[str, str] = {
    "QUALIFYING_OPPORTUNITY": "Qualifies for controlled validation",
    "INVESTIGATION_ONLY": "Investigation only",
    "AI_DEPLOYMENT_NOT_APPLICABLE": "No AI deployment roadmap",
}


def roadmap_status_label(value: str) -> str:
    """Return a business-facing adoption-roadmap status."""
    return ROADMAP_STATUS_LABELS.get(value, _human(value))


# ---------------------------------------------------------------------------
# GRW M2 reassessment run stages
# ---------------------------------------------------------------------------

M2_STAGE_LABELS: dict[str, str] = {
    "OPEN": "Waiting for supporting document",
    "DOCUMENT_SUBMITTED": "Document submitted — awaiting evidence review",
    "EVIDENCE_REVIEWED": "Evidence reviewed — awaiting criterion resolution",
    "RESOLUTION_PROPOSED": "Resolution recorded — ready to request reassessment",
    "REQUESTED": "Reassessment requested — awaiting approval",
    "APPROVED": "Approved — ready to proceed",
    "SUCCESSOR_REVIEW_READY": "Successor review ready — awaiting assessment",
    "ASSESSED": "Assessed — awaiting Decision Package",
    "PACKAGE_READY": "Decision Package ready — awaiting comparison",
    "COMPARED": "Comparison complete",
}


def m2_stage_label(value: str) -> str:
    """Return a business-facing M2 run stage description."""
    return M2_STAGE_LABELS.get(value, _human(value))


# ---------------------------------------------------------------------------
# General-purpose fallback
# ---------------------------------------------------------------------------


def _human(value: str) -> str:
    """Fallback title-case transform for unmapped values."""
    return value.replace("_", " ").replace("-", " ").title()


def human_label(value: str) -> str:
    """Public fallback for values not covered by a specific mapping."""
    return _human(value)
