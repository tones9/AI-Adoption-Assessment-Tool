"""Canonical fingerprinted Preliminary Assessment v0.2 rule artifact."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ai_adoption_engine.models.preliminary_assessment_v0_2 import (
    CONTRACT_STATUS,
    OUTPUT_SCHEMA_ID,
    RULE_SET_ID,
    RULE_SET_VERSION,
    ComponentAction,
    WorkNeedType,
)


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LiteralFamily(_Frozen):
    pd2_rule_code: str
    matched_literal_code: str
    surface_forms: tuple[str, ...]
    component_action: ComponentAction | None


class RuleSetReferenceV2(_Frozen):
    rule_set_id: Literal["preliminary-evaluator-rules.v0.2"]
    rule_set_version: Literal["0.2.0"]
    rule_set_status: Literal["PROVISIONAL EXPLORATION — NOT VALIDATED"]
    rule_set_fingerprint: str


class PreliminaryEvaluatorRulesV2(_Frozen):
    rule_set_id: Literal["preliminary-evaluator-rules.v0.2"]
    rule_set_version: Literal["0.2.0"]
    rule_set_status: Literal["PROVISIONAL EXPLORATION — NOT VALIDATED"]
    evaluator_id: Literal["preliminary-evaluator.v0.2"]
    evaluator_version: Literal["0.2.0"]
    output_schema_id: Literal["preliminary-assessment.v0.2"]
    normalization: tuple[str, ...]
    hard_boundaries: tuple[str, ...]
    protected_abbreviations: tuple[str, ...]
    conjunctions: tuple[str, ...]
    guards: tuple[str, ...]
    literal_manifest: tuple[LiteralFamily, ...]
    work_need_mapping: tuple[tuple[str, str, str], ...]
    precedence: tuple[str, ...]
    conventional_sufficiency: tuple[str, ...]
    pd2_to_pa2_mapping: tuple[tuple[str, tuple[str, ...], str], ...]
    governance_rules: tuple[str, ...]
    affirmative_no_change_bundle: tuple[str, ...]
    work_need_construction: tuple[str, ...]
    opportunity_grouping: tuple[str, ...]
    evidence_coverage_rules: tuple[str, ...]
    mechanical_errata: tuple[str, ...]
    opportunity_limit: int
    identifier_schemas: tuple[str, ...]

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

    def reference(self) -> RuleSetReferenceV2:
        return RuleSetReferenceV2(
            rule_set_id=self.rule_set_id,
            rule_set_version=self.rule_set_version,
            rule_set_status=self.rule_set_status,
            rule_set_fingerprint=self.fingerprint(),
        )


def _forms(base: str, *rest: str) -> tuple[str, ...]:
    return (base, *rest)


_FAMILY_SPECS: tuple[
    tuple[str, str, tuple[str, ...], ComponentAction | None], ...
] = (
    ("001", "001", _forms("record", "records", "recorded", "recording"), ComponentAction.RECORD),
    ("001", "002", _forms("log", "logs", "logged", "logging"), ComponentAction.RECORD),
    ("001", "003", _forms("register", "registers", "registered", "registering"), ComponentAction.RECORD),
    ("001", "004", _forms("capture", "captures", "captured", "capturing"), ComponentAction.RECORD),
    ("001", "005", _forms("enter", "enters", "entered", "entering"), ComponentAction.RECORD),
    ("002", "001", _forms("update", "updates", "updated", "updating"), ComponentAction.UPDATE),
    ("002", "002", _forms("amend", "amends", "amended", "amending"), ComponentAction.UPDATE),
    ("002", "003", _forms("correct", "corrects", "corrected", "correcting"), ComponentAction.UPDATE),
    ("002", "004", _forms("maintain", "maintains", "maintained", "maintaining"), ComponentAction.UPDATE),
    ("003", "001", _forms("notify", "notifies", "notified", "notifying"), ComponentAction.NOTIFY),
    ("003", "002", _forms("inform", "informs", "informed", "informing"), ComponentAction.NOTIFY),
    ("003", "003", _forms("alert", "alerts", "alerted", "alerting"), ComponentAction.NOTIFY),
    ("003", "004", _forms("advise", "advises", "advised", "advising"), ComponentAction.NOTIFY),
    ("004", "001", _forms("assign", "assigns", "assigned", "assigning"), ComponentAction.ASSIGN),
    ("004", "002", _forms("route", "routes", "routed", "routing"), ComponentAction.ROUTE),
    ("004", "003", _forms("forward", "forwards", "forwarded", "forwarding"), ComponentAction.ROUTE),
    ("004", "004", _forms("dispatch", "dispatches", "dispatched", "dispatching"), ComponentAction.ROUTE),
    ("004", "005", _forms("transfer", "transfers", "transferred", "transferring"), ComponentAction.ROUTE),
    ("005", "001", _forms("schedule", "schedules", "scheduled", "scheduling"), ComponentAction.SCHEDULE),
    ("005", "002", _forms("book", "books", "booked", "booking"), ComponentAction.SCHEDULE),
    ("005", "003", _forms("set a date", "sets a date"), ComponentAction.SCHEDULE),
    ("005", "004", _forms("set the date", "sets the date"), ComponentAction.SCHEDULE),
    ("005", "005", _forms("set a time", "sets a time"), ComponentAction.SCHEDULE),
    ("005", "006", _forms("set the time", "sets the time"), ComponentAction.SCHEDULE),
    ("006", "001", _forms("monitor", "monitors", "monitored", "monitoring"), ComponentAction.MONITOR),
    ("006", "002", _forms("track", "tracks", "tracked", "tracking"), ComponentAction.MONITOR),
    ("006", "003", _forms("check progress", "checks progress", "checked progress", "checking progress"), ComponentAction.MONITOR),
    ("006", "004", _forms("follow up", "follows up", "followed up", "following up"), ComponentAction.FOLLOW_UP),
    ("007", "001", _forms("copy", "copies", "copied", "copying"), ComponentAction.TRANSFORM),
    ("007", "002", _forms("calculate", "calculates", "calculated", "calculating"), ComponentAction.TRANSFORM),
    ("007", "003", _forms("convert", "converts", "converted", "converting"), ComponentAction.TRANSFORM),
    ("007", "004", _forms("map", "maps", "mapped", "mapping"), ComponentAction.TRANSFORM),
    ("007", "005", _forms("validate against", "validates against", "validated against", "validating against"), ComponentAction.TRANSFORM),
    ("007", "006", _forms("populate", "populates", "populated", "populating"), ComponentAction.TRANSFORM),
    ("008", "001", _forms("read", "reads", "reading"), ComponentAction.INTERPRET),
    ("008", "002", _forms("interpret", "interprets", "interpreted", "interpreting"), ComponentAction.INTERPRET),
    ("008", "003", _forms("understand", "understands", "understood", "understanding"), ComponentAction.INTERPRET),
    ("008", "004", _forms("analyse", "analyses", "analysed", "analysing"), ComponentAction.INTERPRET),
    ("008", "005", _forms("analyze", "analyzes", "analyzed", "analyzing"), ComponentAction.INTERPRET),
    ("008", "006", _forms("examine", "examines", "examined", "examining"), ComponentAction.INTERPRET),
    ("008", "007", _forms("review", "reviews", "reviewed", "reviewing"), ComponentAction.INTERPRET),
    ("009", "001", _forms("investigate", "investigates", "investigated", "investigating"), ComponentAction.INVESTIGATE),
    ("009", "002", _forms("inquire", "inquires", "inquired", "inquiring"), ComponentAction.INVESTIGATE),
    ("009", "003", _forms("enquire", "enquires", "enquired", "enquiring"), ComponentAction.INVESTIGATE),
    ("009", "004", _forms("establish whether", "establishes whether", "established whether", "establishing whether"), ComponentAction.INVESTIGATE),
    ("010", "001", _forms("categorize", "categorizes", "categorized", "categorizing"), ComponentAction.CATEGORISE),
    ("010", "002", _forms("categorise", "categorises", "categorised", "categorising"), ComponentAction.CATEGORISE),
    ("010", "003", _forms("classify", "classifies", "classified", "classifying"), ComponentAction.CATEGORISE),
    ("010", "004", _forms("determine category", "determines category", "determined category", "determining category"), ComponentAction.CATEGORISE),
    ("010", "005", _forms("determine the category", "determines the category", "determined the category", "determining the category"), ComponentAction.CATEGORISE),
    ("010", "006", _forms("determine stage", "determines stage", "determined stage", "determining stage"), ComponentAction.CATEGORISE),
    ("010", "007", _forms("determine the stage", "determines the stage", "determined the stage", "determining the stage"), ComponentAction.CATEGORISE),
    ("010", "008", _forms("determine type", "determines type", "determined type", "determining type"), ComponentAction.CATEGORISE),
    ("010", "009", _forms("determine the type", "determines the type", "determined the type", "determining the type"), ComponentAction.CATEGORISE),
    ("010", "010", _forms("determine priority", "determines priority", "determined priority", "determining priority"), ComponentAction.CATEGORISE),
    ("010", "011", _forms("determine the priority", "determines the priority", "determined the priority", "determining the priority"), ComponentAction.CATEGORISE),
    ("011", "001", _forms("search", "searches", "searched", "searching"), ComponentAction.RETRIEVE),
    ("011", "002", _forms("look up", "looks up", "looked up", "looking up"), ComponentAction.RETRIEVE),
    ("011", "003", _forms("retrieve", "retrieves", "retrieved", "retrieving"), ComponentAction.RETRIEVE),
    ("011", "004", _forms("consult", "consults", "consulted", "consulting"), ComponentAction.RETRIEVE),
    ("011", "005", _forms("check against", "checks against", "checked against", "checking against"), ComponentAction.RETRIEVE),
    ("011", "006", _forms("refer to", "refers to", "referred to", "referring to"), ComponentAction.RETRIEVE),
    ("012", "001", _forms("compare", "compares", "compared", "comparing"), ComponentAction.COMPARE),
    ("012", "002", _forms("rank", "ranks", "ranked", "ranking"), ComponentAction.COMPARE),
    ("012", "003", _forms("evaluate options", "evaluates options", "evaluated options", "evaluating options"), ComponentAction.COMPARE),
    ("012", "004", _forms("weigh evidence", "weighs evidence", "weighed evidence", "weighing evidence"), ComponentAction.COMPARE),
    ("012", "005", _forms("recommend", "recommends", "recommended", "recommending"), ComponentAction.RECOMMEND),
    ("013", "001", _forms("draft", "drafts", "drafted", "drafting"), ComponentAction.DRAFT),
    ("013", "002", _forms("prepare", "prepares", "prepared", "preparing"), ComponentAction.DRAFT),
    ("013", "003", _forms("write", "writes", "wrote", "written", "writing"), ComponentAction.DRAFT),
    ("013", "004", _forms("compose", "composes", "composed", "composing"), ComponentAction.DRAFT),
    ("013", "005", _forms("generate", "generates", "generated", "generating"), ComponentAction.DRAFT),
    ("013", "006", _forms("summarise", "summarises", "summarised", "summarising"), ComponentAction.SUMMARISE),
    ("013", "007", _forms("summarize", "summarizes", "summarized", "summarizing"), ComponentAction.SUMMARISE),
    ("014", "001", _forms("predict", "predicts", "predicted", "predicting"), ComponentAction.ASSESS),
    ("014", "002", _forms("forecast", "forecasts", "forecasted", "forecasting"), ComponentAction.ASSESS),
    ("014", "003", _forms("detect anomalies", "detects anomalies", "detected anomalies", "detecting anomalies"), ComponentAction.ASSESS),
    ("014", "004", _forms("identify patterns", "identifies patterns", "identified patterns", "identifying patterns"), ComponentAction.ASSESS),
    ("014", "005", _forms("identify trends", "identifies trends", "identified trends", "identifying trends"), ComponentAction.ASSESS),
    ("014", "006", _forms("flag unusual", "flags unusual", "flagged unusual", "flagging unusual"), ComponentAction.ASSESS),
    ("015", "001", _forms("contact", "contacts", "contacted", "contacting"), ComponentAction.CONTACT),
    ("015", "002", _forms("meet", "meets", "met", "meeting"), ComponentAction.CONTACT),
    ("015", "003", _forms("interview", "interviews", "interviewed", "interviewing"), ComponentAction.CONTACT),
    ("015", "004", _forms("discuss", "discusses", "discussed", "discussing"), ComponentAction.CONTACT),
    ("015", "005", _forms("reassure", "reassures", "reassured", "reassuring"), ComponentAction.CONTACT),
    ("015", "006", _forms("manage expectations", "manages expectations", "managed expectations", "managing expectations"), ComponentAction.CONTACT),
    ("015", "007", _forms("agree with", "agrees with", "agreed with", "agreeing with"), ComponentAction.CONTACT),
    ("015", "008", _forms("negotiate", "negotiates", "negotiated", "negotiating"), ComponentAction.NEGOTIATE),
    ("016", "001", _forms("decide", "decides", "decided", "deciding"), ComponentAction.DECIDE),
    ("016", "002", _forms("determine", "determines", "determined", "determining"), ComponentAction.DECIDE),
    ("016", "003", _forms("make the final determination", "makes the final determination", "made the final determination", "making the final determination"), ComponentAction.DECIDE),
    ("016", "004", _forms("make final determination", "makes final determination", "made final determination", "making final determination"), ComponentAction.DECIDE),
    ("016", "005", _forms("approve", "approves", "approved", "approving"), ComponentAction.APPROVE),
    ("016", "006", _forms("authorize", "authorizes", "authorized", "authorizing"), ComponentAction.APPROVE),
    ("016", "007", _forms("authorise", "authorises", "authorised", "authorising"), ComponentAction.APPROVE),
    ("016", "008", _forms("sign off", "signs off", "signed off", "signing off"), ComponentAction.APPROVE),
    ("016", "009", _forms("sign the final determination", "signs the final determination", "signed the final determination", "signing the final determination"), ComponentAction.APPROVE),
    ("016", "010", _forms("sign final determination", "signs final determination", "signed final determination", "signing final determination"), ComponentAction.APPROVE),
    ("017", "001", _forms("use discretion", "uses discretion", "used discretion", "using discretion"), ComponentAction.ASSESS),
    ("017", "002", _forms("use professional judgement", "uses professional judgement", "used professional judgement", "using professional judgement"), ComponentAction.ASSESS),
    ("017", "003", _forms("use professional judgment", "uses professional judgment", "used professional judgment", "using professional judgment"), ComponentAction.ASSESS),
    ("017", "004", _forms("use judgement", "uses judgement", "used judgement", "using judgement"), ComponentAction.ASSESS),
    ("017", "005", _forms("use judgment", "uses judgment", "used judgment", "using judgment"), ComponentAction.ASSESS),
    ("017", "006", _forms("weigh exceptional circumstances", "weighs exceptional circumstances", "weighed exceptional circumstances", "weighing exceptional circumstances"), ComponentAction.ASSESS),
    ("017", "007", _forms("case by case", "case-by-case"), ComponentAction.ASSESS),
    ("018", "001", _forms("rework", "reworks", "reworked", "reworking"), ComponentAction.OTHER_SUPPORTED_ACTION),
    ("018", "002", _forms("repeat the work", "repeats the work", "repeated the work", "repeating the work"), ComponentAction.OTHER_SUPPORTED_ACTION),
    ("018", "003", _forms("enter again", "enters again", "entered again", "entering again"), ComponentAction.OTHER_SUPPORTED_ACTION),
    ("018", "004", _forms("re-enter", "re-enters", "re-entered", "re-entering"), ComponentAction.OTHER_SUPPORTED_ACTION),
    ("018", "005", _forms("duplicate entry", "duplicate entries"), ComponentAction.OTHER_SUPPORTED_ACTION),
    ("018", "006", _forms("correct again", "corrects again", "corrected again", "correcting again"), ComponentAction.OTHER_SUPPORTED_ACTION),
    ("018", "007", _forms("manual reconciliation", "manually reconcile", "manually reconciles", "manually reconciled", "manually reconciling"), ComponentAction.OTHER_SUPPORTED_ACTION),
    ("019", "001", _forms("delay", "delays", "delayed", "delaying"), ComponentAction.OTHER_SUPPORTED_ACTION),
    ("019", "002", _forms("wait", "waits", "waited", "waiting"), ComponentAction.OTHER_SUPPORTED_ACTION),
    ("019", "003", _forms("queue", "queues", "queued", "queuing", "queueing"), ComponentAction.OTHER_SUPPORTED_ACTION),
    ("019", "004", _forms("bottleneck", "bottlenecks", "bottlenecked", "bottlenecking"), ComponentAction.OTHER_SUPPORTED_ACTION),
    ("019", "005", _forms("handoff", "hand-off", "hand over", "hands over", "handed over", "handing over"), ComponentAction.OTHER_SUPPORTED_ACTION),
    ("019", "006", _forms("pass between", "passes between", "passed between", "passing between"), ComponentAction.OTHER_SUPPORTED_ACTION),
    ("021", "001", _forms("after"), None),
    ("021", "002", _forms("once"), None),
    ("021", "003", _forms("using"), None),
    ("021", "004", _forms("based on"), None),
    ("021", "005", _forms("then"), None),
    ("021", "006", _forms("and then"), None),
)


LITERAL_MANIFEST = tuple(
    LiteralFamily(
        pd2_rule_code=f"PD2-{rule}",
        matched_literal_code=f"PD2-{rule}-L{family}",
        surface_forms=forms,
        component_action=action,
    )
    for rule, family, forms, action in _FAMILY_SPECS
)


WORK_NEED_BY_RULE_ACTION: dict[tuple[str, ComponentAction], WorkNeedType] = {
    ("PD2-001", ComponentAction.RECORD): WorkNeedType.RECORD_INFORMATION,
    ("PD2-002", ComponentAction.UPDATE): WorkNeedType.RECORD_INFORMATION,
    ("PD2-003", ComponentAction.NOTIFY): WorkNeedType.ROUTE_OR_NOTIFY,
    ("PD2-004", ComponentAction.ROUTE): WorkNeedType.ROUTE_OR_NOTIFY,
    ("PD2-004", ComponentAction.ASSIGN): WorkNeedType.ROUTE_OR_NOTIFY,
    ("PD2-005", ComponentAction.SCHEDULE): WorkNeedType.SCHEDULE_OR_MONITOR,
    ("PD2-006", ComponentAction.MONITOR): WorkNeedType.SCHEDULE_OR_MONITOR,
    ("PD2-006", ComponentAction.FOLLOW_UP): WorkNeedType.SCHEDULE_OR_MONITOR,
    ("PD2-007", ComponentAction.TRANSFORM): WorkNeedType.TRANSFORM_INFORMATION,
    ("PD2-008", ComponentAction.INTERPRET): WorkNeedType.INTERPRET_INFORMATION,
    ("PD2-009", ComponentAction.INVESTIGATE): WorkNeedType.INVESTIGATE_MATTER,
    ("PD2-010", ComponentAction.CATEGORISE): WorkNeedType.CATEGORISE_ITEM,
    ("PD2-011", ComponentAction.RETRIEVE): WorkNeedType.RETRIEVE_KNOWLEDGE,
    ("PD2-012", ComponentAction.COMPARE): WorkNeedType.COMPARE_OR_RECOMMEND,
    ("PD2-012", ComponentAction.RECOMMEND): WorkNeedType.COMPARE_OR_RECOMMEND,
    ("PD2-013", ComponentAction.DRAFT): WorkNeedType.CREATE_CONTENT,
    ("PD2-013", ComponentAction.SUMMARISE): WorkNeedType.CREATE_CONTENT,
    ("PD2-014", ComponentAction.ASSESS): WorkNeedType.PREDICT_OR_DETECT_PATTERN,
    ("PD2-015", ComponentAction.CONTACT): WorkNeedType.INTERACT_WITH_PERSON,
    ("PD2-015", ComponentAction.NEGOTIATE): WorkNeedType.INTERACT_WITH_PERSON,
    ("PD2-016", ComponentAction.DECIDE): WorkNeedType.MAKE_ACCOUNTABLE_DECISION,
    ("PD2-016", ComponentAction.APPROVE): WorkNeedType.MAKE_ACCOUNTABLE_DECISION,
    ("PD2-017", ComponentAction.ASSESS): WorkNeedType.MAKE_ACCOUNTABLE_DECISION,
    ("PD2-018", ComponentAction.OTHER_SUPPORTED_ACTION): WorkNeedType.IMPROVE_PROCESS_FLOW,
    ("PD2-019", ComponentAction.OTHER_SUPPORTED_ACTION): WorkNeedType.IMPROVE_PROCESS_FLOW,
}


PRELIMINARY_EVALUATOR_RULES_V0_2 = PreliminaryEvaluatorRulesV2(
    rule_set_id=RULE_SET_ID,
    rule_set_version=RULE_SET_VERSION,
    rule_set_status=CONTRACT_STATUS,
    evaluator_id="preliminary-evaluator.v0.2",
    evaluator_version="0.2.0",
    output_schema_id=OUTPUT_SCHEMA_ID,
    normalization=("NFKC", "CASEFOLD", "UNICODE_WHITESPACE_TO_ASCII_SPACE", "TRIM", "TOKEN_PUNCTUATION_AND_SYMBOL_TO_SPACE", "COLLAPSE_SPACES", "NO_STEM", "NO_FUZZY", "NO_SYNONYMS"),
    hard_boundaries=("PERIOD", "QUESTION", "EXCLAMATION", "SEMICOLON", "LINE_FEED", "LIST_ITEM", "COLON_BEFORE_LIST_OR_LINE_FEED"),
    protected_abbreviations=("e.g.", "i.e.", "mr.", "mrs.", "ms.", "dr.", "no.", "etc.", "vs."),
    conjunctions=("and", "then", "and then"),
    guards=("G1_SOURCE", "G2_CURRENT_STATE", "G3_ACTOR", "G4_ACTION", "G5_ASSERTION", "G6_OBJECT", "G7_REQUIRED_FIELDS", "G8_NON_NEGATED", "G9_NON_EXAMPLE", "G10_NON_CONFLICTING", "NORMATIVE_SHOULD_ALL_TEN_CONDITIONS"),
    literal_manifest=LITERAL_MANIFEST,
    work_need_mapping=tuple((rule, action.value, need.value) for (rule, action), need in WORK_NEED_BY_RULE_ACTION.items()),
    precedence=("STAGE_0_VALIDITY_CONFLICT_INSEPARABILITY", "STAGE_1_ASSISTANCE_VETO", "STAGE_2_ACCOUNTABLE_HUMAN_DECISION", "STAGE_3_PROCESS_FRICTION", "STAGE_4_CONVENTIONAL_SUFFICIENCY", "STAGE_5_SEMANTIC_AI_CAPABILITY", "STAGE_6_RELATIONAL_OR_DISCRETION", "STAGE_7_REMAINING"),
    conventional_sufficiency=("CS1_TRIGGER_OR_INPUT", "CS2_DETERMINISTIC_OPERATION", "CS3_COMPLETE_OUTPUT", "CS4_NO_EMBEDDED_SEMANTIC_WORK", "CS5_UPSTREAM_DEPENDENCIES", "CS6_EXCEPTIONS", "CS7_COMPLETE_WORK_NEED"),
    pd2_to_pa2_mapping=(
        ("PD2-001", ("PA2-040",), "CONVENTIONAL_SUFFICIENCY"),
        ("PD2-002", ("PA2-040",), "CONVENTIONAL_SUFFICIENCY"),
        ("PD2-003", ("PA2-040",), "CONVENTIONAL_SUFFICIENCY"),
        ("PD2-004", ("PA2-040",), "CONVENTIONAL_SUFFICIENCY"),
        ("PD2-005", ("PA2-040",), "CONVENTIONAL_SUFFICIENCY"),
        ("PD2-006", ("PA2-040",), "FIXED_TRIGGER_CONDITION_RESPONSE_AND_CONVENTIONAL_SUFFICIENCY"),
        ("PD2-007", ("PA2-041",), "EXPLICIT_TRANSFORMATION_AND_CONVENTIONAL_SUFFICIENCY"),
        ("PD2-008", ("PA2-020", "PA2-050", "PA2-051", "PA2-052"), "SEMANTIC_CAPABILITY_AND_GOVERNANCE"),
        ("PD2-009", ("PA2-020", "PA2-050", "PA2-051", "PA2-052"), "SEMANTIC_CAPABILITY_AND_GOVERNANCE"),
        ("PD2-010", ("PA2-020", "PA2-040", "PA2-050", "PA2-051", "PA2-052"), "CLOSED_MAPPING_OR_SEMANTIC_CAPABILITY_AND_GOVERNANCE"),
        ("PD2-011", ("PA2-020", "PA2-040", "PA2-050", "PA2-051", "PA2-052"), "EXACT_LOOKUP_OR_SEMANTIC_CAPABILITY_AND_GOVERNANCE"),
        ("PD2-012", ("PA2-020", "PA2-050", "PA2-051", "PA2-052"), "SEMANTIC_CAPABILITY_AND_GOVERNANCE"),
        ("PD2-013", ("PA2-020", "PA2-050", "PA2-051", "PA2-052"), "SEMANTIC_CAPABILITY_AND_GOVERNANCE"),
        ("PD2-014", ("PA2-020", "PA2-050", "PA2-051", "PA2-052"), "SEMANTIC_CAPABILITY_AND_GOVERNANCE"),
        ("PD2-015", ("PA2-021",), "MATERIAL_RELATIONAL_WORK"),
        ("PD2-016", ("PA2-020",), "ACCOUNTABLE_HUMAN_DECISION_OR_APPROVAL"),
        ("PD2-017", ("PA2-021",), "MATERIAL_DISCRETION"),
        ("PD2-018", ("PA2-030",), "MATERIAL_REWORK"),
        ("PD2-019", ("PA2-030",), "MATERIAL_DELAY_QUEUE_BOTTLENECK_OR_HANDOFF"),
        ("PD2-020", (), "STRUCTURAL_ATOMIC_SPLITTING_ONLY"),
        ("PD2-021", (), "STRUCTURAL_DEPENDENCY_ONLY"),
    ),
    governance_rules=(
        "PA2-050_COMPLETE_DOCUMENTARY_ASSISTANCE_SCOPE_RISK_CONSEQUENCE_REVIEW_REVIEWER_OWNER_ESCALATION_PERMISSION_SAFETY_LEGAL_PRIVACY_REGULATORY",
        "PA2-051_SUPPORTED_SEMANTIC_WORK_UNRESOLVED_ASSISTANCE_GOVERNANCE_NO_VETO_NO_HIGH_RISK",
        "PA2-052_COMPLETE_POSITIVE_DOCUMENTARY_PREDICTABILITY_DATA_RISK_CONSEQUENCE_JUDGMENT_REVIEW_OWNER_ESCALATION_PERMISSION_SAFETY_LEGAL_PRIVACY_REGULATORY",
        "DOCUMENTED_RISK_OR_ERROR_CONSEQUENCE_4_OR_5_FORBIDS_PA2_050_AND_PA2_051",
    ),
    affirmative_no_change_bundle=(
        "CURRENT_PURPOSE_EXPLICIT",
        "PURPOSE_BEING_ACHIEVED",
        "PERFORMANCE_ACCEPTABLE",
        "CONTROLS_ACCEPTABLE",
        "NO_MATERIAL_PROCESS_PROBLEM",
        "NO_INTERVENTION_NEED",
        "NO_DIRECTION_BEARING_COMPONENT_OR_WORK_NEED",
        "NO_MATERIAL_UNKNOWN",
        "NO_MATERIAL_CONFLICT",
    ),
    work_need_construction=(
        "GREEDY_LEFT_TO_RIGHT",
        "NO_LOOKAHEAD_OR_BACKTRACKING",
        "IDENTICAL_TYPE_AND_SIGNATURES",
        "EQUAL_OBJECT_OR_EXACT_PD2_021_DEPENDENCY",
    ),
    opportunity_grouping=(
        "GREEDY_LEFT_TO_RIGHT",
        "ADJACENT_SAME_DIRECTION_AND_DECIDING_CODE",
        "NO_MATERIAL_CONFLICT",
        "EXACT_GOVERNING_SIGNATURES",
        "SAME_WORK_NEED_OR_EXACT_PD2_021_DEPENDENCY",
        "EQUAL_OBJECT_OR_EXACT_OUTPUT_INPUT_DEPENDENCY",
        "POG2_001_TO_POG2_004",
    ),
    evidence_coverage_rules=(
        "HIGH_ZERO_MATERIAL_INFERENCES_ALL_DOCUMENTED_NO_UNKNOWN_OR_CONFLICT",
        "MEDIUM_EXACTLY_ONE_MATERIAL_INFERENCE_ALL_RESOLVED_NO_UNKNOWN_OR_CONFLICT",
        "LOW_TWO_OR_MORE_INFERENCES_OR_PA2_051_OR_DISCOVERY_OR_UNKNOWN_CONFLICT_LIMITATION",
        "ACTIVITY_WEAKEST_RESULT",
        "PROCESS_WEAKEST_ACTIVITY",
    ),
    mechanical_errata=(
        "PRI2_ID_EXCLUDES_COMPONENT_WORK_NEED_OPPORTUNITY_RUN_TIMESTAMP_AND_RATIONALE",
        "MATCHED_LITERAL_CODES_ARE_IMMUTABLE_FAMILY_CODES",
        "PD2_021_EXACT_OUTPUT_INPUT_DEPENDENCY_USES_PD2_021_S001",
        "WORK_NEEDS_USE_GREEDY_NON_BACKTRACKING_CONSTRUCTION",
        "PD2_001_DEFAULT_OUTPUT_IS_RECORDED_FORM_NORMALIZED_OBJECT_KEY",
        "EXPLICIT_RECORDED_OBJECT_CANONICALIZES_TO_RECORDED_FORM_FOR_DEPENDENCY_ONLY",
    ),
    opportunity_limit=5,
    identifier_schemas=("preliminary-rule-derived-inference-id.v0.2", "preliminary-component-id.v0.2", "preliminary-work-need-id.v0.2", "preliminary-opportunity-id.v0.2", "preliminary-scoped-discovery-id.v0.2"),
)
