"""Immutable provisional rules for deterministic Preliminary Assessment."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ai_adoption_engine.models.preliminary_assessment import (
    PRELIMINARY_INPUT_ORDER,
    RULE_DECIDING_CLAUSES,
    RULE_DIRECTION_BY_CODE,
    RULE_MATERIAL_MANIFESTS,
    PreliminaryDecidingRuleCode,
    PreliminaryComparisonClause,
    PreliminaryInputName,
    PreliminaryRuleSetReference,
    ProvisionalDirection,
)


class _FrozenRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PreliminaryThresholds(_FrozenRule):
    business_value_minimum: Literal[2] = 2
    data_readiness_minimum: Literal[2] = 2
    implementation_complexity_ready_maximum: Literal[4] = 4
    conventional_solution_fit_cutoff: Literal[4] = 4
    ai_capability_fit_minimum: Literal[3] = 3
    residual_risk_veto_minimum: Literal[4] = 4
    assistance_residual_risk: Literal[3] = 3
    assistance_human_judgement_minimum: Literal[3] = 3
    assistance_risk_consequence_minimum: Literal[3] = 3
    automation_data_readiness_minimum: Literal[4] = 4
    automation_complexity_maximum: Literal[3] = 3
    automation_residual_risk_maximum: Literal[2] = 2
    automation_human_judgement_maximum: Literal[2] = 2
    automation_risk_consequence_maximum: Literal[2] = 2
    automation_predictability_minimum: Literal[4] = 4
    automation_requires_no_human_accountability: Literal[True] = True


class PreliminaryMaterialManifest(_FrozenRule):
    deciding_rule_code: PreliminaryDecidingRuleCode
    required_all: tuple[PreliminaryInputName, ...]
    required_any_groups: tuple[tuple[PreliminaryInputName, ...], ...]
    allowed_material_inputs: tuple[PreliminaryInputName, ...]


class PreliminaryRuleDefinition(_FrozenRule):
    deciding_rule_code: PreliminaryDecidingRuleCode
    provisional_direction: ProvisionalDirection
    deciding_clause_codes: tuple[PreliminaryComparisonClause, ...]


class PreliminaryConfidenceRules(_FrozenRule):
    high: Literal[
        "All material inputs documented; no material inference, unknown, or conflict."
    ] = "All material inputs documented; no material inference, unknown, or conflict."
    medium: Literal[
        "Exactly one material input is an explicitly reviewed reasonable inference; no material unknown or conflict."
    ] = "Exactly one material input is an explicitly reviewed reasonable inference; no material unknown or conflict."
    low: Literal[
        "Two or more material inferences, PA-053 fallback, or any insufficient-basis rule."
    ] = "Two or more material inferences, PA-053 fallback, or any insufficient-basis rule."
    process_aggregation: Literal["Weakest activity confidence."] = (
        "Weakest activity confidence."
    )


class PreliminaryEvaluatorRules(_FrozenRule):
    rule_set_id: Literal["preliminary-evaluator-rules.v0.1"]
    rule_set_version: Literal["0.1.0"]
    rule_set_status: Literal["PROVISIONAL CONTINUITY — NOT VALIDATED"]
    threshold_basis: Literal[
        "PROVISIONAL CONTINUITY — NOT VALIDATION OR EQUIVALENCE"
    ]
    output_schema_id: Literal["preliminary-assessment.v0.1"]
    precedence: tuple[
        Literal[
            "CHANGE_CASE",
            "READINESS",
            "INTERVENTION_SELECTION",
            "AI_CAPABILITY",
            "SAFETY_AND_AUTONOMY",
        ],
        ...,
    ]
    thresholds: PreliminaryThresholds
    rules: tuple[PreliminaryRuleDefinition, ...]
    material_manifests: tuple[PreliminaryMaterialManifest, ...]
    confidence: PreliminaryConfidenceRules
    human_supplied_treatment: Literal["CONTEXT_ONLY"]
    activity_rationale_template_version: Literal["pa-rationale.v0.1"]
    unknown_request_template_version: Literal["pa-unknown-request.v0.1"]

    def canonical_json_bytes(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

    def fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_json_bytes()).hexdigest()

    def reference(self) -> PreliminaryRuleSetReference:
        return PreliminaryRuleSetReference(
            rule_set_id=self.rule_set_id,
            rule_set_version=self.rule_set_version,
            rule_set_status=self.rule_set_status,
            rule_set_fingerprint=self.fingerprint(),
        )


def _ordered(inputs: set[PreliminaryInputName]) -> tuple[PreliminaryInputName, ...]:
    return tuple(item for item in PRELIMINARY_INPUT_ORDER if item in inputs)


PRELIMINARY_EVALUATOR_RULES_V0_1 = PreliminaryEvaluatorRules(
    rule_set_id="preliminary-evaluator-rules.v0.1",
    rule_set_version="0.1.0",
    rule_set_status="PROVISIONAL CONTINUITY — NOT VALIDATED",
    threshold_basis="PROVISIONAL CONTINUITY — NOT VALIDATION OR EQUIVALENCE",
    output_schema_id="preliminary-assessment.v0.1",
    precedence=(
        "CHANGE_CASE",
        "READINESS",
        "INTERVENTION_SELECTION",
        "AI_CAPABILITY",
        "SAFETY_AND_AUTONOMY",
    ),
    thresholds=PreliminaryThresholds(),
    rules=tuple(
        PreliminaryRuleDefinition(
            deciding_rule_code=code,
            provisional_direction=RULE_DIRECTION_BY_CODE[code],
            deciding_clause_codes=tuple(
                sorted(RULE_DECIDING_CLAUSES[code], key=lambda clause: clause.value)
            ),
        )
        for code in PreliminaryDecidingRuleCode
    ),
    material_manifests=tuple(
        PreliminaryMaterialManifest(
            deciding_rule_code=code,
            required_all=_ordered(RULE_MATERIAL_MANIFESTS[code][0]),
            required_any_groups=tuple(
                _ordered(group) for group in RULE_MATERIAL_MANIFESTS[code][1]
            ),
            allowed_material_inputs=_ordered(RULE_MATERIAL_MANIFESTS[code][2]),
        )
        for code in PreliminaryDecidingRuleCode
    ),
    confidence=PreliminaryConfidenceRules(),
    human_supplied_treatment="CONTEXT_ONLY",
    activity_rationale_template_version="pa-rationale.v0.1",
    unknown_request_template_version="pa-unknown-request.v0.1",
)
