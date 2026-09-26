# Four-Gate Migration Design v0.1

Status: **DECISION-READY DESIGN — NOT IMPLEMENTED**  
Date: **2026-09-02**  
Last verified against code: **2026-09-03**  
Scope: successor decision contract only; no production, policy, schema, persistence, UI, or frozen-artifact change is made by this document.

## 1. Executive recommendation

Implement the four-gate framework as a versioned successor contract beside, not on top of, the shipped contract.

The successor should:

1. keep `decision_policy.v0.2`, `phase1-v0.3`, `phase5-v0.1`, `phase6-v0.1`, all current SQLite rows, and all frozen evaluation outputs byte-for-byte unchanged;
2. introduce an explicit four-gate policy and output family (`decision_policy.v0.3`, `phase1-v0.4`, `phase5-v0.2`, and `phase6-v0.2` are the recommended identifiers);
3. represent decision status, change disposition, intervention family, and AI autonomy separately, then derive the customer-facing outcome from that typed combination;
4. make evidence sufficiency a path-specific precondition evaluated before each material rule, with `DISCOVERY_REQUIRED` taking precedence over any numeric conclusion at that point;
5. treat a known, sufficiently evidenced readiness failure as `PROCESS_IMPROVEMENT_FIRST`, never as `DISCOVERY_REQUIRED`;
6. pin each assessment workspace to a decision-contract version so a reset or reassessment cannot silently move a historical v0.2 assessment to the successor policy;
7. ship in narrow vertical slices, beginning with an explicitly invoked, persistence-free four-gate domain engine while the current application default remains v0.2.

This design resolves O-001 through O-006 with recommendations. Approval of those recommendations should be recorded in `02_DECISIONS.md` before implementation.

## 2. Current/target conflict

The conflict is expected and must remain visible:

- Current production evaluates `evidence_sufficiency -> technical_fit -> business_value -> risk_and_autonomy` and returns one of `AUTOMATE`, `AUGMENT`, `INVESTIGATE_FURTHER`, or `DO_NOT_RECOMMEND`.
- The adopted target evaluates `Should We Change It? -> Is It Ready? -> What Is the Best Intervention? -> How Much Autonomy Is Safe?` and must distinguish AI, conventional, process-improvement, human-led, and discovery results.
- Current Phase 5, Phase 6, persistence, presentation, GRW, M2 reassessment, and evaluation records encode the legacy gate and recommendation types. Renaming the enum or editing policy v0.2 in place would corrupt meaning and compatibility.

Therefore the migration is a parallel versioned contract, not a rename and not a reinterpretation of stored output.

### Verification basis

This design was checked against branch `codex/validate-process-workspace` at HEAD `d200a6527b87d7b3ef9eaa8b25767fa086c7ff02`. The working tree was already dirty; all unrelated tracked deletions/modifications and untracked files were left untouched.

The contract inventory was verified directly against:

- `config/decision_policy.v0.2.json`;
- `models/process.py`, `models/assessment.py`, `models/integrated_assessment.py`, `models/decision_support.py`, and `models/enums.py`;
- `decision/capabilities.py`, `decision/policy.py`, `decision/gates.py`, `decision/engine.py`, and `decision/scoring.py`;
- Phase 5/6 services, workspace orchestration, SQLite migrations, main-artifact serialization, GRW M1, M2 reassessment models/serialization, DCW, presentation projections, and directly coupled tests.

This is implementation evidence for the migration design, not evidence that the successor framework is implemented or validated.

## 3. Recommended successor output contract

### 3.1 Typed activity decision

Each activity result should contain these independently validated fields:

| Field | Recommended values | Meaning |
|---|---|---|
| `decision_status` | `COMPLETE`, `DISCOVERY_REQUIRED` | Whether the framework reached a substantive decision or stopped on material evidence. |
| `change_disposition` | `CHANGE_JUSTIFIED`, `NO_CHANGE_JUSTIFIED`, `NOT_DETERMINED` | Gate 1's answer. It is not an intervention or an autonomy level. |
| `intervention_family` | `AI`, `CONVENTIONAL_AUTOMATION`, `PROCESS_IMPROVEMENT_FIRST`, `KEEP_HUMAN_LED`, `NOT_APPLICABLE`, `NOT_DETERMINED` | Gate 3 selection, or the terminal readiness intervention from Gate 2. `NOT_APPLICABLE` is used after `NO_CHANGE_JUSTIFIED`; `NOT_DETERMINED` applies only when discovery stops before an intervention is selected. |
| `autonomy_ceiling` | `AI_AUTOMATION`, `AI_ASSISTED`, `AI_NOT_PERMITTED`, `NOT_APPLICABLE`, `NOT_DETERMINED` | Maximum safe AI role. It is material only when Gate 3 selects AI. |
| `outcome_code` | derived values below | Read-only canonical outcome derived from the four fields above; it must not be independently writable. |
| `gate_results` | exactly four ordered successor results | Audit record for each gate, including not-evaluated gates. |
| `blocking_gaps` | typed evidence gaps | Present and non-empty only for `DISCOVERY_REQUIRED`. |
| `capabilities` | existing ordered `Capability` values | Deterministic projection of sufficiently supported capability signals; never LLM-selected. |
| `criteria` and `human_accountability` | successor provenance models using the existing values, knowledge states, rationales, evidence IDs, and confidence | Preserve reviewed inputs and record their actual material gates without mutating the approved process. |
| `priority_status` | `COMPLETE`, `NOT_APPLICABLE` | `COMPLETE` only for complete AI automation/assisted outcomes; all other successor outcomes are not priority-ranked in this contract. |
| `priority` | existing transparent score shape or `null` | Retained only for complete AI opportunities in v0.1 of the successor. With the recommended Gate 1/2/4 materiality, every scoring input is sufficient on a completed AI path, so priority is complete by construction. |
| `reasoning` and `evidence` | deterministic rationale list and referenced evidence records | Preserve the current explainability surface, using successor tokens and only evidence referenced by the activity, material criteria/accountability, and material capability signals. |

Valid field combinations are closed, not permissive:

| Path/result | Status | Change disposition | Intervention family | Autonomy ceiling | Derived outcome |
|---|---|---|---|---|---|
| Discovery at Gate 1 | `DISCOVERY_REQUIRED` | `NOT_DETERMINED` | `NOT_DETERMINED` | `NOT_DETERMINED` | `DISCOVERY_REQUIRED` |
| Discovery at Gate 2 or Gate 3 | `DISCOVERY_REQUIRED` | `CHANGE_JUSTIFIED` | `NOT_DETERMINED` | `NOT_DETERMINED` | `DISCOVERY_REQUIRED` |
| Discovery at Gate 4 after AI selection | `DISCOVERY_REQUIRED` | `CHANGE_JUSTIFIED` | `AI` | `NOT_DETERMINED` | `DISCOVERY_REQUIRED` |
| Gate 1 stop | `COMPLETE` | `NO_CHANGE_JUSTIFIED` | `NOT_APPLICABLE` | `NOT_APPLICABLE` | `NO_CHANGE_JUSTIFIED` |
| Gate 2 readiness stop | `COMPLETE` | `CHANGE_JUSTIFIED` | `PROCESS_IMPROVEMENT_FIRST` | `NOT_APPLICABLE` | `PROCESS_IMPROVEMENT_FIRST` |
| Gate 3 conventional selection | `COMPLETE` | `CHANGE_JUSTIFIED` | `CONVENTIONAL_AUTOMATION` | `NOT_APPLICABLE` | `CONVENTIONAL_AUTOMATION` |
| Gate 3 human-led selection | `COMPLETE` | `CHANGE_JUSTIFIED` | `KEEP_HUMAN_LED` | `NOT_APPLICABLE` | `KEEP_HUMAN_LED` |
| Gate 4 AI veto | `COMPLETE` | `CHANGE_JUSTIFIED` | `AI` | `AI_NOT_PERMITTED` | `KEEP_HUMAN_LED` |
| Gate 4 assisted ceiling | `COMPLETE` | `CHANGE_JUSTIFIED` | `AI` | `AI_ASSISTED` | `AI_ASSISTED_WORK` |
| Gate 4 automation ceiling | `COMPLETE` | `CHANGE_JUSTIFIED` | `AI` | `AI_AUTOMATION` | `AI_AUTOMATION` |

Recommended derived `outcome_code` rules, in precedence order:

1. `decision_status == DISCOVERY_REQUIRED` -> `DISCOVERY_REQUIRED`.
2. `change_disposition == NO_CHANGE_JUSTIFIED` -> `NO_CHANGE_JUSTIFIED`.
3. `intervention_family == PROCESS_IMPROVEMENT_FIRST` -> `PROCESS_IMPROVEMENT_FIRST`.
4. `intervention_family == CONVENTIONAL_AUTOMATION` -> `CONVENTIONAL_AUTOMATION`.
5. `intervention_family == KEEP_HUMAN_LED` -> `KEEP_HUMAN_LED`.
6. `intervention_family == AI` and `autonomy_ceiling == AI_AUTOMATION` -> `AI_AUTOMATION`.
7. `intervention_family == AI` and `autonomy_ceiling == AI_ASSISTED` -> `AI_ASSISTED_WORK`.
8. `intervention_family == AI` and `autonomy_ceiling == AI_NOT_PERMITTED` -> `KEEP_HUMAN_LED`.
9. Every other combination is invalid and must fail schema validation.

`NO_CHANGE_JUSTIFIED` adds a seventh customer outcome while keeping the six adopted target outcomes intact. This is recommended because a current activity may be system-led, outsourced, or already automated; calling every Gate 1 stop `KEEP_HUMAN_LED` would assert a human operating model that may not exist.

At process level, `FourGateProcessAssessment` should retain `process_id`, `process_name`, ordered step assessments, `policy_id`, `policy_version`, and `policy_status`, and add `framework_id`, `framework_version`, and `decision_contract_version`. When Phase 5 later embeds this output, its separate policy reference must add the canonical policy fingerprint and verify all duplicated policy identity fields rather than trusting either copy independently.

### 3.2 Gate result contract

Do not reuse the legacy `GateName` or rely on legacy `FAILED` to represent missing evidence. Introduce successor-only types:

| Field | Contract |
|---|---|
| `gate` | `SHOULD_WE_CHANGE`, `IS_IT_READY`, `BEST_INTERVENTION`, `SAFE_AUTONOMY` |
| `status` | `COMPLETED`, `COMPLETED_WITH_CONSTRAINTS`, `BLOCKED_BY_EVIDENCE`, `NOT_EVALUATED` |
| `decision_code` | A gate-specific code such as `CHANGE_JUSTIFIED`, `PROCESS_IMPROVEMENT_FIRST`, `AI_SELECTED`, or `AI_ASSISTED_REQUIRED`. |
| `rationale` | Non-empty deterministic explanation. |
| `material_criteria` | Criteria actually used at this gate on this path. |
| `accountability_material` | Whether human accountability was material. |
| `evidence_ids` | Only accepted evidence used by the gate. |
| `blocking_gaps` | Typed gaps when status is `BLOCKED_BY_EVIDENCE`; empty otherwise. |

Exactly four results must be returned in gate order. After a completed terminal result or an evidence stop, later gates are `NOT_EVALUATED` and state which earlier gate ended the sequence. A known negative or constrained answer is `COMPLETED`/`COMPLETED_WITH_CONSTRAINTS`, not `FAILED`.

### 3.3 Typed evidence gap

Each blocking gap should contain:

- `field_name` (criterion, accountability, or activity evidence);
- `gate` where the evidence became material;
- `problem_code`: `UNKNOWN`, `VALUE_MISSING`, `INFERRED_CONFIDENCE_TOO_LOW`, `EVIDENCE_REFERENCE_MISSING`, or `ACTIVITY_EVIDENCE_MISSING`;
- a deterministic `blocking_question` suitable for the optional evidence-resolution path;
- existing evidence IDs, if any, without implying that they are sufficient.

Unknown remains distinct from zero. An inferred value below the configured confidence floor and a material value with no required evidence reference are also insufficient.

## 4. Exact gate semantics and precedence

### 4.1 Cross-cutting evidence algorithm

For each gate:

1. Determine whether the gate is applicable on the path already established.
2. Determine the inputs material to that applicable gate.
3. Validate activity evidence and those inputs before evaluating any threshold or rule.
4. If any material input is insufficient, return `DISCOVERY_REQUIRED`, record the current gate as `BLOCKED_BY_EVIDENCE`, and mark every later gate `NOT_EVALUATED`.
5. Otherwise evaluate the substantive deterministic gate rule.

This ordering is mandatory. A low number with missing support does not prove low readiness; it produces discovery. A known, sufficiently supported low number may produce a substantive outcome.

### 4.2 Gate 1 — Should We Change It?

Material decision input: `business_value`.

`repetition` may be displayed as supporting context, but should not become Gate 1 material in successor v0.1 because the current framework has no approved rule by which frequency overrides business value. It remains material at Gate 2 and to priority.

Provisional rule carried forward from v0.2:

- `business_value < minimum_business_value` -> `NO_CHANGE_JUSTIFIED`; later gates are not evaluated.
- otherwise -> `CHANGE_JUSTIFIED` and continue.

The current threshold (`2`) may be copied into v0.3 as explicitly provisional; this is continuity, not validation.

### 4.3 Gate 2 — Is It Ready?

Material inputs: `repetition`, `predictability`, `data_readiness`, `ai_capability_fit`, and `implementation_complexity`.

Recommended deterministic roles:

- `data_readiness < minimum_data_readiness` -> `PROCESS_IMPROVEMENT_FIRST`.
- `implementation_complexity > maximum_implementation_complexity_for_readiness` -> `PROCESS_IMPROVEMENT_FIRST`. The recommended provisional ceiling is `4`, because the existing scale defines `5` as exceptionally complex or currently infeasible.
- Low repetition or predictability does not automatically mean the process should be improved. Their sufficiently evidenced values complete the readiness profile; predictability can later constrain Gate 4 automation, while repetition remains a priority input.
- Low AI capability fit does not make the activity unready for an intervention decision; it rules against AI when Gate 3 compares interventions.
- Otherwise -> `READY_FOR_INTERVENTION_SELECTION` and continue.

The current minimum data-readiness threshold (`2`) may be carried forward provisionally. No new predictive-validity or calibration claim is made.

### 4.4 Gate 3 — What Is the Best Intervention?

Material direct input: `conventional_solution_fit`. Gate 3 also consumes the completed Gate 1 and Gate 2 findings and the deterministic capability mapping; it does not reclassify their evidence.

Recommended deterministic precedence:

1. If Gate 2 already concluded `PROCESS_IMPROVEMENT_FIRST`, Gate 3 is not evaluated.
2. If `conventional_solution_fit >= conventional_solution_fit_cutoff`, select `CONVENTIONAL_AUTOMATION`.
3. Else if `ai_capability_fit >= minimum_ai_capability_fit` and at least one sufficiently evidenced capability signal maps to a concrete capability, select `AI` and continue to Gate 4.
4. If AI fit reaches the threshold but no capability maps because the relevant capability signal remains unresolved, return `DISCOVERY_REQUIRED` at Gate 3 with the blocking question “Which concrete AI capability applies to this activity?”.
5. Else select `KEEP_HUMAN_LED`.

This preserves the current anti-use-case-manufacturing rule while making its true intervention explicit. A known-false capability signal does not create discovery, an unresolved signal is not imputed as false when it is needed to establish an AI path, and one sufficiently supported true signal is enough; unrelated unknown signals remain non-material. `WORKFLOW_AUTOMATION` remains a neutral capability taxonomy value and does not itself prove that AI is preferable. The v0.2 cutoffs (`4` conventional, `3` AI fit) may be carried forward as provisional continuity values.

### 4.5 Gate 4 — How Much Autonomy Is Safe?

Gate 4 is material only when Gate 3 selected `AI`. For conventional automation, process improvement, human-led work, or no change, its gate status is `NOT_EVALUATED` with decision code `NOT_APPLICABLE`; the activity-level autonomy field is `NOT_APPLICABLE`. Missing risk evidence does not create a discovery stop on those paths.

Material inputs for an AI path: `human_judgement_requirement`, `risk_consequence`, `residual_risk_with_human_oversight`, and `human_accountability_required`. The completed Gate 2 readiness finding supplies already-validated predictability and data-readiness facts used by the strict automation test; those criteria remain attributed to Gate 2 for evidence lineage.

Recommended rule order, preserving v0.2 thresholds provisionally:

1. Check Gate 4 evidence. Any insufficiency -> `DISCOVERY_REQUIRED`.
2. `residual_risk_with_human_oversight >= unacceptable_residual_risk` -> `AI_NOT_PERMITTED`, derived outcome `KEEP_HUMAN_LED`.
3. If accountability is required, judgement/risk/residual-risk reaches an augmentation threshold, or any strict automation threshold is not met -> `AI_ASSISTED`.
4. Only when every strict automation condition is met -> `AI_AUTOMATION`.

Human oversight never converts unacceptable residual risk into acceptable automation by assumption.

## 5. `DISCOVERY_REQUIRED` versus `PROCESS_IMPROVEMENT_FIRST`

This distinction is a hard invariant:

| Situation | Result |
|---|---|
| A material value is unknown/null. | `DISCOVERY_REQUIRED` |
| An inferred material value is below the confidence floor. | `DISCOVERY_REQUIRED` |
| A required material evidence reference is absent. | `DISCOVERY_REQUIRED` |
| The activity itself lacks required source evidence. | `DISCOVERY_REQUIRED` |
| A material readiness value is known, confidence-acceptable, traceable, and fails an approved readiness rule. | `PROCESS_IMPROVEMENT_FIRST` |
| A non-material value is missing on the path. | Continue; preserve it as an unknown, but do not stop the decision. |

`DISCOVERY_REQUIRED` says “the product cannot yet decide.” `PROCESS_IMPROVEMENT_FIRST` says “the product has enough evidence to decide that readiness work is the best next intervention.” The latter must name the evidenced readiness blocker. Neither is evidence that AI is suitable.

## 6. Mapping the current decision framework

### 6.1 Current gates

| Current gate | Current role | Successor mapping | Compatibility treatment |
|---|---|---|---|
| `evidence_sufficiency` | Checks activity evidence before decision gates. | Cross-cutting precondition before every applicable gate; activity evidence is checked before Gate 1. | Preserve historical result. Do not expose it as a fifth successor gate. |
| `technical_fit` | AI fit, conditional conventional fit, data readiness; may return investigation or rejection. | Split across Gate 2 (`ai_capability_fit`, `data_readiness`) and Gate 3 (`conventional_solution_fit`). | No mechanical conversion of stored results. |
| `business_value` | Minimum-value check after technical fit. | Gate 1, evaluated first. | Historical order remains accurately labelled as legacy. |
| `risk_and_autonomy` | Risk, judgement, residual risk, accountability, and conditional predictability determine automate/augment/reject. | Gate 4; predictability is evidenced at Gate 2 and consumed through its finding. | Preserve v0.2 result and rationale verbatim. |

### 6.2 The 11 inputs

| Input | Current role | Primary successor role | Evidence/materiality rule |
|---|---|---|---|
| `repetition` | Priority only. | Gate 2 readiness profile; priority. | Material at Gate 2 in the successor; may support Gate 1 copy without changing its rule. |
| `predictability` | Conditional at risk/autonomy; priority; strict automation. | Gate 2, with its validated finding consumed by Gate 3/Gate 4. | Checked once at Gate 2; lineage remains visible in final autonomy. |
| `data_readiness` | Technical-fit minimum; priority; strict automation. | Gate 2 readiness; strict automation consumes Gate 2 finding. | Known low -> process improvement; insufficient evidence -> discovery. |
| `ai_capability_fit` | Technical-fit minimum; priority. | Gate 2 profile and Gate 3 AI comparison. | Low fit rules against AI but does not manufacture a readiness failure. |
| `human_judgement_requirement` | Gate 4 equivalent. | Gate 4. | Material only on an AI path. |
| `business_value` | Current business-value gate; priority. | Gate 1; priority. | Always material at applicable Gate 1. |
| `risk_consequence` | Current risk/autonomy; priority. | Gate 4; priority. | Material only on an AI path. |
| `residual_risk_with_human_oversight` | Current risk/autonomy. | Gate 4. | Unacceptable known residual risk prohibits AI autonomy. |
| `implementation_complexity` | Priority only. | Gate 2 readiness ceiling and priority. | Dual role is explicit; it is not a hidden Gate 3 weight. |
| `conventional_solution_fit` | Conditional technical-fit rejection. | Gate 3 direct comparison. | Material only if Gate 3 is reached. |
| `human_accountability_required` | Separate typed field at risk/autonomy. | Gate 4 separate typed field. | Remains Boolean/unknown; never converted to 0–5. |

Values, knowledge state, rationale, evidence IDs, inferred confidence, and reviewed lineage remain unchanged input concepts. No twelfth dimension is introduced.

### 6.3 Capability signals and mapped capabilities

The current input contract also contains ten provenance-aware Boolean/unknown capability signals. They are not assessment dimensions, but they are reviewed inputs, are included in Phase 5 traceability, and deterministically produce the `capabilities` list. They must not disappear from the successor contract.

| Current signal | Deterministic mapped capability |
|---|---|
| `reads_unstructured_documents` | `DOCUMENT_INFORMATION_EXTRACTION` |
| `categorises_items` | `CLASSIFICATION` |
| `predicts_future_outcomes` | `PREDICTION_FORECASTING` |
| `detects_anomalies_or_patterns` | `ANOMALY_PATTERN_DETECTION` |
| `creates_new_content` | `GENERATIVE_AI` |
| `searches_reference_knowledge` | `KNOWLEDGE_RETRIEVAL` |
| `ranks_or_suggests_options` | `RECOMMENDATION` |
| `supports_complex_decisions` | `DECISION_SUPPORT` |
| `interprets_images_or_video` | `COMPUTER_VISION` |
| `routes_or_orchestrates_work` | `WORKFLOW_AUTOMATION` |

Successor treatment:

- preserve each signal's value, knowledge state, rationale, evidence IDs, and inferred confidence, plus the stable mapping order;
- do not turn the signals into ten extra scored dimensions or allow a language model to select a capability;
- use the mapping at Gate 3 only after conventional automation has been considered;
- require at least one sufficiently evidenced true signal before selecting `AI`; when AI fit is otherwise sufficient but the mapping is blocked by unresolved signals, use typed discovery rather than treating unknown as false;
- retain every signal in the Phase 5 traceability record whether or not it becomes material on the selected path.

### 6.4 Current recommendation modes

| Current mode | Closest successor expression | Why no automatic historical conversion is allowed |
|---|---|---|
| `AUTOMATE` | `intervention_family=AI`, `autonomy_ceiling=AI_AUTOMATION` | Similar semantics, but gate order and materiality differ. |
| `AUGMENT` | `intervention_family=AI`, `autonomy_ceiling=AI_ASSISTED` | Similar semantics, but the new output records intervention and ceiling separately. |
| `INVESTIGATE_FURTHER` | Often `DISCOVERY_REQUIRED`; a known low data-readiness result could instead be `PROCESS_IMPROVEMENT_FIRST` under the successor. | Current code uses this mode both for insufficient evidence and known low data readiness. |
| `DO_NOT_RECOMMEND` | Could be `NO_CHANGE_JUSTIFIED`, `CONVENTIONAL_AUTOMATION`, `KEEP_HUMAN_LED`, or an AI veto. | The legacy token deliberately collapses multiple reasons. |

Historical values remain historical values. If a legacy screen needs comparison, it may display a non-authoritative “closest successor concept” explanation, never write a converted successor record.

### 6.5 Current policy fields

| v0.2 field | Successor treatment |
|---|---|
| `policy_id`, `version`, `status`, `description` | Required; new identity/version and the same provisional disclosure principle. |
| new `framework_id`, `framework_version`, `decision_contract_version` | Required in the separate successor policy model and must match the output envelope (`four-gate-framework.v0.1`, `0.1`, and `phase1-v0.4`). |
| `scale.minimum`, `scale.maximum`, `scale.unknown_representation`, all criterion directions/meanings | Retain unchanged unless a later explicit scale decision is made. |
| `evidence.minimum_inferred_confidence` | Retain. |
| `evidence.require_step_evidence_reference` | Retain as the pre-Gate-1 activity check. |
| `evidence.require_material_criterion_evidence_reference` | Retain and apply path-specifically. |
| new `evidence.require_material_capability_signal_evidence_reference` | Recommended `true`; applies only to capability signals needed to establish the Gate 3 AI path and must not make unrelated unknown signals material. |
| `evidence.material_by_gate` | Replace legacy keys with four-gate keys and include accountability separately. |
| `evidence.conditional_by_gate` | Make path conditions explicit: Gate 3 only after Gates 1/2; Gate 4 only for AI. |
| new `evidence.capability_mapping_gate` | Set explicitly to `BEST_INTERVENTION`; keeps capability-signal materiality out of the 11-dimension map while making the deterministic dependency auditable. |
| `minimum_business_value` | Gate 1. |
| `minimum_data_readiness` | Gate 2. |
| `minimum_ai_capability_fit` | Gate 3 AI selection, after Gate 2 evidence validation. |
| `conventional_solution_fit_cutoff` | Gate 3 and evaluated before AI selection. |
| `unacceptable_residual_risk` | Gate 4 AI veto. |
| `augment_human_judgement`, `augment_risk_consequence`, `augment_residual_risk` | Gate 4 assisted-work ceiling. |
| `automate_minimum_predictability`, `automate_minimum_data_readiness`, `automate_maximum_human_judgement`, `automate_maximum_risk_consequence`, `automate_maximum_residual_risk` | Gate 4 strict automation test, using validated Gate 2 facts where applicable. |
| new `maximum_implementation_complexity_for_readiness` | Gate 2. Recommended provisional value `4`; this is a new transparent rule, not a validated threshold. |
| `scoring.eligible_recommendations` | Replace with a predicate: complete AI outcome with ceiling `AI_AUTOMATION` or `AI_ASSISTED`. |
| `scoring.criteria` and each `weight`/`direction` | Preserve initially for continuity, including implementation complexity. Keep provisional disclosure. |
| `scoring.bands.high_minimum`, `scoring.bands.medium_minimum` | Preserve the current `70`/`50` cutoffs initially and keep them explicitly provisional. |

The current `DecisionPolicy` model hard-codes legacy gate keys and eligible legacy recommendations. The successor needs a separate policy model or a version-discriminated union; loosening the existing model would make v0.2 validation less safe.

## 7. Persisted and generated contract map

### 7.1 Main workspace artifacts

| Artifact | Current contract | Successor action |
|---|---|---|
| `INGESTION_RESULT` | `phase2-v0.1` | Unchanged. |
| `CANDIDATE_EXTRACTION_RESULT` | `phase3-v0.1` | Unchanged. The 11 inputs and evidence model remain. |
| `REVIEW_SESSION` | `phase4-v0.1` | Unchanged. |
| `APPROVED_REVIEW` | `phase4-v0.1` | Unchanged. Human approval remains mandatory. |
| `INTEGRATED_ASSESSMENT_RESULT` | `phase5-v0.1`, containing `phase1-v0.3` output and legacy trace paths | Add `phase5-v0.2` for successor output and `phase1-v0.4`; retain v0.1 reader indefinitely. Recommendation trace becomes an outcome-contract trace with explicit status/intervention/autonomy paths. |
| `DECISION_PACKAGE_RESULT` | `phase6-v0.1`, with legacy portfolio, future state, roadmap, governance, gaps, methodology, and 13 report sections | Add `phase6-v0.2`; retain v0.1 reader. Portfolio items must carry the successor typed decision. Report semantics must distinguish intervention from autonomy and no-change from human-led. |
| `GRW_EVIDENCE_SUBMISSION` | `grw-m1-v0.1`, pinned to a Phase 6 information gap | Keep v0.1 for legacy packages. A successor path requires a new GRW schema only when a four-gate gap is admitted; do not coerce the old `InformationGap`. |
| `GRW_EVIDENCE_REVIEW` | `grw-m1-v0.1`, including `GrwNonChangeProof` with legacy gate results and recommendation enum | Keep legacy-only initially. A successor proof must be versioned and snapshot `decision_status`, `intervention_family`, `autonomy_ceiling`, derived outcome, and successor gates. |

`phase1-v0.3` is not a standalone workspace artifact: it is the decision-output contract identified inside Phase 5 run metadata. Its successor, `phase1-v0.4`, must likewise remain explicitly identified inside `phase5-v0.2`. A successor `StepAssessmentTrace` replaces the single `recommendation_path` with paths for `decision_status`, `change_disposition`, `intervention_family`, `autonomy_ceiling`, and derived `outcome_code`, while preserving the ordered gate-results path and all reviewed-input traces.

The SQLite `assessment_artifacts` and `active_artifacts` tables already store artifact schema version, immutable revisions, hashes, parents, and active pointers. They do not need payload rewriting. Serialization must route adapters by `(artifact_type, artifact_schema_version)` rather than one adapter per artifact type.

### 7.2 Assessment workspace record

The current workspace record does not pin a decision contract before assessment. A successor release therefore requires an additive migration:

- add `decision_contract_version` to `assessments`;
- backfill every existing row in writable databases to `phase1-v0.3` without touching artifacts;
- require new rows to be created with an explicit supported contract;
- select the policy/engine from the pinned contract in `WorkspaceService.assess`;
- prohibit changing the pin after an approved review or any assessment artifact exists;
- include the pinned contract and policy fingerprint in assessment-operation idempotency material, so a completed legacy operation can never satisfy a successor request.

This is strictly required to prevent reset/re-run operations from silently reassessing an old workspace under a new default.

Frozen evaluation databases require a separate read-only compatibility path. The current protected-workspace guard requires its applied migration set to equal the application's complete `MIGRATIONS` set; adding migration 4 without changing that guard would reject an untouched migration-1–3 frozen database. The successor implementation must:

- recognise the exact migration-1–3 schema as a supported historical read-only schema;
- hydrate its missing `decision_contract_version` as a virtual `phase1-v0.3` pin in the legacy read adapter;
- never add the column, migration row, or any other bytes to the frozen database;
- keep current frozen-path write refusal and integrity/hash checks intact.

### 7.3 M2 controlled reassessment artifacts

All current M2 artifacts are persisted under `grw-m2-m1-v0.1`. The serializer currently dispatches only by artifact type, so any successor M2 family must dispatch by both artifact type and schema version; the legacy adapter and stored payload stay unchanged.

| M2 artifact | Coupling | Successor treatment |
|---|---|---|
| `RUN_MANIFEST` | Pins baseline package and policy identity. | Keep historical manifests unchanged; add decision-contract identity for new runs. Never mix contract families in one run. |
| `DOCUMENT_SUBMISSION`, `EVIDENCE_REVIEW` | Evidence-side records. | Payload semantics can remain, but new schema identity is needed if they reference a successor gap type. |
| `DATA_READINESS_RESOLUTION` | Hard-codes permitted gate `technical_fit`. | Legacy remains. Successor version permits `IS_IT_READY`; no string reinterpretation. |
| `REASSESSMENT_REQUEST`, `REASSESSMENT_APPROVAL` | Pin baseline and approved change. | Preserve legacy; successor versions pin the four-gate contract and policy fingerprint. |
| `SUCCESSOR_APPROVED_REVIEW` | One-field approved projection. | Input model can remain conceptually identical; contract identity must remain pinned. |
| `SUCCESSOR_INTEGRATED_ASSESSMENT` | Embeds Phase 5 legacy success. | Version to embed `phase5-v0.2` successor success only when baseline is also four-gate. |
| `SUCCESSOR_DECISION_PACKAGE` | Embeds Phase 6 legacy package. | Version to embed `phase6-v0.2` only for a four-gate run. |
| `BASELINE_SUCCESSOR_COMPARISON` | Compares legacy gate JSON and recommendation strings. | Add a version that compares same-contract typed outcomes and four-gate results. Cross-contract recommendation movement is not a valid M2 comparison. |

Existing M2 runs already reject a changed policy fingerprint. Preserve that safeguard. A v0.2 baseline must continue to reassess under its pinned v0.2 policy or become stale; it must never generate a four-gate successor.

### 7.4 Frozen and historical artifacts

- Do not edit evaluation portfolio JSON/Markdown, run outputs, manifests, hashes, or recorded conclusions.
- Do not recalculate frozen recommendations under the successor.
- Frozen-boundary tests continue to hash the same files.
- New successor evaluation, when authorised, uses a new cohort/run identity and explicitly states its policy, Phase 1 contract, Phase 5 schema, and Phase 6 schema.

## 8. Report and presentation surface map

The UI architecture and decision-first presentation rules remain unchanged. The content projections require version-aware vocabulary:

| Surface | Current coupling | Successor requirement |
|---|---|---|
| CLI JSON (`cli.py`) | Defaults to v0.2 and serializes legacy `ProcessAssessment`. | Keep legacy default through the first slice; require explicit v0.3 invocation. On cutover, expose contract/policy identity in output. |
| Assessment Results (`pages/results.py`) | Counts four modes; renders legacy gates, labels, priority, and next action. | Count derived outcomes; show the four target gates; display intervention and autonomy separately in technical detail. |
| Shared process flow (`components/process_flow.py`) | Prints raw recommendation mode. | Render derived outcome through version-aware labels. |
| Decision Package (`pages/decision_package.py`) | Uses legacy portfolio items, report sections, and mode-based tones. | Keep the page hierarchy; drive tone and copy from derived outcome and status, not a collapsed enum. |
| Decision narrative (`decision_narrative.py`) | Branches extensively on `RecommendationMode` for Results, Package, and report prologues. | Add a successor projection; never infer a negative fact from discovery or a non-evaluated gate. |
| Structured report model/content (`models/decision_support.py`, `decision_support/report.py`) | Counts four modes; has “AI opportunity,” investigation, and “not recommended” sections. | Version the report model/content and preserve 13 ordered sections with successor-safe IDs and titles. |
| Report view and HTML export (`report_view.py`, `report_html.py`) | Project legacy labels, gates, recommendation tokens, and the shared package narrative. | Dispatch by Phase 6 schema; keep identifiers and policy detail reachable in the technical layer. |
| Vocabulary (`labels.py`) | Maps four recommendation and legacy gate/status tokens. | Add version-aware direct vocabulary only; keep composed interpretation in narrative and all decision logic in the engine. |
| Decision Continuation Workspace (`application/decision_continuation.py`, `pages/decision_continuation.py`) | Stores recommendation strings and compares legacy gate maps. | Use a contract-discriminated view model. Do not compare unlike contracts as decision movement. |
| Gap Resolution M1 (`grw/*`, `pages/gap_resolution.py`) | Snapshots legacy mode/gates as a non-change proof. | Legacy-only until a successor proof schema is implemented. |
| M2 reassessment (`grw/m2/*`, `pages/reassessment.py`, `controlled_reassessment_report.py`) | Shows baseline/successor recommendation strings and legacy gate differences. | Same-contract successor fields and four-gate differences only; preserve baseline immutability. |
| Methodology disclosure | Contains hard-coded `decision_policy.v0.2` copy in structured report content. | Generate disclosure from policy identity/status; always say thresholds are provisional and not academically validated. |
| Assessments, Source, and Validate Process pages | Show workflow state or pre-decision inputs, not a recommendation contract. | No semantic redesign. Only accept additive contract-selection/status copy if later required by workspace pinning. |

`labels.py` remains vocabulary-only, and `decision_narrative.py` remains a pure presentation projection. No assessment logic may move into Streamlit or report code.

### 8.1 The 13 persisted report sections

`phase6-v0.1` requires exactly the following ordered sections. `phase6-v0.2` should preserve the count and order but version the four AI-assumption-heavy IDs/titles rather than silently changing what the legacy IDs mean.

| Order | Current section ID/title | Successor treatment |
|---:|---|---|
| 1 | `executive-summary` — Executive summary | Keep ID; summarize decision status and derived outcomes. |
| 2 | `process-assessed` — Process assessed | Keep unchanged. |
| 3 | `ai-opportunity-portfolio` — AI opportunity portfolio | Replace in v0.2 with `activity-decision-portfolio` — Activity decision portfolio; include every activity and outcome. |
| 4 | `highest-priority-opportunities` — Highest-priority opportunities | Replace in v0.2 with `highest-priority-ai-opportunities`; include only complete AI outcomes with a score. |
| 5 | `requires-further-investigation` — Opportunities requiring further investigation | Replace in v0.2 with `discovery-required`; list typed blocking questions without implying a negative AI finding. |
| 6 | `ai-use-not-recommended` — AI use not recommended | Replace in v0.2 with `other-interventions-and-no-change`; distinguish conventional automation, process improvement, keep human-led, and no change. |
| 7 | `proposed-future-state-workflow` — Proposed future-state workflow | Keep structure and “proposed/not deployed” disclaimer; project the selected intervention and autonomy ceiling separately. |
| 8 | `human-roles-and-controls` — Human roles and controls | Keep; derive controls from Gate 4 only where it was evaluated. |
| 9 | `risks-and-governance` — Risks and governance considerations | Keep; never claim missing Gate 4 evidence was evaluated on a non-AI path. |
| 10 | `adoption-roadmap` — Adoption roadmap | Keep existing decision-support boundary and planning-origin labels; do not turn it into AEL execution. |
| 11 | `missing-information` — Missing information | Keep; separate decision-blocking gaps from preserved non-material unknowns. |
| 12 | `methodology-and-policy-disclosure` — Methodology and policy disclosure | Keep; disclose framework, contract, policy identity/fingerprint, and provisional status. |
| 13 | `evidence-and-traceability-appendix` — Evidence and traceability appendix | Keep; expose gate-material evidence, capability-signal lineage, and non-evaluated gates. |

## 9. Decision-ready resolution of O-001 through O-006

### O-001 — Gate 1 negative result

Options:

1. **Recommended: add `NO_CHANGE_JUSTIFIED` as a change disposition and derived outcome.** Consequence: seven customer outcomes, but no false claim that the current activity is human-led. Gate 3 and Gate 4 are correctly not evaluated.
2. Fold it into `KEEP_HUMAN_LED`. Consequence: simpler vocabulary, but semantically false for already automated, system-led, or outsourced work.
3. Store only a reason under another intervention. Consequence: the primary decision becomes dependent on prose and is harder to query, test, migrate, and compare.

### O-002 — Intervention and autonomy fields

Options:

1. **Recommended: separate `intervention_family` and `autonomy_ceiling`, with a derived `outcome_code`.** Consequence: schema/report migration is required, but Gate 3 and Gate 4 remain independently auditable and invalid combinations can be rejected.
2. Expand one enum to every intervention/autonomy combination. Consequence: combinatorial growth, duplicated semantics, and continued conflation of selection and safety constraint.
3. Keep the four legacy modes and add reason codes. Consequence: cannot represent conventional automation, process improvement, no change, and human-led outcomes honestly.

### O-003 — Backward compatibility

Options:

1. **Recommended: parallel versioned contracts with workspace pinning and schema-version adapter dispatch.** Consequence: more explicit loaders/models, but legacy rows, reports, hashes, and M2 baselines remain readable and honest.
2. In-place enum/policy/schema change. Consequence: rejected; old JSON may fail validation or appear to mean something it never meant.
3. One permissive union without workspace pinning. Consequence: reads may work, but reset/reassessment can silently switch policy and create mixed chains.

### O-004 — `strategic_criticality`

Options:

1. **Recommended: keep it out of framework v0.1 and allow strategic considerations only in `business_value.rationale`.** Consequence: no extraction/review/schema expansion; strategic claims remain evidence-traceable without becoming a twelfth scored input.
2. Add a twelfth dimension. Consequence: requires new extraction, review, policy, persistence, reporting, fixtures, and validation work with no adopted scale.
3. Add an untyped Gate 1 override. Consequence: rejected; it would weaken deterministic auditability.

### O-005 — Process improvement versus discovery

Options:

1. **Recommended: evidence sufficiency has precedence; only a sufficiently evidenced known readiness failure can yield `PROCESS_IMPROVEMENT_FIRST`.** Consequence: more discovery outcomes where evidence is weak, but no missing fact is mistaken for a low fact.
2. Treat all low/unknown readiness as process improvement. Consequence: invents a diagnosis and violates unknown preservation.
3. Treat all low/unknown readiness as discovery. Consequence: discards a valid decision when evidence clearly proves a readiness blocker.

### O-006 — Implementation complexity

Options:

1. **Recommended: explicit dual role—Gate 2 readiness ceiling plus post-decision priority component.** Consequence: high, evidenced infeasibility can stop an intervention decision at readiness; for eligible AI outcomes, lower complexity still improves prioritisation. It never silently ranks Gate 3 candidates.
2. Priority only, as in v0.2. Consequence: Gate 2 can call an activity ready even when implementation is recorded as currently infeasible.
3. Gate 3 ranking only. Consequence: conflates readiness with intervention selection and weakens the stated Gate 2 input map.
4. Hard Gate 2 role only. Consequence: loses the current transparent effort/priority influence among viable AI opportunities.

## 10. Recommended versioning and compatibility strategy

Recommended identities:

| Layer | Legacy | Successor |
|---|---|---|
| Framework | implicit/current | `four-gate-framework.v0.1` |
| Decision policy | `decision_policy.v0.2` / `0.2.0` | `decision_policy.v0.3` / `0.3.0` |
| Phase 1 output contract | `phase1-v0.3` | `phase1-v0.4` |
| Integrated assessment artifact | `phase5-v0.1` | `phase5-v0.2` |
| Decision package artifact | `phase6-v0.1` | `phase6-v0.2` |
| GRW M1 artifacts | `grw-m1-v0.1` | legacy-only initially; successor version deferred until a four-gate gap route is authorised |
| M2 reassessment artifacts | `grw-m2-m1-v0.1` | versioned successor family only after same-contract four-gate reassessment is authorised |
| Workspace database | migrations 1–3 | additive migration 4 for contract pinning; no artifact rewrite |

Rules:

- Policy IDs, schema versions, and fingerprints are stored, rendered, and tested together.
- Loaders reject unknown versions; they do not fall back to the newest model.
- Serializers validate against the exact schema selected by artifact version.
- Parent chains may contain unchanged Phase 2–4 artifacts plus either the complete legacy Phase 5–6 pair or complete successor pair. A mixed Phase 5/Phase 6 contract is invalid.
- Existing assessments are pinned to legacy during migration. The new default changes only in a separately approved release step.
- Writable databases receive migration 4 and a stored legacy backfill; supported frozen migration-1–3 databases remain byte-for-byte unchanged and receive a virtual legacy pin only while being read.
- Failure payloads are versioned with their integration schema as well as success payloads.
- No compatibility adapter writes a converted legacy artifact back to SQLite.

## 11. Smallest vertical implementation slice

The first implementation slice should prove the deterministic four-gate domain contract without touching application defaults, SQLite, reports, Streamlit, GRW, M2, or frozen evaluation.

### Slice 1 deliverable

Given an approved `BusinessProcess` already satisfying the unchanged input model and an explicitly loaded v0.3 policy, produce one validated `FourGateProcessAssessment` with:

- exactly four ordered results per activity;
- the typed output fields in section 3;
- path-specific discovery stops;
- all seven derived outcomes reachable in tests;
- preserved criterion/accountability values and evidence lineage;
- deterministic, complete priority behavior for complete AI outcomes only;
- deterministic repeatability.

The v0.2 engine and all existing tests must remain unchanged and passing. The slice is callable only through a new explicit API (and optionally `--policy config/decision_policy.v0.3.json --contract phase1-v0.4`); it is not the workspace default.

### Exact files likely to change in Slice 1

Prefer additive files to protect the legacy engine:

- add `config/decision_policy.v0.3.json`;
- add `src/ai_adoption_engine/models/four_gate_assessment.py`;
- add `src/ai_adoption_engine/decision/four_gate_policy.py`;
- add `src/ai_adoption_engine/decision/four_gate_gates.py`;
- add `src/ai_adoption_engine/decision/four_gate_engine.py`;
- minimally extend `src/ai_adoption_engine/models/enums.py` only for shared successor enums, or keep them in the new model module;
- minimally extend `src/ai_adoption_engine/cli.py` only if explicit contract selection is included;
- add `tests/unit/test_four_gate_policy.py`;
- add `tests/unit/test_four_gate_gates.py`;
- add `tests/unit/test_four_gate_engine.py`;
- add a v0.2 regression assertion to `tests/unit/test_policy.py` or `tests/unit/test_engine.py` only if needed.

Do not edit `decision/gates.py`, reinterpret `RecommendationMode`, or broaden the legacy `DecisionPolicy` validator to accept successor keys.

### Later authorised slices

1. Phase 5 successor integration and traceability (`models/integrated_assessment.py`, `application/assessment.py`, fingerprints, contract tests).
2. Phase 6 successor package and report-domain models (`models/decision_support.py`, `decision_support/*`) without presentation changes.
3. Persistence version dispatch and workspace contract pinning (`workspace/models.py`, `workspace/service.py`, `persistence/migrations.py`, `persistence/serialization.py`, `persistence/sqlite.py`).
4. Version-aware decision-first UI/report projection (`presentation/labels.py`, `decision_narrative.py`, `report_view.py`, `report_html.py`, results/package/process-flow pages).
5. Successor GRW/DCW/M2 contracts and same-contract reassessment comparison.
6. Separately governed successor evaluation; never modify the frozen v0.2 portfolio.

## 12. Targeted acceptance tests

### Slice 1 domain tests

1. Missing activity evidence stops at Gate 1 with discovery; Gates 2–4 are not evaluated.
2. Unknown, low-confidence inferred, and unreferenced material input each produce a typed discovery gap before numeric evaluation.
3. Low, sufficiently evidenced business value produces `NO_CHANGE_JUSTIFIED`, not human-led and not discovery.
4. Known low data readiness produces `PROCESS_IMPROVEMENT_FIRST`; the same numeric value without sufficient evidence produces discovery.
5. Known implementation complexity `5` produces process improvement under the provisional readiness ceiling.
6. High conventional fit selects conventional automation before AI.
7. Low AI fit and low conventional fit selects keep human-led.
8. AI fit above threshold plus one sufficiently evidenced true signal maps a stable concrete capability and permits AI selection; the same signal with insufficient evidence produces Gate 3 discovery.
9. AI fit above threshold with no mapped capability and unresolved capability signals produces discovery; ten sufficiently evidenced false signals produce keep human-led.
10. `WORKFLOW_AUTOMATION` does not bypass the conventional-automation precedence rule.
11. AI selection plus unacceptable residual risk yields `AI_NOT_PERMITTED` and derived keep human-led.
12. AI selection plus judgement/accountability/risk constraint yields AI-assisted work.
13. AI selection meeting every strict threshold yields AI automation.
14. Missing Gate 4 evidence does not block a conventional or human-led path because Gate 4 is not material there.
15. Every valid row in the closed field-combination table validates; nearby invalid combinations fail validation.
16. Priority exists and is complete only for complete AI automation/assisted results; every other successor result marks priority `NOT_APPLICABLE`.
17. Same inputs and policy produce byte-equivalent semantic JSON.
18. Existing v0.2 policy, capability, gate, engine, and scoring tests remain green with unchanged expected outputs.

### Contract and integration tests for later slices

- Phase 5 preserves every criterion, accountability field, evidence trace, policy fingerprint, and ordered step exactly once.
- Phase 6 accepts exactly the gate set for its declared contract and rejects mixed legacy/successor payloads.
- Serialization reads existing `phase5-v0.1`/`phase6-v0.1` rows and new v0.2 rows through exact version adapters.
- Existing rows in writable databases backfill to `phase1-v0.3`; new workspaces pin the selected contract; the pin cannot change after assessment begins.
- A frozen migration-1–3 workspace opens read-only with a virtual `phase1-v0.3` pin after migration 4 exists in the application; no file bytes, migration rows, artifacts, or hashes change.
- Reset and package regeneration retain the workspace's pinned contract.
- Legacy package pages and HTML remain snapshot/semantics equivalent.
- Successor Results, Decision Package, and HTML use the same derived outcome and never turn discovery into a negative factual claim.
- The technical layer exposes contract, policy, gate, intervention, autonomy, evidence, and fingerprint details.
- GRW non-change proofs compare like contracts only.
- M2 refuses cross-contract baseline/successor comparisons and preserves the original package and hashes.
- Phase 5/6/7 architecture tests continue to prevent policy logic in orchestration, persistence, and presentation.
- Frozen portfolio manifest/hash tests remain unchanged and pass.

Relevant existing test families to extend, not rewrite:

| Family | Current tests to preserve/extend | Successor focus |
|---|---|---|
| Input and output models | `tests/unit/test_models.py`, `test_candidate_process_models.py`, `test_capabilities.py` | Closed successor combinations, unknown preservation, signal provenance, stable deterministic mapping. |
| Policy, gates, engine, scoring | `tests/unit/test_policy.py`, `test_gates.py`, `test_engine.py`, `test_scoring.py`, `test_gate_wording_consistency.py` | All gate paths/outcomes, evidence precedence, threshold boundaries, priority eligibility, deterministic wording/serialization, untouched v0.2 expectations. |
| Phase 5 orchestration and fingerprints | `tests/unit/test_assessment_orchestration.py`, `test_assessment_fingerprints.py`, `tests/integration/test_integrated_assessment.py`, `test_human_review.py` | Explicit contract selection, policy fingerprint, complete reviewed-input traceability, approval boundary. |
| Phase 6 package domain | `tests/unit/test_decision_support_package.py`, `test_decision_support_governance.py`, `tests/integration/test_decision_support_pipeline.py` | Version-matched typed decisions, all 13 successor sections, gaps, future-state/control semantics. |
| Main persistence/workspace | `tests/unit/test_phase7_persistence.py`, `tests/integration/test_phase7_offline_workspace.py`, `test_f1_frozen_workspace_protection.py` | Exact schema adapter dispatch, immutable contract pin, reset/regeneration behavior, no legacy payload rewrite. |
| Results/package/report presentation | `tests/unit/test_decision_narrative.py`, `test_report_decision_first.py`, `test_phase7_demo_and_report.py`, `tests/ui/test_results_decision_first.py`, `test_decision_package_decision_first.py`, `test_portfolio_v1_release_journey.py` | Version-aware vocabulary and counts, discovery-safe copy, identical app/export story, preserved legacy snapshots. |
| Decision continuation | `tests/unit/test_decision_continuation.py`, `tests/ui/test_decision_continuation_decision_first.py`, `test_decision_continuation_ui.py`, `tests/integration/test_dcw_p1.py` | Contract-discriminated views and refusal to present cross-contract movement as a like-for-like change. |
| GRW M1 | `tests/unit/test_grw_models.py`, `test_grw_service.py`, `tests/integration/test_grw_m1_lifecycle.py`, `tests/ui/test_grw_m1.py`, `test_grw_m1_decision_clear.py` | Legacy proof unchanged; later successor proof snapshots typed fields and blocking gaps. |
| M2 reassessment | `tests/unit/test_grw_m2_models.py`, `test_grw_m2_policy_instrument.py`, `test_grw_m2_projection_comparison.py`, `test_grw_m2_service.py`, `test_controlled_reassessment_report.py`, `tests/integration/test_grw_m2_m1_lifecycle.py`, `tests/ui/test_grw_m2.py`, `test_reassessment_decision_clear.py` | Same-contract enforcement, successor Gate 2 reference, versioned comparison/report, baseline immutability. |
| Architecture boundaries | `tests/architecture/test_phase5_boundaries.py`, `test_phase6_boundaries.py`, `test_phase7_boundaries.py`, `test_dcw_p1_boundaries.py`, `test_grw_m1_boundaries.py`, `test_grw_m2_boundaries.py` | No policy logic in orchestration, persistence, continuation, GRW, report, or UI; additive successor modules do not loosen legacy boundaries. |
| Frozen evaluation and release behavior | `tests/architecture/test_phase8_portfolio_boundaries.py`, `tests/integration/test_phase8_portfolio_*`, `test_phase8_development_validation.py`, `test_phase8_primary_annotation_app.py` | Frozen hashes/manifests/results remain unchanged; any successor evaluation uses a new governed cohort and explicit contract identity. |

## 13. Migration risks and controls

| Risk | Control |
|---|---|
| Legacy JSON validates as a successor and changes apparent meaning. | Exact schema-version adapter dispatch; no fallback and no write-back conversion. |
| New default silently reassesses an old workspace. | Persisted decision-contract pin, backfilled in writable databases to legacy and immutable after assessment begins. |
| Adding migration 4 makes a frozen migration-1–3 database unreadable or attempts to mutate it. | Support the exact historical schema through a read-only legacy adapter with a virtual `phase1-v0.3` pin; never run migration 4 on a protected path. |
| Assessment idempotency returns a completed v0.2 artifact for a successor request. | Include contract version and policy fingerprint in assessment-operation idempotency material in addition to the approved artifact identity. |
| Discovery is shown as evidence against AI. | Dedicated `decision_status`, `BLOCKED_BY_EVIDENCE`, typed gaps, and copy tests. |
| Process improvement is emitted from missing facts. | Evidence checks precede rules; schema requires evidenced readiness decision codes. |
| Gate 3 and Gate 4 become conflated again in reports. | Separate fields plus derived outcome and consistent view-model tests. |
| `DO_NOT_RECOMMEND` history is falsely decomposed. | Never auto-map stored legacy outcomes. |
| Mixed Phase 5/6 or baseline/successor contracts enter persistence. | Parent-chain contract validation and same-contract M2 guard. |
| Report copy hard-codes v0.2 or raw tokens. | Policy-driven disclosure and version-aware vocabulary; preserve technical details behind the canonical control. |
| Threshold carry-over is described as validated. | Keep `PROVISIONAL — NOT YET ACADEMICALLY VALIDATED` and add explicit continuity disclosures/tests. |
| New logic leaks into UI, Phase 5, Phase 6, or persistence. | Existing architecture boundaries plus successor-specific boundary tests. |
| Frozen evaluation is accidentally regenerated. | No in-place evaluation writes; unchanged hash/manifest tests. |
| M2 data-readiness route points to legacy `technical_fit`. | Keep legacy schema; introduce a new successor gate reference only in a versioned M2 contract. |

## 14. Explicit non-scope

This design does not authorise or claim:

- production-code, policy, schema, persistence, database, UI, report, GRW, M2, or test implementation;
- modification of `decision_policy.v0.2` or its behavior;
- threshold, weight, predictive-accuracy, recommendation-accuracy, ROI, causal-impact, deployment-readiness, or academic-validation claims;
- retroactive conversion or rewrite of persisted assessments, reports, frozen evaluation artifacts, manifests, or historical conclusions;
- a twelfth `strategic_criticality` dimension;
- LLM judgement in the deterministic decision engine;
- implementation, piloting, deployment, operational monitoring, or the Adoption Execution Layer;
- authentication, tenancy, enterprise integrations, hosted commercialisation, or unrelated reliability work;
- a Validate Process redesign release, push, or relabelling.

## 15. Approval checklist before code

Before Slice 1 is authorised, record approval or amendment of these recommendations in `02_DECISIONS.md`:

- [ ] `NO_CHANGE_JUSTIFIED` is a separate Gate 1 disposition/outcome.
- [ ] Intervention and autonomy are separate typed fields with a derived outcome.
- [ ] The parallel version identifiers and no-conversion compatibility rule are accepted.
- [ ] `strategic_criticality` remains out of framework v0.1.
- [ ] Discovery has precedence over substantive rules; process improvement requires sufficient evidence.
- [ ] Implementation complexity has the explicit Gate 2 plus priority dual role.
- [ ] Capability signals remain provenance-aware deterministic inputs; AI selection requires one sufficiently supported mapped capability and unresolved mapping produces discovery only when needed on that path.
- [ ] The provisional carry-forward thresholds and new complexity ceiling are acceptable for an unvalidated successor policy draft.
- [ ] Slice 1 remains explicit/persistence-free and does not change the production default.

Only after those decisions are recorded should a separate implementation task create or modify production artifacts.
