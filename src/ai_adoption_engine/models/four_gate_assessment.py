"""Strict output contracts for the persistence-free four-gate successor slice."""

import json
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_adoption_engine.models.enums import Capability, CriterionName, KnowledgeState
from ai_adoption_engine.models.evidence import EvidenceReference


class FourGateName(StrEnum):
    SHOULD_WE_CHANGE = "SHOULD_WE_CHANGE"
    IS_IT_READY = "IS_IT_READY"
    BEST_INTERVENTION = "BEST_INTERVENTION"
    SAFE_AUTONOMY = "SAFE_AUTONOMY"


class FourGateStatus(StrEnum):
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_CONSTRAINTS = "COMPLETED_WITH_CONSTRAINTS"
    BLOCKED_BY_EVIDENCE = "BLOCKED_BY_EVIDENCE"
    NOT_EVALUATED = "NOT_EVALUATED"


class GateDecisionCode(StrEnum):
    CHANGE_JUSTIFIED = "CHANGE_JUSTIFIED"
    NO_CHANGE_JUSTIFIED = "NO_CHANGE_JUSTIFIED"
    READY_FOR_INTERVENTION_SELECTION = "READY_FOR_INTERVENTION_SELECTION"
    PROCESS_IMPROVEMENT_FIRST = "PROCESS_IMPROVEMENT_FIRST"
    AI_SELECTED = "AI_SELECTED"
    CONVENTIONAL_AUTOMATION_SELECTED = "CONVENTIONAL_AUTOMATION_SELECTED"
    KEEP_HUMAN_LED_SELECTED = "KEEP_HUMAN_LED_SELECTED"
    AI_AUTOMATION_PERMITTED = "AI_AUTOMATION_PERMITTED"
    AI_ASSISTED_REQUIRED = "AI_ASSISTED_REQUIRED"
    AI_NOT_PERMITTED = "AI_NOT_PERMITTED"
    DISCOVERY_REQUIRED = "DISCOVERY_REQUIRED"
    NOT_EVALUATED = "NOT_EVALUATED"


EVALUATED_DECISION_CODES_BY_GATE: dict[
    FourGateName, frozenset[GateDecisionCode]
] = {
    FourGateName.SHOULD_WE_CHANGE: frozenset(
        {
            GateDecisionCode.CHANGE_JUSTIFIED,
            GateDecisionCode.NO_CHANGE_JUSTIFIED,
            GateDecisionCode.DISCOVERY_REQUIRED,
        }
    ),
    FourGateName.IS_IT_READY: frozenset(
        {
            GateDecisionCode.READY_FOR_INTERVENTION_SELECTION,
            GateDecisionCode.PROCESS_IMPROVEMENT_FIRST,
            GateDecisionCode.DISCOVERY_REQUIRED,
        }
    ),
    FourGateName.BEST_INTERVENTION: frozenset(
        {
            GateDecisionCode.AI_SELECTED,
            GateDecisionCode.CONVENTIONAL_AUTOMATION_SELECTED,
            GateDecisionCode.KEEP_HUMAN_LED_SELECTED,
            GateDecisionCode.DISCOVERY_REQUIRED,
        }
    ),
    FourGateName.SAFE_AUTONOMY: frozenset(
        {
            GateDecisionCode.AI_AUTOMATION_PERMITTED,
            GateDecisionCode.AI_ASSISTED_REQUIRED,
            GateDecisionCode.AI_NOT_PERMITTED,
            GateDecisionCode.DISCOVERY_REQUIRED,
        }
    ),
}


class DecisionStatus(StrEnum):
    COMPLETE = "COMPLETE"
    DISCOVERY_REQUIRED = "DISCOVERY_REQUIRED"


class ChangeDisposition(StrEnum):
    CHANGE_JUSTIFIED = "CHANGE_JUSTIFIED"
    NO_CHANGE_JUSTIFIED = "NO_CHANGE_JUSTIFIED"
    NOT_DETERMINED = "NOT_DETERMINED"


class ReadinessDisposition(StrEnum):
    READY_FOR_INTERVENTION_SELECTION = "READY_FOR_INTERVENTION_SELECTION"
    PROCESS_IMPROVEMENT_FIRST = "PROCESS_IMPROVEMENT_FIRST"
    NOT_EVALUATED = "NOT_EVALUATED"
    NOT_DETERMINED = "NOT_DETERMINED"


class SelectedInterventionFamily(StrEnum):
    AI = "AI"
    CONVENTIONAL_AUTOMATION = "CONVENTIONAL_AUTOMATION"
    KEEP_HUMAN_LED = "KEEP_HUMAN_LED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_DETERMINED = "NOT_DETERMINED"


class AutonomyCeiling(StrEnum):
    AI_AUTOMATION = "AI_AUTOMATION"
    AI_ASSISTED = "AI_ASSISTED"
    AI_NOT_PERMITTED = "AI_NOT_PERMITTED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_DETERMINED = "NOT_DETERMINED"


class OutcomeCode(StrEnum):
    NO_CHANGE_JUSTIFIED = "NO_CHANGE_JUSTIFIED"
    AI_AUTOMATION = "AI_AUTOMATION"
    AI_ASSISTED_WORK = "AI_ASSISTED_WORK"
    CONVENTIONAL_AUTOMATION = "CONVENTIONAL_AUTOMATION"
    PROCESS_IMPROVEMENT_FIRST = "PROCESS_IMPROVEMENT_FIRST"
    KEEP_HUMAN_LED = "KEEP_HUMAN_LED"
    DISCOVERY_REQUIRED = "DISCOVERY_REQUIRED"


class FourGatePriorityStatus(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class EvidenceProblemCode(StrEnum):
    UNKNOWN = "UNKNOWN"
    VALUE_MISSING = "VALUE_MISSING"
    INFERRED_CONFIDENCE_TOO_LOW = "INFERRED_CONFIDENCE_TOO_LOW"
    EVIDENCE_REFERENCE_MISSING = "EVIDENCE_REFERENCE_MISSING"
    ACTIVITY_EVIDENCE_MISSING = "ACTIVITY_EVIDENCE_MISSING"


class CapabilitySignalName(StrEnum):
    READS_UNSTRUCTURED_DOCUMENTS = "reads_unstructured_documents"
    CATEGORISES_ITEMS = "categorises_items"
    PREDICTS_FUTURE_OUTCOMES = "predicts_future_outcomes"
    DETECTS_ANOMALIES_OR_PATTERNS = "detects_anomalies_or_patterns"
    CREATES_NEW_CONTENT = "creates_new_content"
    SEARCHES_REFERENCE_KNOWLEDGE = "searches_reference_knowledge"
    RANKS_OR_SUGGESTS_OPTIONS = "ranks_or_suggests_options"
    SUPPORTS_COMPLEX_DECISIONS = "supports_complex_decisions"
    INTERPRETS_IMAGES_OR_VIDEO = "interprets_images_or_video"
    ROUTES_OR_ORCHESTRATES_WORK = "routes_or_orchestrates_work"


class BlockingEvidenceGap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_name: str = Field(min_length=1)
    gate: FourGateName
    problem_code: EvidenceProblemCode
    blocking_question: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)


class FourGateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gate: FourGateName
    status: FourGateStatus
    decision_code: GateDecisionCode
    rationale: str = Field(min_length=1)
    material_criteria: list[CriterionName] = Field(default_factory=list)
    context_criteria: list[CriterionName] = Field(default_factory=list)
    accountability_material: bool = False
    material_capability_signals: list[CapabilitySignalName] = Field(
        default_factory=list
    )
    evidence_ids: list[str] = Field(default_factory=list)
    blocking_gaps: list[BlockingEvidenceGap] = Field(default_factory=list)
    decided_by: FourGateName | None = None

    @model_validator(mode="after")
    def validate_status_contract(self) -> Self:
        if len(self.material_criteria) != len(set(self.material_criteria)):
            raise ValueError("Material criteria must be unique")
        if len(self.context_criteria) != len(set(self.context_criteria)):
            raise ValueError("Context criteria must be unique")
        if set(self.material_criteria) & set(self.context_criteria):
            raise ValueError("A criterion cannot be material and context at one gate")
        if len(self.material_capability_signals) != len(
            set(self.material_capability_signals)
        ):
            raise ValueError("Material capability signals must be unique")

        if self.status is FourGateStatus.NOT_EVALUATED:
            if self.decision_code is not GateDecisionCode.NOT_EVALUATED:
                raise ValueError("A not-evaluated gate needs the matching decision code")
            if self.decided_by is None:
                raise ValueError("A not-evaluated gate must identify the deciding gate")
            if (
                self.material_criteria
                or self.context_criteria
                or self.accountability_material
                or self.material_capability_signals
                or self.evidence_ids
                or self.blocking_gaps
            ):
                raise ValueError("A not-evaluated gate cannot claim evaluated evidence")
            return self

        if self.decision_code not in EVALUATED_DECISION_CODES_BY_GATE[self.gate]:
            raise ValueError(
                f"{self.gate.value} cannot use decision code {self.decision_code.value}"
            )
        if self.decided_by is not None:
            raise ValueError("Only a not-evaluated gate may identify an earlier gate")

        if self.status is FourGateStatus.BLOCKED_BY_EVIDENCE:
            if self.decision_code is not GateDecisionCode.DISCOVERY_REQUIRED:
                raise ValueError("An evidence-blocked gate must require discovery")
            if not self.blocking_gaps:
                raise ValueError("An evidence-blocked gate requires blocking gaps")
        else:
            if self.decision_code is GateDecisionCode.DISCOVERY_REQUIRED:
                raise ValueError("Discovery requires an evidence-blocked gate")
            if self.blocking_gaps:
                raise ValueError("Only an evidence-blocked gate may contain blocking gaps")
        return self


class FourGateCriterionAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion: CriterionName
    value: int | None = Field(default=None, ge=0, le=5)
    knowledge_state: KnowledgeState
    rationale: str = Field(min_length=1)
    evidence_ids: list[str]
    confidence: float | None = Field(default=None, ge=0, le=1)
    material_to_decision: bool
    material_to_priority: bool
    material_at_gates: list[FourGateName]
    context_at_gates: list[FourGateName]

    @model_validator(mode="after")
    def validate_materiality(self) -> Self:
        if self.material_to_decision != bool(self.material_at_gates):
            raise ValueError("Criterion decision materiality must match its gate trace")
        _validate_provenance_value(
            self.value,
            self.knowledge_state,
            self.confidence,
            label="Criterion",
        )
        return self


class FourGateAccountabilityAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: bool | None
    knowledge_state: KnowledgeState
    rationale: str = Field(min_length=1)
    evidence_ids: list[str]
    confidence: float | None = Field(default=None, ge=0, le=1)
    material_to_decision: bool
    material_at_gates: list[FourGateName]

    @model_validator(mode="after")
    def validate_materiality(self) -> Self:
        if self.material_to_decision != bool(self.material_at_gates):
            raise ValueError("Accountability materiality must match its gate trace")
        _validate_provenance_value(
            self.value,
            self.knowledge_state,
            self.confidence,
            label="Accountability",
        )
        return self


class FourGateCapabilitySignalAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal: CapabilitySignalName
    value: bool | None
    knowledge_state: KnowledgeState
    rationale: str = Field(min_length=1)
    evidence_ids: list[str]
    confidence: float | None = Field(default=None, ge=0, le=1)
    material_to_decision: bool
    material_at_gates: list[FourGateName]

    @model_validator(mode="after")
    def validate_materiality(self) -> Self:
        if self.material_to_decision != bool(self.material_at_gates):
            raise ValueError("Capability materiality must match its gate trace")
        _validate_provenance_value(
            self.value,
            self.knowledge_state,
            self.confidence,
            label="Capability signal",
        )
        return self


def _validate_provenance_value(
    value: int | bool | None,
    knowledge_state: KnowledgeState,
    confidence: float | None,
    *,
    label: str,
) -> None:
    if knowledge_state is KnowledgeState.UNKNOWN:
        if value is not None or confidence is not None:
            raise ValueError(f"{label} unknowns require null value and confidence")
        return
    if value is None:
        raise ValueError(f"{label} known or inferred states require a value")
    if knowledge_state is KnowledgeState.INFERRED and confidence is None:
        raise ValueError(f"{label} inferred states require confidence")


class FourGateScoreComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion: CriterionName
    raw_value: int
    favourable_value: int
    weight: float
    contribution: float


class FourGatePriorityScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float = Field(ge=0, le=100)
    band: Literal["HIGH", "MEDIUM", "LOW"]
    components: list[FourGateScoreComponent]


ClosedCombination = tuple[
    DecisionStatus,
    ChangeDisposition,
    ReadinessDisposition,
    SelectedInterventionFamily,
    AutonomyCeiling,
]


CLOSED_OUTCOME_COMBINATIONS: dict[ClosedCombination, OutcomeCode] = {
    (
        DecisionStatus.DISCOVERY_REQUIRED,
        ChangeDisposition.NOT_DETERMINED,
        ReadinessDisposition.NOT_EVALUATED,
        SelectedInterventionFamily.NOT_DETERMINED,
        AutonomyCeiling.NOT_DETERMINED,
    ): OutcomeCode.DISCOVERY_REQUIRED,
    (
        DecisionStatus.COMPLETE,
        ChangeDisposition.NO_CHANGE_JUSTIFIED,
        ReadinessDisposition.NOT_EVALUATED,
        SelectedInterventionFamily.NOT_APPLICABLE,
        AutonomyCeiling.NOT_APPLICABLE,
    ): OutcomeCode.NO_CHANGE_JUSTIFIED,
    (
        DecisionStatus.DISCOVERY_REQUIRED,
        ChangeDisposition.CHANGE_JUSTIFIED,
        ReadinessDisposition.NOT_DETERMINED,
        SelectedInterventionFamily.NOT_DETERMINED,
        AutonomyCeiling.NOT_DETERMINED,
    ): OutcomeCode.DISCOVERY_REQUIRED,
    (
        DecisionStatus.COMPLETE,
        ChangeDisposition.CHANGE_JUSTIFIED,
        ReadinessDisposition.PROCESS_IMPROVEMENT_FIRST,
        SelectedInterventionFamily.NOT_APPLICABLE,
        AutonomyCeiling.NOT_APPLICABLE,
    ): OutcomeCode.PROCESS_IMPROVEMENT_FIRST,
    (
        DecisionStatus.DISCOVERY_REQUIRED,
        ChangeDisposition.CHANGE_JUSTIFIED,
        ReadinessDisposition.READY_FOR_INTERVENTION_SELECTION,
        SelectedInterventionFamily.NOT_DETERMINED,
        AutonomyCeiling.NOT_DETERMINED,
    ): OutcomeCode.DISCOVERY_REQUIRED,
    (
        DecisionStatus.COMPLETE,
        ChangeDisposition.CHANGE_JUSTIFIED,
        ReadinessDisposition.READY_FOR_INTERVENTION_SELECTION,
        SelectedInterventionFamily.CONVENTIONAL_AUTOMATION,
        AutonomyCeiling.NOT_APPLICABLE,
    ): OutcomeCode.CONVENTIONAL_AUTOMATION,
    (
        DecisionStatus.COMPLETE,
        ChangeDisposition.CHANGE_JUSTIFIED,
        ReadinessDisposition.READY_FOR_INTERVENTION_SELECTION,
        SelectedInterventionFamily.KEEP_HUMAN_LED,
        AutonomyCeiling.NOT_APPLICABLE,
    ): OutcomeCode.KEEP_HUMAN_LED,
    (
        DecisionStatus.DISCOVERY_REQUIRED,
        ChangeDisposition.CHANGE_JUSTIFIED,
        ReadinessDisposition.READY_FOR_INTERVENTION_SELECTION,
        SelectedInterventionFamily.AI,
        AutonomyCeiling.NOT_DETERMINED,
    ): OutcomeCode.DISCOVERY_REQUIRED,
    (
        DecisionStatus.COMPLETE,
        ChangeDisposition.CHANGE_JUSTIFIED,
        ReadinessDisposition.READY_FOR_INTERVENTION_SELECTION,
        SelectedInterventionFamily.AI,
        AutonomyCeiling.AI_NOT_PERMITTED,
    ): OutcomeCode.KEEP_HUMAN_LED,
    (
        DecisionStatus.COMPLETE,
        ChangeDisposition.CHANGE_JUSTIFIED,
        ReadinessDisposition.READY_FOR_INTERVENTION_SELECTION,
        SelectedInterventionFamily.AI,
        AutonomyCeiling.AI_ASSISTED,
    ): OutcomeCode.AI_ASSISTED_WORK,
    (
        DecisionStatus.COMPLETE,
        ChangeDisposition.CHANGE_JUSTIFIED,
        ReadinessDisposition.READY_FOR_INTERVENTION_SELECTION,
        SelectedInterventionFamily.AI,
        AutonomyCeiling.AI_AUTOMATION,
    ): OutcomeCode.AI_AUTOMATION,
}


def derive_outcome(
    decision_status: DecisionStatus,
    change_disposition: ChangeDisposition,
    readiness_disposition: ReadinessDisposition,
    selected_intervention_family: SelectedInterventionFamily,
    autonomy_ceiling: AutonomyCeiling,
) -> OutcomeCode:
    combination = (
        decision_status,
        change_disposition,
        readiness_disposition,
        selected_intervention_family,
        autonomy_ceiling,
    )
    try:
        return CLOSED_OUTCOME_COMBINATIONS[combination]
    except KeyError as exc:
        raise ValueError("Invalid four-gate output-field combination") from exc


class FourGateStepAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(min_length=1)
    activity: str = Field(min_length=1)
    decision_status: DecisionStatus
    change_disposition: ChangeDisposition
    readiness_disposition: ReadinessDisposition
    selected_intervention_family: SelectedInterventionFamily
    autonomy_ceiling: AutonomyCeiling
    outcome_code: OutcomeCode | None = Field(
        default=None,
        frozen=True,
        json_schema_extra={"readOnly": True},
    )
    gate_results: list[FourGateResult] = Field(min_length=4, max_length=4)
    blocking_gaps: list[BlockingEvidenceGap] = Field(default_factory=list)
    capabilities: list[Capability] = Field(default_factory=list)
    capability_signals: list[FourGateCapabilitySignalAssessment]
    criteria: list[FourGateCriterionAssessment]
    human_accountability: FourGateAccountabilityAssessment
    priority_status: FourGatePriorityStatus
    priority: FourGatePriorityScore | None = None
    priority_missing_criteria: list[CriterionName] = Field(default_factory=list)
    reasoning: list[str]
    evidence: list[EvidenceReference]

    @model_validator(mode="after")
    def validate_closed_contract(self) -> Self:
        derived = derive_outcome(
            self.decision_status,
            self.change_disposition,
            self.readiness_disposition,
            self.selected_intervention_family,
            self.autonomy_ceiling,
        )
        if self.outcome_code is not None and self.outcome_code is not derived:
            raise ValueError("outcome_code must equal the derived four-gate outcome")
        object.__setattr__(self, "outcome_code", derived)

        expected_gates = list(FourGateName)
        if [item.gate for item in self.gate_results] != expected_gates:
            raise ValueError("Exactly four gate results must appear in canonical order")

        blocked_indexes = [
            index
            for index, item in enumerate(self.gate_results)
            if item.status is FourGateStatus.BLOCKED_BY_EVIDENCE
        ]
        if self.decision_status is DecisionStatus.DISCOVERY_REQUIRED:
            if len(blocked_indexes) != 1:
                raise ValueError("Discovery requires exactly one evidence-blocked gate")
            stop_index = blocked_indexes[0]
        else:
            if blocked_indexes:
                raise ValueError("A complete decision cannot contain a blocked gate")
            stop_index = self._substantive_stop_index()

        if stop_index != self._field_stop_index():
            raise ValueError("The deciding gate does not match the typed output path")

        for index, gate_result in enumerate(self.gate_results):
            if index < stop_index and gate_result.status not in {
                FourGateStatus.COMPLETED,
                FourGateStatus.COMPLETED_WITH_CONSTRAINTS,
            }:
                raise ValueError("Gates before the deciding gate must be completed")
            if index > stop_index and gate_result.status is not FourGateStatus.NOT_EVALUATED:
                raise ValueError("Gates after the deciding gate must be not evaluated")
            if index > stop_index and gate_result.decided_by is not self.gate_results[
                stop_index
            ].gate:
                raise ValueError("A later gate must identify the actual deciding gate")
        if self.decision_status is DecisionStatus.COMPLETE and self.gate_results[
            stop_index
        ].status not in {
            FourGateStatus.COMPLETED,
            FourGateStatus.COMPLETED_WITH_CONSTRAINTS,
        }:
            raise ValueError("The substantive deciding gate must be completed")

        expected_codes = self._expected_evaluated_decision_codes(stop_index)
        actual_codes = [
            gate_result.decision_code
            for gate_result in self.gate_results[: stop_index + 1]
        ]
        if actual_codes != expected_codes:
            raise ValueError(
                "Evaluated gate decision codes do not agree with the typed output path"
            )

        gate_gaps = [
            gap for result in self.gate_results for gap in result.blocking_gaps
        ]
        if self.blocking_gaps != gate_gaps:
            raise ValueError("Activity blocking gaps must match the blocked gate")
        if bool(self.blocking_gaps) != (
            self.decision_status is DecisionStatus.DISCOVERY_REQUIRED
        ):
            raise ValueError("Blocking gaps must exist exactly for discovery outcomes")

        if [item.criterion for item in self.criteria] != list(CriterionName):
            raise ValueError("Criteria must contain every criterion in canonical order")
        if [item.signal for item in self.capability_signals] != list(
            CapabilitySignalName
        ):
            raise ValueError(
                "Capability signals must contain every signal in canonical order"
            )
        if len(self.capabilities) != len(set(self.capabilities)):
            raise ValueError("Mapped capabilities must be unique")

        eligible = derived in {
            OutcomeCode.AI_AUTOMATION,
            OutcomeCode.AI_ASSISTED_WORK,
        }
        if not eligible:
            if (
                self.priority_status is not FourGatePriorityStatus.NOT_APPLICABLE
                or self.priority is not None
                or self.priority_missing_criteria
            ):
                raise ValueError("Non-AI outcomes cannot receive a priority score")
        elif self.priority_status is FourGatePriorityStatus.COMPLETE:
            if self.priority is None or self.priority_missing_criteria:
                raise ValueError("Complete priority requires a score and no missing inputs")
        elif self.priority_status is FourGatePriorityStatus.INCOMPLETE:
            if self.priority is not None or not self.priority_missing_criteria:
                raise ValueError("Incomplete priority requires missing inputs and no score")
        else:
            raise ValueError("Eligible AI outcomes require complete or incomplete priority")
        return self

    def _substantive_stop_index(self) -> int:
        if self.change_disposition is ChangeDisposition.NO_CHANGE_JUSTIFIED:
            return 0
        if (
            self.readiness_disposition
            is ReadinessDisposition.PROCESS_IMPROVEMENT_FIRST
        ):
            return 1
        if self.selected_intervention_family in {
            SelectedInterventionFamily.CONVENTIONAL_AUTOMATION,
            SelectedInterventionFamily.KEEP_HUMAN_LED,
        }:
            return 2
        return 3

    def _field_stop_index(self) -> int:
        if self.change_disposition in {
            ChangeDisposition.NOT_DETERMINED,
            ChangeDisposition.NO_CHANGE_JUSTIFIED,
        }:
            return 0
        if self.readiness_disposition in {
            ReadinessDisposition.NOT_DETERMINED,
            ReadinessDisposition.PROCESS_IMPROVEMENT_FIRST,
        }:
            return 1
        if self.selected_intervention_family in {
            SelectedInterventionFamily.NOT_DETERMINED,
            SelectedInterventionFamily.CONVENTIONAL_AUTOMATION,
            SelectedInterventionFamily.KEEP_HUMAN_LED,
        }:
            return 2
        return 3

    def _expected_evaluated_decision_codes(
        self,
        stop_index: int,
    ) -> list[GateDecisionCode]:
        preceding_codes = [
            GateDecisionCode.CHANGE_JUSTIFIED,
            GateDecisionCode.READY_FOR_INTERVENTION_SELECTION,
            GateDecisionCode.AI_SELECTED,
        ]
        if self.decision_status is DecisionStatus.DISCOVERY_REQUIRED:
            deciding_code = GateDecisionCode.DISCOVERY_REQUIRED
        elif stop_index == 0:
            deciding_code = GateDecisionCode.NO_CHANGE_JUSTIFIED
        elif stop_index == 1:
            deciding_code = GateDecisionCode.PROCESS_IMPROVEMENT_FIRST
        elif stop_index == 2:
            deciding_code = (
                GateDecisionCode.CONVENTIONAL_AUTOMATION_SELECTED
                if self.selected_intervention_family
                is SelectedInterventionFamily.CONVENTIONAL_AUTOMATION
                else GateDecisionCode.KEEP_HUMAN_LED_SELECTED
            )
        elif self.autonomy_ceiling is AutonomyCeiling.AI_AUTOMATION:
            deciding_code = GateDecisionCode.AI_AUTOMATION_PERMITTED
        elif self.autonomy_ceiling is AutonomyCeiling.AI_ASSISTED:
            deciding_code = GateDecisionCode.AI_ASSISTED_REQUIRED
        else:
            deciding_code = GateDecisionCode.AI_NOT_PERMITTED
        return [*preceding_codes[:stop_index], deciding_code]


class FourGateProcessAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    process_id: str = Field(min_length=1)
    process_name: str = Field(min_length=1)
    framework_id: Literal["four-gate-framework.v0.1"]
    framework_version: Literal["0.1"]
    decision_contract_version: Literal["phase1-v0.4"]
    policy_id: Literal["decision_policy.v0.3"]
    policy_version: Literal["0.3.0"]
    policy_status: str = Field(min_length=1)
    step_assessments: list[FourGateStepAssessment]

    def canonical_json_bytes(self) -> bytes:
        """Return deterministic semantic JSON for fingerprints and repeatability checks."""

        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
