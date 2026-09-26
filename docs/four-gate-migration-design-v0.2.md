# Four-Gate Migration Design v0.2

Status: **DECISION-READY SUCCESSOR DESIGN — NOT IMPLEMENTED**  
Date: **2026-09-03**  
Supersedes for design review: `docs/four-gate-migration-design-v0.1.md`; v0.1 remains unchanged as the prior design record.  
Scope: successor decision contract only. This document makes no production-code, test, configuration, schema, database, UI, canonical-memory, or frozen-artifact change.

## 1. Executive recommendation

Implement the four-gate framework as a versioned successor contract beside the shipped v0.2 contract.

The successor should:

1. preserve every legacy artifact payload JSON document, payload hash, recorded historical outcome, and protected frozen-workspace file unchanged;
2. permit writable databases to receive only additive migration-4 schema and contract-pin metadata, without rewriting legacy artifact payloads or reinterpreting legacy outcomes;
3. introduce `decision_policy.v0.3`, `phase1-v0.4`, `phase5-v0.2`, and `phase6-v0.2` as recommended successor identifiers;
4. represent decision status, Gate 1 change disposition, Gate 2 readiness disposition, Gate 3 selected candidate intervention, and Gate 4 autonomy ceiling separately, then derive one final customer outcome;
5. evaluate evidence only when it can alter the active decision path;
6. allow a sufficiently evidenced Gate 2 blocker to produce `PROCESS_IMPROVEMENT_FIRST` without requiring unrelated readiness-profile evidence;
7. preserve `DISCOVERY_REQUIRED` for material uncertainty and never infer process improvement from missing information;
8. let Gate 4 reject an AI candidate with `AI_NOT_PERMITTED`, producing the single final outcome `KEEP_HUMAN_LED`;
9. begin any later implementation with an explicitly invoked, persistence-free domain slice while the application default remains v0.2.

This document recommends decision-ready resolutions for O-001 through O-006. They remain proposals until explicitly approved and recorded in canonical project memory.

## 2. Authority, verification basis, and current/target conflict

Canonical target intent is defined by `00_PROJECT_CONTEXT.md`, `01_FRAMEWORK_SPEC.md`, and adopted entries in `02_DECISIONS.md`. Implemented truth remains the current code and `decision_policy.v0.2`, summarized in `03_CURRENT_STATE.md`. `04_CODEX_HANDOFF.md` authorizes design only.

The expected conflict remains visible:

- production evaluates `evidence_sufficiency -> technical_fit -> business_value -> risk_and_autonomy`;
- production returns `AUTOMATE`, `AUGMENT`, `INVESTIGATE_FURTHER`, or `DO_NOT_RECOMMEND`;
- the target evaluates Should We Change It? -> Is It Ready? -> What Is the Best Intervention? -> How Much Autonomy Is Safe?;
- current Phase 5, Phase 6, persistence, reports, DCW, GRW, M2, and frozen evaluations encode legacy types and meanings.

This design was checked on branch `codex/validate-process-workspace` at HEAD `d200a6527b87d7b3ef9eaa8b25767fa086c7ff02`. The working tree was already dirty and unrelated work remains untouched.

The retained contract inventory comes from v0.1 and was verified against the current policy, decision models/engine, capability mapper, Phase 5/6 contracts, workspace and SQLite layers, GRW/DCW/M2 contracts, report/presentation projections, and their directly coupled test families. This is design evidence, not evidence that the successor is implemented or validated.

## 3. Recommended successor output contract

### 3.1 Process envelope

`FourGateProcessAssessment` should contain:

- `process_id` and `process_name`;
- `framework_id = four-gate-framework.v0.1`;
- `framework_version = 0.1`;
- `decision_contract_version = phase1-v0.4`;
- `policy_id`, `policy_version`, and `policy_status`;
- ordered activity assessments.

When Phase 5 later embeds this result, its separate policy reference must add the canonical policy fingerprint and verify every duplicated policy identity field.

### 3.2 Typed activity decision

| Field | Recommended values | Contract meaning |
|---|---|---|
| `decision_status` | `COMPLETE`, `DISCOVERY_REQUIRED` | Whether a substantive final decision was reached or the active path stopped on material evidence. |
| `change_disposition` | `CHANGE_JUSTIFIED`, `NO_CHANGE_JUSTIFIED`, `NOT_DETERMINED` | Gate 1 answer. |
| `readiness_disposition` | `READY_FOR_INTERVENTION_SELECTION`, `PROCESS_IMPROVEMENT_FIRST`, `NOT_EVALUATED`, `NOT_DETERMINED` | Gate 2 answer. This field carries the readiness stop; it is not a Gate 3 selection. |
| `selected_intervention_family` | `AI`, `CONVENTIONAL_AUTOMATION`, `KEEP_HUMAN_LED`, `NOT_APPLICABLE`, `NOT_DETERMINED` | Candidate selected by Gate 3. The name deliberately does not imply final approval before Gate 4. |
| `autonomy_ceiling` | `AI_AUTOMATION`, `AI_ASSISTED`, `AI_NOT_PERMITTED`, `NOT_APPLICABLE`, `NOT_DETERMINED` | Gate 4 maximum safe AI role. |
| `outcome_code` | derived values below | The single final customer outcome; read-only and never independently writable. |
| `gate_results` | exactly four ordered successor gate results | Complete audit path, including not-evaluated gates. |
| `blocking_gaps` | typed evidence gaps | Non-empty exactly when `decision_status=DISCOVERY_REQUIRED`. |
| `capabilities` | existing ordered `Capability` values | Deterministic projection of sufficiently supported capability signals. |
| `criteria`, `human_accountability` | successor provenance records | Preserve value, knowledge state, rationale, evidence IDs, confidence, and actual materiality. |
| `priority_status` | `COMPLETE`, `INCOMPLETE`, `NOT_APPLICABLE` | Priority may be incomplete when non-decision context such as repetition remains insufficient. |
| `priority`, `priority_missing_criteria` | existing score shape or `null`; missing criterion list | Only complete AI automation/assisted outcomes are eligible; insufficient scoring-only inputs do not change the decision. |
| `reasoning`, `evidence` | deterministic rationales and referenced evidence | Preserve explainability without presenting context as decision evidence. |

### 3.3 Closed output-field combinations

Only these semantic combinations are valid:

| Active path/final result | Status | Change | Readiness | Selected candidate | Autonomy | Derived outcome |
|---|---|---|---|---|---|---|
| Discovery at Gate 1 | `DISCOVERY_REQUIRED` | `NOT_DETERMINED` | `NOT_EVALUATED` | `NOT_DETERMINED` | `NOT_DETERMINED` | `DISCOVERY_REQUIRED` |
| Gate 1 no-change stop | `COMPLETE` | `NO_CHANGE_JUSTIFIED` | `NOT_EVALUATED` | `NOT_APPLICABLE` | `NOT_APPLICABLE` | `NO_CHANGE_JUSTIFIED` |
| Discovery at Gate 2 | `DISCOVERY_REQUIRED` | `CHANGE_JUSTIFIED` | `NOT_DETERMINED` | `NOT_DETERMINED` | `NOT_DETERMINED` | `DISCOVERY_REQUIRED` |
| Gate 2 readiness stop | `COMPLETE` | `CHANGE_JUSTIFIED` | `PROCESS_IMPROVEMENT_FIRST` | `NOT_APPLICABLE` | `NOT_APPLICABLE` | `PROCESS_IMPROVEMENT_FIRST` |
| Discovery at Gate 3 | `DISCOVERY_REQUIRED` | `CHANGE_JUSTIFIED` | `READY_FOR_INTERVENTION_SELECTION` | `NOT_DETERMINED` | `NOT_DETERMINED` | `DISCOVERY_REQUIRED` |
| Gate 3 conventional candidate | `COMPLETE` | `CHANGE_JUSTIFIED` | `READY_FOR_INTERVENTION_SELECTION` | `CONVENTIONAL_AUTOMATION` | `NOT_APPLICABLE` | `CONVENTIONAL_AUTOMATION` |
| Gate 3 human-led candidate | `COMPLETE` | `CHANGE_JUSTIFIED` | `READY_FOR_INTERVENTION_SELECTION` | `KEEP_HUMAN_LED` | `NOT_APPLICABLE` | `KEEP_HUMAN_LED` |
| Discovery at Gate 4 after AI selection | `DISCOVERY_REQUIRED` | `CHANGE_JUSTIFIED` | `READY_FOR_INTERVENTION_SELECTION` | `AI` | `NOT_DETERMINED` | `DISCOVERY_REQUIRED` |
| Gate 4 safety veto | `COMPLETE` | `CHANGE_JUSTIFIED` | `READY_FOR_INTERVENTION_SELECTION` | `AI` | `AI_NOT_PERMITTED` | `KEEP_HUMAN_LED` |
| Gate 4 assisted ceiling | `COMPLETE` | `CHANGE_JUSTIFIED` | `READY_FOR_INTERVENTION_SELECTION` | `AI` | `AI_ASSISTED` | `AI_ASSISTED_WORK` |
| Gate 4 automation ceiling | `COMPLETE` | `CHANGE_JUSTIFIED` | `READY_FOR_INTERVENTION_SELECTION` | `AI` | `AI_AUTOMATION` | `AI_AUTOMATION` |

Derived `outcome_code` precedence:

1. `decision_status == DISCOVERY_REQUIRED` -> `DISCOVERY_REQUIRED`.
2. `change_disposition == NO_CHANGE_JUSTIFIED` -> `NO_CHANGE_JUSTIFIED`.
3. `readiness_disposition == PROCESS_IMPROVEMENT_FIRST` -> `PROCESS_IMPROVEMENT_FIRST`.
4. `selected_intervention_family == CONVENTIONAL_AUTOMATION` -> `CONVENTIONAL_AUTOMATION`.
5. `selected_intervention_family == KEEP_HUMAN_LED` -> `KEEP_HUMAN_LED`.
6. `selected_intervention_family == AI` and `autonomy_ceiling == AI_AUTOMATION` -> `AI_AUTOMATION`.
7. `selected_intervention_family == AI` and `autonomy_ceiling == AI_ASSISTED` -> `AI_ASSISTED_WORK`.
8. `selected_intervention_family == AI` and `autonomy_ceiling == AI_NOT_PERMITTED` -> `KEEP_HUMAN_LED`.
9. Every other combination fails schema validation.

The safety-veto row records history without creating simultaneous recommendations: AI was the Gate 3 candidate, Gate 4 prohibited AI autonomy, and Keep Human-Led is the one final outcome.

### 3.4 Proposed seventh outcome amendment

`NO_CHANGE_JUSTIFIED` remains the recommended Gate 1 outcome because an unchanged activity may already be automated, system-led, or outsourced; `KEEP_HUMAN_LED` could be false.

This is a **proposed amendment**, not part of the currently canonical six-outcome target. It requires explicit approval of O-001 and a later authorized update to `01_FRAMEWORK_SPEC.md` and `02_DECISIONS.md` before implementation. Until then, the canonical target still contains six outcomes.

### 3.5 Gate result and evidence-gap contracts

Successor gate result fields:

| Field | Contract |
|---|---|
| `gate` | `SHOULD_WE_CHANGE`, `IS_IT_READY`, `BEST_INTERVENTION`, `SAFE_AUTONOMY` |
| `status` | `COMPLETED`, `COMPLETED_WITH_CONSTRAINTS`, `BLOCKED_BY_EVIDENCE`, `NOT_EVALUATED` |
| `decision_code` | Gate-specific deterministic result. |
| `rationale` | Non-empty explanation of the actual rule path. |
| `material_criteria` | Only criteria that could alter the result at the point evaluated. |
| `context_criteria` | Displayed readiness/priority context that did not control this decision. |
| `accountability_material` | Whether accountability affected this path. |
| `material_capability_signals` | Capability signals required to establish the selected AI candidate. |
| `evidence_ids` | Accepted evidence used by material rules. |
| `blocking_gaps` | Typed gaps only for `BLOCKED_BY_EVIDENCE`. |

Exactly four gate results are always returned in order. After a substantive terminal result or evidence stop, later gates are `NOT_EVALUATED` and identify the earlier deciding gate. A negative or constrained substantive answer is completed, not failed.

Each blocking gap contains:

- `field_name`;
- the gate where it became material;
- `problem_code`: `UNKNOWN`, `VALUE_MISSING`, `INFERRED_CONFIDENCE_TOO_LOW`, `EVIDENCE_REFERENCE_MISSING`, or `ACTIVITY_EVIDENCE_MISSING`;
- a deterministic blocking question;
- existing evidence IDs, if any, without implying sufficiency.

Unknown is never zero. Contextual or scoring-only unknowns are preserved but are not `blocking_gaps`.

## 4. Exact path-specific evidence algorithm

For each applicable gate:

1. Start from decisions already established by earlier gates.
2. Evaluate any sufficiently evidenced terminal rule whose result cannot be changed by remaining inputs.
3. If such a rule determines the path, return that substantive result and do not require unrelated evidence.
4. Otherwise identify only inputs that can still change the active decision.
5. Validate those inputs for value, knowledge state, inferred confidence, and required evidence reference.
6. If any is insufficient, return `DISCOVERY_REQUIRED`, mark the current gate `BLOCKED_BY_EVIDENCE`, and mark later gates `NOT_EVALUATED`.
7. Otherwise evaluate the next deterministic rule.

This is decision-path short-circuiting, not imputation. Known evidence may remove a question from the active path; missing information never proves a substantive blocker.

## 5. Exact gate semantics

### 5.1 Gate 1 — Should We Change It?

Decision-material input: `business_value`.

`repetition` may appear as context but has no approved rule that can override business value, so it cannot cause Gate 1 discovery.

Provisional rule carried from v0.2:

- insufficient business-value evidence -> `DISCOVERY_REQUIRED` at Gate 1;
- `business_value < minimum_business_value` -> `NO_CHANGE_JUSTIFIED`;
- otherwise -> `CHANGE_JUSTIFIED`.

The current threshold `2` may be inherited only as an explicitly provisional continuity value.

### 5.2 Gate 2 — Is It Ready?

Decision-material inputs:

- `data_readiness`;
- `implementation_complexity`.

Readiness-profile context, not Gate 2 blockers:

- `repetition` — also a priority input;
- `predictability` — also a priority input and conditionally material later at Gate 4;
- `ai_capability_fit` — conditionally material later at Gate 3.

Gate 2 algorithm:

1. Independently identify sufficiently evidenced known blockers:
   - `data_readiness < minimum_data_readiness`;
   - `implementation_complexity > maximum_implementation_complexity_for_readiness`.
2. If one or both known blockers exist, return `PROCESS_IMPROVEMENT_FIRST`, name every established blocker, and do not require evidence for the other Gate 2 input or readiness-profile context because none can change that final Gate 2 result.
3. If no blocker is established, both decision-material inputs are required to conclude readiness. Any insufficient one produces `DISCOVERY_REQUIRED` at Gate 2.
4. If both are sufficient and neither blocks, return `READY_FOR_INTERVENTION_SELECTION`.

Consequences:

- known low data readiness can produce Process Improvement First even when implementation complexity, repetition, predictability, or AI fit is unknown;
- known excessive implementation complexity can produce Process Improvement First even when data readiness or readiness-profile context is unknown;
- an unknown data-readiness or complexity value cannot itself produce Process Improvement First;
- missing repetition never causes Gate 2 discovery;
- missing predictability never causes Gate 2 discovery;
- missing AI capability fit never causes Gate 2 discovery.

The inherited data-readiness threshold `2` and proposed complexity ceiling `4` remain provisional and not academically validated.

### 5.3 Gate 3 — What Is the Best Intervention?

Gate 3 runs only after Gate 2 returns `READY_FOR_INTERVENTION_SELECTION`.

Rule order and dynamic materiality:

1. `conventional_solution_fit` is material first.
2. If its evidence is insufficient, return Gate 3 discovery.
3. If it meets `conventional_solution_fit_cutoff`, select `CONVENTIONAL_AUTOMATION`; do not require AI capability fit or capability-signal evidence.
4. Only after conventional automation is ruled out does `ai_capability_fit` become material.
5. If AI fit evidence is then insufficient, return Gate 3 discovery.
6. If AI fit is below `minimum_ai_capability_fit`, select `KEEP_HUMAN_LED`; capability signals cannot override the low fit and remain non-material.
7. If AI fit meets the threshold, require at least one sufficiently supported true capability signal to map a concrete capability.
8. If no capability maps because potentially relevant signals remain unresolved, return Gate 3 discovery with the blocking question “Which concrete AI capability applies to this activity?”.
9. If all capability signals are sufficiently evidenced false, select `KEEP_HUMAN_LED`.
10. If at least one sufficiently supported true signal maps, set `selected_intervention_family=AI` and continue to Gate 4.

Thus missing AI fit cannot block a sufficiently evidenced conventional solution. `WORKFLOW_AUTOMATION` remains a neutral taxonomy value and does not override conventional-automation precedence.

The current conventional cutoff `4` and AI-fit minimum `3` may be inherited only as provisional continuity values.

### 5.4 Gate 4 — How Much Autonomy Is Safe?

Gate 4 runs only for `selected_intervention_family=AI`.

Potential inputs:

- `residual_risk_with_human_oversight`;
- `human_judgement_requirement`;
- `risk_consequence`;
- `human_accountability_required`;
- validated Gate 2 `data_readiness`;
- `predictability`, only when it can still distinguish automation from assistance.

Rule order and dynamic materiality:

1. Residual risk is material first because it alone can veto the AI candidate. If insufficient, return Gate 4 discovery.
2. If `residual_risk_with_human_oversight >= unacceptable_residual_risk`, set `autonomy_ceiling=AI_NOT_PERMITTED` and derive `KEEP_HUMAN_LED`. Other Gate 4 evidence is not required because it cannot reverse the veto.
3. Otherwise inspect human judgement, risk consequence, human accountability, and the already known residual-risk value for assisted-work constraints.
4. If any sufficiently evidenced known constraint independently requires assistance, set `AI_ASSISTED`; insufficient peer inputs do not block because they cannot change that ceiling.
5. If no assistance constraint is established, insufficient judgement, risk, or accountability evidence produces Gate 4 discovery because each could still change the ceiling.
6. Evaluate the strict automation conditions already known from Gate 2 and Gate 4, excluding predictability. If any fails, set `AI_ASSISTED`; predictability is not material because it cannot restore automation.
7. Only if every other automation condition passes does predictability become decision-material. Insufficient predictability then produces Gate 4 discovery; a known value below the automation minimum yields `AI_ASSISTED`; a known value meeting it yields `AI_AUTOMATION`.

This preserves path-specific discovery. Predictability is Gate 2 context, but it becomes material only at Gate 4 and only while the automation-versus-assistance question remains open.

### 5.5 Discovery Required versus Process Improvement First

| Situation | Result |
|---|---|
| Material activity or Gate 1 evidence is insufficient. | `DISCOVERY_REQUIRED` |
| No Gate 2 blocker is established and a decision-material Gate 2 input is insufficient. | `DISCOVERY_REQUIRED` |
| A known, confidence-acceptable, traceable Gate 2 value satisfies a blocker rule. | `PROCESS_IMPROVEMENT_FIRST` |
| One Gate 2 blocker is established while another input is missing. | `PROCESS_IMPROVEMENT_FIRST`; the missing input is preserved but cannot change this path. |
| Conventional fit establishes conventional automation while AI fit is missing. | `CONVENTIONAL_AUTOMATION`; AI fit is not material. |
| Conventional automation is ruled out and AI fit is missing. | `DISCOVERY_REQUIRED` at Gate 3. |
| A non-material context or priority value is missing. | Continue; preserve the unknown and mark priority incomplete if applicable. |

Discovery means “the product cannot yet decide this active question.” Process Improvement First means “the product has enough evidence to decide that an established readiness blocker should be addressed first.” Neither implies AI suitability.

## 6. Complete current-to-successor mapping

### 6.1 Current gates

| Current gate | Current role | Successor mapping | Legacy treatment |
|---|---|---|---|
| `evidence_sufficiency` | Step evidence before legacy decision gates. | Cross-cutting, rule-path-specific precondition; activity evidence is checked at Gate 1. | Preserve as the historical fourth-name set; do not expose it as a fifth successor gate. |
| `technical_fit` | AI fit, conditional conventional fit, data readiness. | Data readiness -> Gate 2; conventional fit, AI fit, capability mapping -> ordered Gate 3 rules. | Never mechanically convert stored results. |
| `business_value` | Minimum-value gate after technical fit. | Gate 1, evaluated first. | Preserve historical order and rationale. |
| `risk_and_autonomy` | Risk, judgement, accountability, conditional predictability. | Gate 4 with ordered veto, assistance, and automation rules. | Preserve v0.2 result and rationale verbatim. |

### 6.2 Ten ordinal criteria plus accountability

| Input | Current role | Successor role | Decision materiality |
|---|---|---|---|
| `repetition` | Priority only. | Gate 2 readiness context; priority. | Never Gate 2 decision-material in v0.2 design; missing value cannot cause Gate 2 discovery. |
| `predictability` | Conditional legacy risk/autonomy; priority; automation eligibility. | Gate 2 context; priority; Gate 4 automation discriminator. | Material only on an AI path when all other automation conditions still pass. |
| `data_readiness` | Technical-fit minimum; priority; automation eligibility. | Gate 2 blocker/readiness; known value reused at Gate 4. | Gate 2 decision-material unless another established Gate 2 blocker already determines Process Improvement First. |
| `ai_capability_fit` | Technical-fit minimum; priority. | Gate 2 context; Gate 3 AI comparison. | Material only after conventional automation has been ruled out. |
| `human_judgement_requirement` | Legacy risk/autonomy. | Gate 4 assistance/automation ceiling. | Material on an AI path only while no earlier veto or independently sufficient assistance constraint has determined the ceiling. |
| `business_value` | Legacy business-value gate; priority. | Gate 1; priority. | Gate 1 decision-material. |
| `risk_consequence` | Legacy risk/autonomy; priority. | Gate 4 assistance/automation ceiling; priority. | Dynamic Gate 4 materiality as above. |
| `residual_risk_with_human_oversight` | Legacy risk/autonomy. | Gate 4 safety veto, then assistance/automation ceiling. | First material Gate 4 input on every AI path. |
| `implementation_complexity` | Priority only. | Gate 2 blocker/readiness; priority. | Gate 2 decision-material unless another established Gate 2 blocker already determines Process Improvement First. |
| `conventional_solution_fit` | Conditional legacy technical-fit rejection. | First Gate 3 comparison. | Material whenever Gate 3 is reached. |
| `human_accountability_required` | Separate Boolean/unknown field. | Gate 4 assistance/automation ceiling. | Remains separately typed; dynamic Gate 4 materiality, never converted to 0–5. |

All values retain knowledge state, rationale, evidence references, and inferred confidence. No twelfth assessment dimension is introduced.

### 6.3 Capability signals and mapped capabilities

The ten provenance-aware signals remain reviewed inputs beneath the dimensions:

| Signal | Deterministic mapped capability |
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

Preserve stable mapping order and each signal's value, knowledge state, rationale, evidence IDs, and confidence. Signals do not become scored dimensions. A language model never selects the capability. Phase 5 retains all signal traceability even when the signals are non-material on the selected path.

### 6.4 Current recommendation modes

| Legacy mode | Closest successor concept | Why no automatic conversion is valid |
|---|---|---|
| `AUTOMATE` | AI candidate + `AI_AUTOMATION` | Gate order and evidence materiality differ. |
| `AUGMENT` | AI candidate + `AI_ASSISTED` | New contract audits candidate selection separately from autonomy. |
| `INVESTIGATE_FURTHER` | Often `DISCOVERY_REQUIRED`; known low data readiness may become Process Improvement First. | Legacy combines insufficient evidence and known readiness failure. |
| `DO_NOT_RECOMMEND` | No change, conventional automation, keep human-led, or safety-vetoed AI. | Legacy collapses distinct reasons and outcomes. |

Historical values remain historical values. Any displayed “closest concept” is explanatory only and is never persisted as a converted successor record.

### 6.5 Current policy fields

| v0.2 field | Successor treatment |
|---|---|
| `policy_id`, `version`, `status`, `description` | New identity/version; retain provisional disclosure. |
| new `framework_id`, `framework_version`, `decision_contract_version` | Required and validated against the successor output envelope. |
| `scale.minimum`, `scale.maximum`, `scale.unknown_representation` | Retain 0–5 and null-plus-unknown semantics. |
| `scale.criteria` and every direction/meaning | Retain unless separately approved. |
| `evidence.minimum_inferred_confidence` | Retain. |
| `evidence.require_step_evidence_reference` | Retain for Gate 1 activity evidence. |
| `evidence.require_material_criterion_evidence_reference` | Retain; apply only to actually material criteria. |
| new `evidence.require_material_capability_signal_evidence_reference` | Recommended `true` when a signal is needed to establish an AI candidate. |
| `evidence.material_by_gate` | Replace static legacy interpretation with ordered unconditional material rules: Gate 1 business value; Gate 2 blocker inputs; Gate 3 conventional fit; Gate 4 residual risk. |
| `evidence.conditional_by_gate` | Encode AI fit/capability mapping after conventional precedence and Gate 4 assistance/predictability predicates. |
| new `evidence.context_by_gate` | Declare Gate 2 repetition, predictability, and AI fit as non-blocking readiness context until a later rule makes them material. |
| `minimum_business_value` | Gate 1. |
| `minimum_data_readiness` | Gate 2 blocker and Gate 4 strict automation fact. |
| `minimum_ai_capability_fit` | Gate 3 after conventional automation is ruled out. |
| `conventional_solution_fit_cutoff` | First Gate 3 rule. |
| `unacceptable_residual_risk` | First Gate 4 safety-veto rule. |
| `augment_human_judgement`, `augment_risk_consequence`, `augment_residual_risk` | Gate 4 independent assisted-work constraints. |
| `automate_minimum_predictability`, `automate_minimum_data_readiness` | Gate 4 strict automation test; predictability is checked last and only if still outcome-relevant. |
| `automate_maximum_human_judgement`, `automate_maximum_risk_consequence`, `automate_maximum_residual_risk` | Gate 4 strict automation test. |
| new `maximum_implementation_complexity_for_readiness` | Gate 2 blocker; proposed provisional value `4`. |
| `scoring.eligible_recommendations` | Replace with final-outcome predicate: complete `AI_AUTOMATION` or `AI_ASSISTED_WORK`. |
| `scoring.criteria` and every weight/direction | Preserve initially; insufficient scoring-only inputs produce incomplete priority, not discovery. |
| `scoring.bands.high_minimum`, `scoring.bands.medium_minimum` | Preserve `70`/`50` provisionally. |

Use a separate successor policy model or strict version-discriminated union. Do not loosen the legacy `DecisionPolicy` validator.

## 7. Persistence and compatibility contract

### 7.1 Exact preservation meaning

“Legacy preservation” means:

- legacy artifact `payload_json` remains unchanged;
- legacy artifact `payload_sha256` remains unchanged;
- recorded legacy recommendation modes, gate results, reports, and historical conclusions remain unchanged and are not reinterpreted;
- protected frozen-workspace files remain byte-for-byte unchanged;
- no compatibility adapter writes a converted legacy payload back to SQLite.

It does **not** mean every writable database file remains byte-for-byte unchanged. Writable databases may receive additive migration-4 schema and contract-pin metadata. Migration 4 must not rewrite legacy artifact payloads, recalculate their hashes, or relabel their outcomes.

### 7.2 Main workspace artifacts

| Artifact | Current contract | Successor action |
|---|---|---|
| `INGESTION_RESULT` | `phase2-v0.1` | Unchanged. |
| `CANDIDATE_EXTRACTION_RESULT` | `phase3-v0.1` | Unchanged; inputs/evidence remain. |
| `REVIEW_SESSION` | `phase4-v0.1` | Unchanged. |
| `APPROVED_REVIEW` | `phase4-v0.1` | Unchanged; explicit human approval remains mandatory. |
| `INTEGRATED_ASSESSMENT_RESULT` | `phase5-v0.1` embedding `phase1-v0.3` | Add `phase5-v0.2` embedding `phase1-v0.4`; retain exact v0.1 reader. |
| `DECISION_PACKAGE_RESULT` | `phase6-v0.1` | Add `phase6-v0.2`; retain exact v0.1 reader. |
| `GRW_EVIDENCE_SUBMISSION` | `grw-m1-v0.1` | Legacy-only initially; successor version only when a four-gate gap route is authorized. |
| `GRW_EVIDENCE_REVIEW` | `grw-m1-v0.1` with legacy non-change proof | Legacy-only initially; a later successor proof snapshots the typed successor decision. |

`phase1-v0.3` is metadata inside Phase 5 rather than a standalone workspace artifact. A successor trace replaces `recommendation_path` with paths for `decision_status`, `change_disposition`, `readiness_disposition`, `selected_intervention_family`, `autonomy_ceiling`, and derived `outcome_code`, while preserving gate, criterion, accountability, capability-signal, and evidence traces.

Serialization must dispatch by `(artifact_type, artifact_schema_version)`. Unknown versions fail closed. Phase 5 and Phase 6 contract families may not be mixed in one parent chain.

### 7.3 Writable assessment database migration

Recommended additive migration 4:

- add `decision_contract_version` to `assessments`;
- backfill writable existing assessment rows to `phase1-v0.3` as metadata only;
- require new assessment rows to pin an explicitly supported contract;
- prohibit pin changes after approval or any assessment artifact exists;
- select policy and engine from the immutable pin;
- include approved artifact identity, contract version, and policy fingerprint in assessment-operation idempotency material.

Migration 4 may alter writable database schema bytes and assessment metadata. It must not update `assessment_artifacts.payload_json`, `payload_sha256`, recorded results, or historical report content.

### 7.4 Protected frozen database compatibility

Protected migration-1–3 frozen databases are never migrated. The application must:

- recognize the exact migration-1–3 schema as a supported historical read-only schema;
- supply a virtual `phase1-v0.3` decision-contract pin only in the legacy read adapter;
- make no file-byte, schema, migration-row, payload, hash, active-pointer, or outcome change;
- retain write refusal and integrity verification.

The current protected-workspace guard compares the applied migration set with the application's full migration list. A later implementation must update that guard to accept the supported historical read-only schema before adding migration 4, or frozen databases would become unreadable.

### 7.5 M2 controlled reassessment artifacts

All current M2 artifacts use `grw-m2-m1-v0.1` and remain unchanged.

| M2 artifact | Current coupling | Successor treatment |
|---|---|---|
| `RUN_MANIFEST` | Pins baseline package and policy. | Add contract identity only in a new schema family; never mix families. |
| `DOCUMENT_SUBMISSION`, `EVIDENCE_REVIEW` | Evidence-side records. | Keep payload meaning; version if referencing a successor gap. |
| `DATA_READINESS_RESOLUTION` | Hard-codes `technical_fit`. | Legacy unchanged; successor version permits `IS_IT_READY`. |
| `REASSESSMENT_REQUEST`, `REASSESSMENT_APPROVAL` | Pin baseline and approved change. | Successor versions also pin four-gate contract/fingerprint. |
| `SUCCESSOR_APPROVED_REVIEW` | One-field approved projection. | Concept retained; contract identity pinned. |
| `SUCCESSOR_INTEGRATED_ASSESSMENT` | Embeds Phase 5 legacy success. | New version embeds `phase5-v0.2` only for a four-gate baseline. |
| `SUCCESSOR_DECISION_PACKAGE` | Embeds Phase 6 legacy package. | New version embeds `phase6-v0.2` only. |
| `BASELINE_SUCCESSOR_COMPARISON` | Compares legacy modes/gates. | New version compares same-contract typed fields and four gates only. |

A `decision_policy.v0.2` baseline reassesses under its pinned legacy contract or becomes stale. It never generates a four-gate successor. M2 serialization must also dispatch by artifact type plus schema version.

### 7.6 Frozen and historical evaluation artifacts

- Do not edit or regenerate portfolio JSON/Markdown, run outputs, manifests, hashes, databases, or conclusions.
- Do not recalculate frozen recommendations under the successor.
- Existing hash/boundary tests continue to protect the same files.
- Any later successor evaluation uses a new governed cohort/run identity and explicit framework, policy, Phase 1, Phase 5, and Phase 6 versions.

## 8. Report and presentation contract

The UI architecture and decision-first presentation rules remain unchanged. Only version-aware content projections change in later authorized slices.

| Surface | Current coupling | Successor requirement |
|---|---|---|
| CLI JSON (`cli.py`) | Defaults to v0.2 legacy assessment. | Keep legacy default through Slice 1; later explicit contract selection only. |
| Results (`pages/results.py`) | Counts legacy modes and gates. | Count derived outcomes; show four gates; distinguish context from blocking material evidence. |
| Process flow (`components/process_flow.py`) | Prints raw legacy mode. | Render the one derived outcome through version-aware labels. |
| Decision Package (`pages/decision_package.py`) | Uses legacy portfolio/report sections and mode tones. | Drive tone/copy from decision status and derived outcome. |
| Decision narrative (`decision_narrative.py`) | Branches on `RecommendationMode`. | Add successor projection; never infer negative facts from discovery or contextual unknowns. |
| Structured report (`models/decision_support.py`, `decision_support/report.py`) | Four-mode counts and AI-centric sections. | Version model/content; retain 13-section order with successor-safe IDs/titles. |
| Report view/HTML (`report_view.py`, `report_html.py`) | Projects legacy labels and narrative. | Dispatch by Phase 6 schema and expose typed technical detail. |
| Vocabulary (`labels.py`) | Legacy mode/gate labels. | Add direct successor vocabulary only; keep interpretation in narrative and decisions in engine. |
| DCW (`application/decision_continuation.py`, `pages/decision_continuation.py`) | Stores/compares legacy recommendation strings and gates. | Contract-discriminated view; never present cross-contract movement as like-for-like. |
| GRW M1 (`grw/*`, gap-resolution page) | Legacy non-change proof. | Legacy-only until a versioned successor proof exists. |
| M2 reassessment and controlled report (`pages/reassessment.py`, `controlled_reassessment_report.py`) | Legacy baseline/successor mode and gate comparison. | Same-contract typed comparison only; preserve baseline immutability. |
| Assessments, Source, Validate Process | Pre-decision workflow/input surfaces. | No semantic redesign; only later additive contract-pin copy if required. |

### 8.1 Reporting path-specific materiality

Reports must:

- list only active `blocking_gaps` under Discovery Required;
- preserve unknown repetition, predictability, AI fit, or peer inputs as contextual/priority gaps when they could not change the reached outcome;
- show Process Improvement First only with the sufficiently evidenced blocker(s) that determined it;
- show conventional automation without implying that missing AI fit blocked the decision;
- show `priority_status=INCOMPLETE` separately from decision status;
- for `selected_intervention_family=AI` plus `AI_NOT_PERMITTED`, say that AI was considered and selected as the Gate 3 candidate but rejected by the safety gate, with Keep Human-Led as the sole final recommendation;
- never display AI and Keep Human-Led as simultaneous final recommendations.

### 8.2 Thirteen persisted report sections

| Order | Legacy ID/title | Successor treatment |
|---:|---|---|
| 1 | `executive-summary` — Executive summary | Decision status and final derived outcomes. |
| 2 | `process-assessed` — Process assessed | Unchanged. |
| 3 | `ai-opportunity-portfolio` — AI opportunity portfolio | `activity-decision-portfolio`; every activity and final outcome. |
| 4 | `highest-priority-opportunities` | `highest-priority-ai-opportunities`; complete scored AI outcomes only. |
| 5 | `requires-further-investigation` | `discovery-required`; active blocking questions only. |
| 6 | `ai-use-not-recommended` | `other-interventions-and-no-change`; distinguish conventional, process improvement, human-led, and no change. |
| 7 | `proposed-future-state-workflow` | Keep proposed/not-deployed disclaimer; use final outcome, while retaining candidate/veto in technical detail. |
| 8 | `human-roles-and-controls` | Derive from evaluated safety rules only. |
| 9 | `risks-and-governance` | Never claim a non-material or non-evaluated risk input was assessed. |
| 10 | `adoption-roadmap` | Preserve decision-support boundary; no AEL execution. |
| 11 | `missing-information` | Separate blocking gaps, contextual unknowns, and priority-only gaps. |
| 12 | `methodology-and-policy-disclosure` | Framework/contract/policy identity, fingerprint, and provisional status. |
| 13 | `evidence-and-traceability-appendix` | Material evidence, context lineage, capability signals, and not-evaluated gates. |

## 9. Decision-ready recommendations for O-001 through O-006

All six remain subject to explicit approval.

### O-001 — Gate 1 negative result

1. **Recommended: add `NO_CHANGE_JUSTIFIED` as a separate change disposition and seventh derived customer outcome.** Accurate for non-human current states, but amends the canonical six-outcome target and therefore requires later canonical updates.
2. Fold into Keep Human-Led. Simpler, but can assert a false operating model.
3. Store only prose under another outcome. Harder to query, test, and audit.

### O-002 — Candidate intervention and autonomy

1. **Recommended: separate `selected_intervention_family` and `autonomy_ceiling`, with `readiness_disposition` and a derived `outcome_code`.** Gate 3 candidate and Gate 4 approval/veto remain independently auditable.
2. Use one expanded enum. Causes combinatorial conflation.
3. Keep legacy modes plus reasons. Cannot represent the target honestly.

### O-003 — Backward compatibility

1. **Recommended: parallel strict contracts, immutable workspace pinning, version-keyed adapters, additive writable migration, and virtual legacy pin for frozen migration-1–3 databases.** Preserves historical meaning and frozen bytes.
2. Change enums/policy/schemas in place. Rejected: corrupts meaning and validation.
3. Use a permissive union without a pin. Risks mixed chains and silent reassessment.

### O-004 — Strategic criticality

1. **Recommended: keep it out of framework v0.1 and allow strategic considerations only in evidence-backed business-value rationale.** No unvalidated twelfth dimension.
2. Add a twelfth dimension. Requires end-to-end contract expansion and scale validation.
3. Add an untyped override. Rejected: weakens determinism and auditability.

### O-005 — Process improvement versus discovery

1. **Recommended: Process Improvement First requires at least one sufficiently evidenced known Gate 2 blocker; Discovery applies only when missing material evidence can still change the active path.** Avoids both imputation and unnecessary blocking.
2. Treat all low/unknown readiness as process improvement. Invents a diagnosis.
3. Treat all low/unknown readiness as discovery. Discards valid known blocker decisions.

### O-006 — Implementation complexity

1. **Recommended: explicit dual role—Gate 2 blocker plus priority component.** A known value above the ceiling can determine Process Improvement First; otherwise complexity remains a scored effort factor on eligible AI outcomes.
2. Priority only. Can call known infeasible work ready.
3. Gate 3 ranking only. Conflates readiness and intervention choice.
4. Gate 2 only. Loses transparent prioritization influence.

## 10. Versioning strategy

| Layer | Legacy | Recommended successor |
|---|---|---|
| Framework | implicit/current | `four-gate-framework.v0.1` |
| Decision policy | `decision_policy.v0.2` / `0.2.0` | `decision_policy.v0.3` / `0.3.0` |
| Phase 1 output | `phase1-v0.3` | `phase1-v0.4` |
| Integrated assessment | `phase5-v0.1` | `phase5-v0.2` |
| Decision package | `phase6-v0.1` | `phase6-v0.2` |
| GRW M1 | `grw-m1-v0.1` | Legacy-only initially; successor deferred. |
| M2 | `grw-m2-m1-v0.1` | New same-contract successor family only when authorized. |
| Writable workspace DB | migrations 1–3 | additive migration 4; metadata only, no legacy payload rewrite |
| Protected frozen DB | migration-1–3 file | unchanged file; virtual `phase1-v0.3` pin on read |

Rules:

- loaders reject unknown versions and never fall back to newest;
- policy IDs, contract versions, fingerprints, and schema versions are stored/rendered/tested together where persisted;
- failures are versioned with successes;
- Phase 2–4 artifacts can parent either a complete legacy Phase 5–6 pair or complete successor pair, never a mixed pair;
- no adapter persists a converted legacy object;
- application default changes only in a separately approved release.

## 11. Smallest vertical implementation slice

The first later implementation slice proves only the deterministic four-gate domain contract. It does not touch application defaults, Phase 5/6, SQLite, reports, Streamlit, DCW, GRW, M2, or frozen evaluation.

### 11.1 Slice 1 deliverable

Given an approved `BusinessProcess` and explicitly loaded v0.3 policy, produce a validated `FourGateProcessAssessment` with:

- exactly four ordered gate results per activity;
- the closed fields in section 3;
- Gate 2 blocker short-circuiting and non-blocking readiness context;
- Gate 3 conventional precedence before AI-fit materiality;
- Gate 4 candidate/veto semantics and dynamic predictability materiality;
- all seven proposed derived outcomes reachable;
- preserved criterion, accountability, capability-signal, and evidence lineage;
- complete, incomplete, and not-applicable priority states;
- deterministic repeatability.

The slice is callable only through a new explicit domain API. The v0.2 engine/default and existing expected outputs remain unchanged.

### 11.2 Exact files likely to change in an authorized Slice 1

Prefer additive files:

- add `config/decision_policy.v0.3.json`;
- add `src/ai_adoption_engine/models/four_gate_assessment.py`;
- add `src/ai_adoption_engine/decision/four_gate_policy.py`;
- add `src/ai_adoption_engine/decision/four_gate_gates.py`;
- add `src/ai_adoption_engine/decision/four_gate_engine.py`;
- keep successor enums in the new model module, or minimally extend `models/enums.py` only if sharing is proven necessary;
- add `tests/unit/test_four_gate_policy.py`;
- add `tests/unit/test_four_gate_gates.py`;
- add `tests/unit/test_four_gate_engine.py`;
- add focused v0.2 regression assertions only where required.

Do not edit `decision/gates.py`, reinterpret `RecommendationMode`, broaden the legacy policy validator, add persistence, or change the CLI/default in Slice 1.

### 11.3 Later separately authorized slices

1. Phase 5 successor integration and traceability.
2. Phase 6 package/report-domain successor contracts.
3. Version-keyed persistence adapters and workspace contract pinning, including frozen read compatibility.
4. Version-aware Results, Package, report, and HTML projections.
5. Successor DCW/GRW/M2 contracts and same-contract comparisons.
6. A separately governed successor evaluation cohort; never rewrite the frozen v0.2 portfolio.

## 12. Targeted acceptance tests for later implementation

### 12.1 Domain paths and evidence precedence

1. Missing activity/business-value evidence -> Gate 1 discovery; Gates 2–4 not evaluated.
2. Sufficient low business value -> proposed `NO_CHANGE_JUSTIFIED`; Gates 2–4 not evaluated.
3. Known low data readiness -> Process Improvement First even when complexity and all Gate 2 context are unknown.
4. Known excessive complexity -> Process Improvement First even when data readiness and all Gate 2 context are unknown.
5. No known Gate 2 blocker plus insufficient data readiness or complexity -> Gate 2 discovery.
6. Unknown repetition never causes Gate 1 or Gate 2 discovery.
7. Unknown predictability never causes Gate 2 discovery.
8. Unknown AI fit never causes Gate 2 discovery.
9. Sufficient conventional fit at/above cutoff -> Conventional Automation without requiring AI fit or capability signals.
10. Conventional fit below cutoff plus missing AI fit -> Gate 3 discovery.
11. Low sufficient AI fit -> Keep Human-Led without requiring capability signals.
12. Sufficient AI fit plus supported true signal -> AI candidate; unresolved mapping -> Gate 3 discovery; all supported false signals -> Keep Human-Led.
13. `WORKFLOW_AUTOMATION` cannot bypass conventional precedence.
14. AI candidate plus insufficient residual risk -> Gate 4 discovery.
15. AI candidate plus unacceptable known residual risk -> `AI_NOT_PERMITTED` and sole final outcome Keep Human-Led without requiring other Gate 4 inputs.
16. AI candidate plus one independently sufficient assistance constraint -> AI-Assisted even if peer constraint inputs or predictability are missing.
17. With no established assistance constraint, missing judgement/risk/accountability that could alter the ceiling -> Gate 4 discovery.
18. A failed strict non-predictability automation condition -> AI-Assisted without requiring predictability.
19. Only when all other automation conditions pass does missing predictability -> Gate 4 discovery; known low -> AI-Assisted; known sufficient -> AI Automation.
20. Known low readiness with missing support -> discovery, never Process Improvement First.
21. Every row in the closed combination table validates and nearby invalid combinations fail.
22. Exactly four gate results occur in order; all substantive stops and evidence stops produce correct later `NOT_EVALUATED` records.
23. Same input/policy produces byte-equivalent semantic JSON.
24. Legacy policy/capability/gate/engine/scoring expectations remain unchanged.

### 12.2 Priority and reporting

- AI final outcomes receive complete priority only when every scoring input is sufficient.
- Missing repetition, conditionally non-material predictability, or another scoring-only value yields incomplete priority without changing the decision.
- Non-AI, safety-vetoed AI, no-change, process-improvement, and discovery outcomes have priority not applicable.
- Results, Package, and HTML use one derived outcome and identical candidate/veto language.
- Discovery sections contain only active blocking gaps.
- Missing-information sections distinguish blocking, context, and priority gaps.
- Process Improvement First reports only established blocker evidence.
- A conventional result never says missing AI fit prevented a decision.
- An AI safety veto never appears as simultaneous AI and human-led final recommendations.

### 12.3 Integration, compatibility, and boundaries

- Phase 5 traces every criterion, accountability field, capability signal, materiality state, and typed output path exactly once.
- Phase 6 rejects mixed gate/contract families and produces all 13 ordered successor sections.
- Main serializers read legacy and successor versions through exact `(type, version)` adapters.
- Writable migration 4 adds/backfills contract metadata without changing any legacy payload JSON, payload hash, or recorded outcome.
- Frozen migration-1–3 databases open read-only with a virtual legacy pin and identical file hash before/after.
- Reset, regeneration, and idempotent assessment retain the pinned contract and policy fingerprint.
- Legacy pages/reports remain semantically equivalent.
- DCW rejects cross-contract movement comparisons.
- GRW legacy proofs remain unchanged; later successor proofs snapshot all typed decision fields.
- M2 refuses cross-contract reassessment/comparison and preserves baseline bytes/hashes.
- Existing Phase 5/6/7, DCW, GRW, M2, and frozen-evaluation boundaries remain enforced.

### 12.4 Relevant existing test families to extend, not rewrite

| Family | Existing tests | Successor focus |
|---|---|---|
| Models/capabilities | `tests/unit/test_models.py`, `test_candidate_process_models.py`, `test_capabilities.py` | Closed combinations, unknown/context preservation, stable capability mapping. |
| Policy/gates/engine/scoring | `tests/unit/test_policy.py`, `test_gates.py`, `test_engine.py`, `test_scoring.py`, `test_gate_wording_consistency.py` | Dynamic materiality, thresholds, all paths, priority states, legacy regression. |
| Phase 5/fingerprints | `tests/unit/test_assessment_orchestration.py`, `test_assessment_fingerprints.py`, `tests/integration/test_integrated_assessment.py`, `test_human_review.py` | Contract selection, approval, fingerprint, complete traceability. |
| Phase 6 domain | `tests/unit/test_decision_support_package.py`, `test_decision_support_governance.py`, `tests/integration/test_decision_support_pipeline.py` | Typed package, 13 sections, gap classes, veto semantics. |
| Persistence/workspace | `tests/unit/test_phase7_persistence.py`, `tests/integration/test_phase7_offline_workspace.py`, `test_f1_frozen_workspace_protection.py` | Version adapters, metadata-only migration, virtual frozen pin, immutable contract. |
| Results/package/report | `tests/unit/test_decision_narrative.py`, `test_report_decision_first.py`, `test_phase7_demo_and_report.py`, `tests/ui/test_results_decision_first.py`, `test_decision_package_decision_first.py`, `test_portfolio_v1_release_journey.py` | Path-specific copy, one outcome, app/export equivalence. |
| DCW | `tests/unit/test_decision_continuation.py`, `tests/integration/test_dcw_p1.py`, `tests/ui/test_decision_continuation_decision_first.py`, `test_decision_continuation_ui.py` | Contract discrimination; no cross-contract movement claim. |
| GRW M1 | `tests/unit/test_grw_models.py`, `test_grw_service.py`, `tests/integration/test_grw_m1_lifecycle.py`, `tests/ui/test_grw_m1.py`, `test_grw_m1_decision_clear.py` | Legacy proof unchanged; later typed successor proof. |
| M2 | `tests/unit/test_grw_m2_models.py`, `test_grw_m2_policy_instrument.py`, `test_grw_m2_projection_comparison.py`, `test_grw_m2_service.py`, `test_controlled_reassessment_report.py`, `tests/integration/test_grw_m2_m1_lifecycle.py`, `tests/ui/test_grw_m2.py`, `test_reassessment_decision_clear.py` | Same-contract reassessment, Gate 2 reference, immutable baseline. |
| Architecture boundaries | `tests/architecture/test_phase5_boundaries.py`, `test_phase6_boundaries.py`, `test_phase7_boundaries.py`, `test_dcw_p1_boundaries.py`, `test_grw_m1_boundaries.py`, `test_grw_m2_boundaries.py` | No successor policy logic in orchestration, persistence, continuation, GRW, report, or UI. |
| Frozen evaluation | `tests/architecture/test_phase8_portfolio_boundaries.py`, `tests/integration/test_phase8_portfolio_*`, `test_phase8_development_validation.py`, `test_phase8_primary_annotation_app.py` | No legacy/frozen rewrite; new governed successor cohort only. |

## 13. Migration risks and controls

| Risk | Control |
|---|---|
| Gate-wide evidence checks create unnecessary discovery. | Ordered rule-path materiality; context fields cannot block until outcome-relevant. |
| Missing data is mistaken for a readiness blocker. | Process Improvement First requires a sufficiently evidenced known blocker. |
| A known blocker is suppressed by unrelated unknowns. | Established terminal blocker short-circuits unrelated evidence requirements. |
| Missing AI fit blocks a conventional result. | Conventional precedence is evaluated before AI fit becomes material. |
| AI candidate and Keep Human-Led appear as simultaneous recommendations. | `selected_intervention_family` records Gate 3 history; `outcome_code` is the sole final recommendation. |
| Legacy JSON validates as successor or changes apparent meaning. | Exact version adapters, no fallback, no persisted conversion. |
| Writable migration rewrites legacy decisions. | Migration 4 changes schema/contract metadata only; assert payload JSON and hashes unchanged. |
| Adding migration 4 makes a frozen database unreadable. | Supported migration-1–3 read adapter with virtual legacy pin; never migrate protected files. |
| A legacy idempotent operation satisfies a successor request. | Include contract and policy fingerprint in operation identity. |
| Discovery appears as evidence against AI. | Dedicated status, typed gaps, and copy tests. |
| Candidate/autonomy fields drift apart. | Closed combination validation and derived-only outcome. |
| Threshold carry-over is described as validated. | Preserve provisional/not-academically-validated disclosure in policy and reports. |
| Logic leaks into reports, persistence, or UI. | Additive domain modules plus existing architecture boundaries. |
| GRW/DCW/M2 compare unlike contracts. | Version-discriminated view/proof/comparison models and same-contract guards. |
| Frozen evaluation is regenerated. | No in-place evaluation writes; unchanged manifests/hashes and boundary tests. |

## 14. Validation status and explicit non-scope

Inherited thresholds, scoring weights/bands, and the proposed implementation-complexity ceiling remain **PROVISIONAL — NOT YET ACADEMICALLY VALIDATED**. Carry-forward supports continuity only. It does not validate predictive accuracy, recommendation accuracy, ROI, causal impact, deployment readiness, or generalization.

This design does not authorize or claim:

- production code, tests, configuration, schema, persistence, database, UI, report, GRW, M2, or framework implementation;
- modification of `decision_policy.v0.2` or legacy behavior;
- any threshold, weight, outcome-rule, or academic validation claim;
- retroactive conversion/rewrite of persisted assessments, reports, artifact payloads/hashes, frozen files, manifests, or historical conclusions;
- a twelfth strategic-criticality dimension;
- unconstrained LLM judgment in deterministic decisions;
- implementation, pilot, deployment, monitoring, or the Adoption Execution Layer;
- authentication, tenancy, enterprise integration, hosting/commercialization, or unrelated reliability work;
- release/push/relabeling of the Validate Process redesign;
- a commit or push.

## 15. Explicit approval checklist before implementation

Before Slice 1, approve or amend and then record in canonical memory:

- [ ] O-001: amend the canonical target from six to seven derived outcomes by adding `NO_CHANGE_JUSTIFIED`.
- [ ] O-002: use `readiness_disposition`, `selected_intervention_family`, `autonomy_ceiling`, and a derived-only `outcome_code`.
- [ ] O-003: accept parallel strict versions, writable metadata-only migration 4, and virtual frozen legacy pins.
- [ ] O-004: keep strategic criticality out of framework v0.1 and only in evidence-backed business-value rationale.
- [ ] O-005: use rule-path evidence materiality; Process Improvement First requires a known evidenced blocker.
- [ ] O-006: give implementation complexity an explicit Gate 2 blocker plus priority role.
- [ ] Treat repetition as Gate 2 context/priority only; it never causes Gate 2 discovery.
- [ ] Treat predictability as context/priority and conditionally material only at Gate 4 while it can distinguish automation from assistance.
- [ ] Evaluate conventional fit before AI fit; do not require AI evidence for a decided conventional path.
- [ ] Preserve deterministic capability-signal mapping and require supported mapping only after AI fit qualifies.
- [ ] Accept the Gate 4 AI-candidate safety-veto semantics and mandatory single-outcome report wording.
- [ ] Accept the recommended successor identifiers and strict no-conversion rules.
- [ ] Accept inherited thresholds plus complexity ceiling only as provisional and not academically validated.
- [ ] Keep Slice 1 persistence-free, explicit-only, and non-default.

After approval, use an authorized canonical-memory update to record the decisions and proposed seventh-outcome amendment before any implementation task begins.
