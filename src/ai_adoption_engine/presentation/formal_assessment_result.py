"""Read-only, version-aware presentation of one completed formal result.

No adapter, engine, persistence service, or user-interface framework is
imported here.  This is deliberately an explicit, default-off projection.
"""

from __future__ import annotations

from pydantic import ValidationError

from ai_adoption_engine.formal.guidance import _has_v0_1_identity
from ai_adoption_engine.models.enums import KnowledgeState
from ai_adoption_engine.models.formal_assessment import (
    FORMAL_GUIDANCE_CATALOGUE_FINGERPRINT,
    FORMAL_GUIDANCE_CATALOGUE_ID,
    FormalAssessmentInputMode,
    FormalAssessmentResult,
    FormalAssessmentResultSupersession,
    FormalEvidenceGuidance,
    ProjectedValueOrigin,
    SupportingEvidenceDisposition,
)
from ai_adoption_engine.models.formal_assessment_presentation import (
    FormalAssessmentCustomerPresentation,
    FormalAssessmentPresentationAudit,
    FormalAssessmentResultPresentation,
    FormalPresentationActivity,
    FormalPresentationGap,
    FormalPresentationGate,
    FormalPresentationGuidance,
    FormalPresentationPriority,
    FormalPresentationProvenance,
)
from ai_adoption_engine.presentation.labels import (
    criterion_label,
    four_gate_name_label,
    four_gate_outcome_label,
    four_gate_status_label,
    priority_band_label,
    priority_status_label,
)


class FormalAssessmentPresentationError(ValueError):
    """Base typed failure for an unsafe formal presentation input."""


class UnsupportedFormalAssessmentPresentationIdentity(FormalAssessmentPresentationError):
    """The source uses an identity for which there is no explicit handler."""


class CorruptFormalAssessmentPresentationRecord(FormalAssessmentPresentationError):
    """The result, guidance, or trace could not be validated as frozen."""


class InvalidFormalAssessmentPresentationGuidance(
    FormalAssessmentPresentationError
):
    """Guidance was unrelated, stale, reordered, or otherwise not exact."""


_INPUT_MODE_LABELS = {
    FormalAssessmentInputMode.APPROVED_PROCESS_ONLY: "Approved process only",
    FormalAssessmentInputMode.APPROVED_PROCESS_WITH_SUPPORTING_EVIDENCE: (
        "Approved process with supporting evidence"
    ),
}
_DISPOSITION_LABELS = {
    SupportingEvidenceDisposition.NO_SUPPORTING_HISTORY: "No supporting evidence history was used",
    SupportingEvidenceDisposition.CURRENT_SUPPORTING_EVIDENCE_INCLUDED: (
        "Current supporting evidence was included"
    ),
    SupportingEvidenceDisposition.CURRENT_SUPPORTING_EVIDENCE_EXPLICITLY_EXCLUDED: (
        "Current supporting evidence was explicitly excluded"
    ),
}
_ORIGIN_LABELS = {
    ProjectedValueOrigin.SOURCE_ONLY: "Approved-process source only",
    ProjectedValueOrigin.CORROBORATED: (
        "Approved-process source corroborated by reviewed supporting evidence"
    ),
    ProjectedValueOrigin.FILLED_UNKNOWN: (
        "Approved unknown filled from reviewed supporting evidence"
    ),
    ProjectedValueOrigin.EXPLICITLY_RESOLVED: (
        "Human-resolved conflict; original alternatives remain in audit history"
    ),
}
def _human(value: object) -> str:
    return str(getattr(value, "value", value)).replace("_", " ").capitalize()


def _decision_label(value: object) -> str:
    raw = str(getattr(value, "value", value))
    labels = {
        "CHANGE_JUSTIFIED": "Change justified",
        "NO_CHANGE_JUSTIFIED": "No change justified",
        "READY_FOR_INTERVENTION_SELECTION": "Ready for intervention selection",
        "PROCESS_IMPROVEMENT_FIRST": "Process improvement first",
        "AI_SELECTED": "AI selected",
        "CONVENTIONAL_AUTOMATION_SELECTED": "Conventional automation selected",
        "KEEP_HUMAN_LED_SELECTED": "Keep human-led selected",
        "AI_AUTOMATION_PERMITTED": "AI automation permitted",
        "AI_ASSISTED_REQUIRED": "AI-assisted work required",
        "AI_NOT_PERMITTED": "AI not permitted by the Gate 4 safety boundary",
        "DISCOVERY_REQUIRED": "Discovery required",
        "NOT_EVALUATED": "Not evaluated — an earlier gate determined the path",
    }
    return labels.get(raw, _human(raw))


def _validated_result(source: object) -> FormalAssessmentResult:
    if not isinstance(source, FormalAssessmentResult):
        raise CorruptFormalAssessmentPresentationRecord(
            "Presentation requires a completed FormalAssessmentResult."
        )
    try:
        if not _has_v0_1_identity(source):
            raise UnsupportedFormalAssessmentPresentationIdentity(
                "Unsupported or mixed Formal Assessment presentation compatibility identity."
            )
    except UnsupportedFormalAssessmentPresentationIdentity:
        raise
    except (AttributeError, TypeError) as exc:
        raise CorruptFormalAssessmentPresentationRecord(
            "The supplied Formal Assessment result has an invalid frozen structure."
        ) from exc
    try:
        result = FormalAssessmentResult.model_validate(source.model_dump(mode="python"))
    except (ValidationError, ValueError, TypeError) as exc:
        raise CorruptFormalAssessmentPresentationRecord(
            "The supplied Formal Assessment result failed frozen integrity validation."
        ) from exc
    if not _has_v0_1_identity(result):
        raise UnsupportedFormalAssessmentPresentationIdentity(
            "Unsupported or mixed Formal Assessment presentation compatibility identity."
        )
    return result


def _validated_guidance(
    guidance: object | None,
    *,
    result: FormalAssessmentResult,
) -> FormalEvidenceGuidance | None:
    if guidance is None:
        return None
    if not isinstance(guidance, FormalEvidenceGuidance):
        raise InvalidFormalAssessmentPresentationGuidance(
            "Presentation guidance must be a frozen FormalEvidenceGuidance record."
        )
    try:
        validated = FormalEvidenceGuidance.model_validate(guidance.model_dump(mode="python"))
    except (ValidationError, ValueError, TypeError) as exc:
        raise InvalidFormalAssessmentPresentationGuidance(
            "The supplied evidence guidance failed frozen integrity validation."
        ) from exc
    if (
        validated.source_result != result
        or validated.catalogue_id != FORMAL_GUIDANCE_CATALOGUE_ID
        or validated.catalogue_fingerprint != FORMAL_GUIDANCE_CATALOGUE_FINGERPRINT
    ):
        raise InvalidFormalAssessmentPresentationGuidance(
            "Guidance must reference the exact result and frozen catalogue identity."
        )
    return validated


def _validated_supersession(
    supersession: object | None,
    *,
    result: FormalAssessmentResult,
) -> FormalAssessmentResultSupersession | None:
    if supersession is None:
        return None
    if not isinstance(supersession, FormalAssessmentResultSupersession):
        raise CorruptFormalAssessmentPresentationRecord(
            "Audit supersession must be a frozen FormalAssessmentResultSupersession."
        )
    try:
        validated = FormalAssessmentResultSupersession.model_validate(
            supersession.model_dump(mode="python")
        )
    except (ValidationError, ValueError, TypeError) as exc:
        raise CorruptFormalAssessmentPresentationRecord(
            "The supplied supersession failed frozen integrity validation."
        ) from exc
    lifecycle_id = result.manifest.authorization.approved_process.lineage.formal_lifecycle_id
    if (
        validated.formal_lifecycle_id != lifecycle_id
        or result.result_id
        not in {validated.superseded_result_id, validated.successor_result_id}
    ):
        raise CorruptFormalAssessmentPresentationRecord(
            "Audit supersession must identify this result in its exact lifecycle."
        )
    return validated


def _guidance_by_gap(
    guidance: FormalEvidenceGuidance | None,
) -> dict[tuple[str, int], FormalPresentationGuidance]:
    if guidance is None:
        return {}
    by_gap: dict[tuple[str, int], FormalPresentationGuidance] = {}
    index = 0
    for activity in guidance.source_result.assessment.step_assessments:
        for _ in activity.blocking_gaps:
            item = guidance.items[index]
            by_gap[(activity.step_id, index)] = FormalPresentationGuidance(
                requested_information=item.requested_information,
                boundary_notice=item.boundary_notice,
            )
            index += 1
    return by_gap


def _provenance(activity) -> tuple[FormalPresentationProvenance, ...]:
    def field_name(trace) -> str:
        target = trace.target
        if target.kind.value == "criterion":
            return criterion_label(target.criterion.value)
        if target.kind.value == "human_accountability_required":
            return "Human accountability"
        return _human(target.capability_signal)

    def evidence_status(trace) -> tuple[str, str]:
        if trace.projected_knowledge_state is KnowledgeState.UNKNOWN:
            return "Remaining unknown", "No scalar evidence reference is recorded"
        if trace.origin is ProjectedValueOrigin.EXPLICITLY_RESOLVED:
            return (
                "Human-resolved value",
                "The original conflict and alternatives remain in the audit history",
            )
        if trace.origin is ProjectedValueOrigin.SOURCE_ONLY:
            return (
                "Approved-process value",
                "Recorded approved-process evidence supports this value",
            )
        if trace.projected_knowledge_state is KnowledgeState.INFERRED:
            return "Reviewed inference", "Reviewed supporting evidence supports this inference"
        return "Documented fact", "Reviewed supporting evidence supports this documented fact"

    return tuple(
        FormalPresentationProvenance(
            field_name=field_name(trace),
            projection_origin=_ORIGIN_LABELS[trace.origin],
            knowledge_state=evidence_status(trace)[0],
            evidence_status=evidence_status(trace)[1],
        )
        for trace in activity.field_resolutions
    )


def _activities(
    result: FormalAssessmentResult,
    guidance: FormalEvidenceGuidance | None,
) -> tuple[FormalPresentationActivity, ...]:
    guidance_map = _guidance_by_gap(guidance)
    projected = result.manifest.projection.activities
    activities: list[FormalPresentationActivity] = []
    gap_index = 0
    for assessed, projection in zip(
        result.assessment.step_assessments, projected, strict=True
    ):
        gates: list[FormalPresentationGate] = []
        for gate in assessed.gate_results:
            gaps: list[FormalPresentationGap] = []
            for gap in gate.blocking_gaps:
                gaps.append(
                    FormalPresentationGap(
                        field_name=criterion_label(gap.field_name),
                        question=gap.blocking_question,
                        guidance=guidance_map.get((assessed.step_id, gap_index)),
                    )
                )
                gap_index += 1
            gates.append(
                FormalPresentationGate(
                    name=four_gate_name_label(gate.gate.value),
                    status=four_gate_status_label(gate.status.value),
                    decision=_decision_label(gate.decision_code),
                    rationale=gate.rationale,
                    blocking_gaps=tuple(gaps),
                    capabilities=tuple(_human(item) for item in gate.material_capability_signals),
                )
            )
        priority = FormalPresentationPriority(
            status=priority_status_label(assessed.priority_status.value),
            score=assessed.priority.score if assessed.priority else None,
            band=priority_band_label(assessed.priority.band) if assessed.priority else None,
        )
        activities.append(
            FormalPresentationActivity(
                name=assessed.activity,
                outcome=four_gate_outcome_label(assessed.outcome_code.value),
                decision_status=_human(assessed.decision_status),
                change_disposition=_human(assessed.change_disposition),
                readiness_disposition=_human(assessed.readiness_disposition),
                selected_intervention_family=_human(
                    assessed.selected_intervention_family
                ),
                autonomy_ceiling=_human(assessed.autonomy_ceiling),
                priority=priority,
                gates=tuple(gates),
                capabilities=tuple(_human(item) for item in assessed.capabilities),
                provenance=_provenance(projection),
                activity_evidence=(
                    "Activity-level evidence is retained separately from scalar values."
                    if projection.activity_evidence
                    else None
                ),
            )
        )
    if guidance is not None and gap_index != len(guidance.items):
        raise InvalidFormalAssessmentPresentationGuidance(
            "Guidance items did not attach to the exact ordered result gaps."
        )
    return tuple(activities)


def present_formal_assessment_result(
    result: object,
    *,
    guidance: object | None = None,
    supersession: object | None = None,
    include_audit: bool = False,
) -> FormalAssessmentResultPresentation:
    """Project exactly one supported result identity into frozen customer text."""

    validated_result = _validated_result(result)
    validated_guidance = _validated_guidance(guidance, result=validated_result)
    validated_supersession = _validated_supersession(
        supersession, result=validated_result
    )
    choice = validated_result.manifest.authorization.input_choice
    try:
        presentation = FormalAssessmentResultPresentation(
            customer=FormalAssessmentCustomerPresentation(
                process_name=validated_result.assessment.process_name,
                input_mode=_INPUT_MODE_LABELS[choice.mode],
                supporting_evidence_disposition=_DISPOSITION_LABELS[
                    choice.supporting_evidence_disposition
                ],
                activities=_activities(validated_result, validated_guidance),
            ),
            audit=(
                FormalAssessmentPresentationAudit(
                    source_result=validated_result,
                    guidance=validated_guidance,
                    supersession=validated_supersession,
                )
                if include_audit
                else None
            ),
        )
    except FormalAssessmentPresentationError:
        raise
    except (KeyError, ValidationError, ValueError, TypeError) as exc:
        raise CorruptFormalAssessmentPresentationRecord(
            "The Formal Assessment result could not produce a complete frozen presentation."
        ) from exc
    return presentation
