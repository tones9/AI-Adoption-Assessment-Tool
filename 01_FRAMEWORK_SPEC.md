# Four-Gate Framework Specification

Status: **APPROVED CANONICAL TARGET — NOT YET IMPLEMENTED**  
Framework contract: **`four-gate-framework.v0.1`**  
Detailed design authority: **`docs/four-gate-migration-design-v0.2.md`**  
Last reconciled: **2026-09-03**

## Decision question

For each business activity:

> Should this activity change, is it ready, what intervention is best, and how much autonomy is safe?

The unit of assessment is an activity within one reviewed and approved business process. The approved target is a deterministic, evidence-traceable successor to the shipped `decision_policy.v0.2` system. It is not current production behavior.

## Evidence materiality and precedence

Evidence sufficiency is evaluated per active rule path, not as a global completeness gate.

- Missing, unreliable, insufficiently confident, or untraceable information produces **Discovery Required** only when that information could change the active decision.
- A sufficiently evidenced terminal decision is not suppressed by unrelated unknowns. Later gates are recorded as not evaluated.
- **Process Improvement First** requires a sufficiently evidenced known readiness failure. It must never be inferred from missing information.
- An input may be decision-material, contextual, priority-scoring, or not evaluated on a particular path. Reports and traces must preserve that role.
- Unknown remains distinct from zero and retains its knowledge state, rationale, confidence where inferred, and evidence lineage.

**Discovery Required — insufficient evidence for the active decision** is a completed customer outcome. It must identify the blocking question or evidence gap and must not imply that AI is suitable or unsuitable. The current code's `INVESTIGATE_FURTHER` mode is its closest legacy predecessor, but is not the successor contract.

## The four gates

### Gate 1 — Should We Change It?

Purpose: establish whether changing the activity is justified before selecting a technology.

Decision-material input:

- Business value

Task repetition may support an evidence-backed value rationale, but repetition alone does not establish the Gate 1 decision. `strategic_criticality` is not a framework v0.1 dimension; strategic considerations may appear only inside an evidence-backed business-value rationale.

Rules:

1. If business value is decision-materially unknown, return **Discovery Required**.
2. If business value is below the approved value threshold, set `change_disposition=NO_CHANGE_JUSTIFIED` and derive the same customer outcome.
3. Otherwise set `change_disposition=CHANGE_JUSTIFIED` and continue to Gate 2.

`NO_CHANGE_JUSTIFIED` is a distinct disposition and outcome. It must not be collapsed into `KEEP_HUMAN_LED`, because the current activity may already be automated or system-led.

### Gate 2 — Is It Ready?

Purpose: determine whether the activity has a known readiness blocker or is ready for intervention selection.

Decision-material inputs:

- Data readiness
- Implementation complexity

Context and priority inputs:

- Task repetition
- Task predictability

AI capability fit may be retained as readiness-profile context, but becomes decision-material only at Gate 3 after conventional-automation precedence is evaluated.

Rules:

1. Evaluate sufficiently evidenced known readiness blockers from data readiness and implementation complexity.
2. If either establishes a blocker, set `readiness_disposition=PROCESS_IMPROVEMENT_FIRST` and derive that outcome. Unrelated missing readiness-profile inputs do not override it.
3. If no blocker is established, both decision-material inputs must be sufficient to establish readiness. If either could still change the Gate 2 decision, return **Discovery Required**.
4. Otherwise set `readiness_disposition=READY_FOR_INTERVENTION_SELECTION` and continue.

Repetition is never a Gate 2 discovery blocker. Predictability is not a Gate 2 discovery blocker; it becomes decision-material only if an AI candidate reaches the Gate 4 branch that still needs to distinguish AI Automation from AI-Assisted Work.

### Gate 3 — What Is the Best Intervention?

Purpose: select the candidate intervention family without assuming AI is the destination.

Decision-material inputs, in precedence order:

1. Conventional solution fit
2. AI capability fit, only if a sufficiently fitting conventional solution was not selected
3. Deterministic, provenance-aware capability mapping, only if AI capability fit supports an AI path

Rules:

1. If conventional solution fit is decision-materially unknown, return **Discovery Required**.
2. If it meets the conventional threshold, set `selected_intervention_family=CONVENTIONAL_AUTOMATION`. Missing AI capability evidence cannot block this established result.
3. Otherwise evaluate AI capability fit. If it is decision-materially unknown, return **Discovery Required**.
4. If AI capability fit is below threshold, set `selected_intervention_family=KEEP_HUMAN_LED`.
5. If AI capability fit meets threshold, use deterministic, evidence-provenanced capability mapping. An unresolved material mapping returns **Discovery Required**; an evidenced mapping with no supported AI capability selects `KEEP_HUMAN_LED`; a supported mapping selects `AI` and continues to Gate 4.

`selected_intervention_family` names the Gate 3 candidate, not the final approved intervention. **Process Improvement First** is a Gate 2 terminal result, not a Gate 3 family.

### Gate 4 — How Much Autonomy Is Safe?

Purpose: apply the safety ceiling to a Gate 3 AI candidate and determine the final permitted AI role.

This gate is evaluated only when `selected_intervention_family=AI`.

Decision-material inputs are evaluated path-specifically:

- Residual risk with human oversight is evaluated first as the safety veto.
- Human judgement requirement, risk consequence, and human accountability determine whether assistance is required.
- Task predictability becomes decision-material only if the prior checks still permit automation and the engine must distinguish AI Automation from AI-Assisted Work.

Rules:

1. If sufficiently evidenced residual risk is unacceptable, set `autonomy_ceiling=AI_NOT_PERMITTED`. Missing unrelated Gate 4 evidence cannot suppress the veto. The sole derived outcome is `KEEP_HUMAN_LED`.
2. Otherwise, any sufficiently evidenced assistance constraint sets `autonomy_ceiling=AI_ASSISTED`; missing peer inputs cannot change that established ceiling.
3. If no assistance constraint is established, any missing input that could still change the ceiling produces **Discovery Required**.
4. If the strict non-predictability conditions require assistance, set `AI_ASSISTED` without requiring predictability.
5. Only when automation remains possible does predictability become decision-material. Missing predictability produces **Discovery Required**; insufficient predictability sets `AI_ASSISTED`; sufficient predictability sets `AI_AUTOMATION`.

Reports must describe `selected_intervention_family=AI` plus `autonomy_ceiling=AI_NOT_PERMITTED` as **an AI candidate rejected at the safety gate**, with `KEEP_HUMAN_LED` as the sole final outcome. They must not present simultaneous final AI and human-led recommendations.

## The 11 assessment dimensions

The dimensions remain lower-level evidence-bearing inputs, not 11 independent top-level decisions.

| # | Dimension | Type | Approved target role | Current implementation note |
|---:|---|---|---|---|
| 1 | Task repetition | 0–5 ordinal | Gate 2 context; priority input; may support Gate 1 rationale; never a Gate 2 discovery blocker | Priority only in policy v0.2 |
| 2 | Task predictability | 0–5 ordinal | Gate 2 context and priority; conditionally material at Gate 4 | Conditional at the current risk/autonomy gate and automation eligibility |
| 3 | Data readiness | 0–5 ordinal | Gate 2 decision-material readiness input | Material at the current technical-fit gate |
| 4 | AI capability fit | 0–5 ordinal | Gate 2 context; Gate 3 decision-material after conventional precedence | Material at the current technical-fit gate |
| 5 | Human judgement requirement | 0–5 ordinal | Gate 4 conditionally decision-material | Material at the current risk/autonomy gate |
| 6 | Business value | 0–5 ordinal | Gate 1 decision-material | Material at the current business-value gate |
| 7 | Risk consequence | 0–5 ordinal | Gate 4 conditionally decision-material | Material at the current risk/autonomy gate |
| 8 | Residual risk with human oversight | 0–5 ordinal | Gate 4 first safety-veto input | Material at the current risk/autonomy gate |
| 9 | Implementation complexity | 0–5 ordinal | Gate 2 decision-material blocker and eligible-AI priority input | Priority only in policy v0.2 |
| 10 | Conventional solution fit | 0–5 ordinal | Gate 3 first decision-material input | Conditional at the current technical-fit gate |
| 11 | Human accountability | Boolean/unknown | Gate 4 conditionally decision-material | Separate typed field, not a 0–5 criterion |

All inputs retain value, knowledge state (`known`, `inferred`, or `unknown`), rationale, evidence references where required, and confidence for inferred values.

## Typed successor output contract

The successor uses parallel typed fields rather than a single overloaded recommendation enum:

| Field | Approved values and meaning |
|---|---|
| `decision_status` | `COMPLETE` or `DISCOVERY_REQUIRED` |
| `change_disposition` | `CHANGE_JUSTIFIED`, `NO_CHANGE_JUSTIFIED`, or `NOT_DETERMINED` |
| `readiness_disposition` | `READY_FOR_INTERVENTION_SELECTION`, `PROCESS_IMPROVEMENT_FIRST`, `NOT_EVALUATED`, or `NOT_DETERMINED` |
| `selected_intervention_family` | Gate 3 candidate: `AI`, `CONVENTIONAL_AUTOMATION`, `KEEP_HUMAN_LED`, `NOT_APPLICABLE`, or `NOT_DETERMINED` |
| `autonomy_ceiling` | `AI_AUTOMATION`, `AI_ASSISTED`, `AI_NOT_PERMITTED`, `NOT_APPLICABLE`, or `NOT_DETERMINED` |
| `outcome_code` | Derived-only customer outcome; callers must not set it independently |

Every successor activity result records exactly four gate results. Gates after a terminal result use not-evaluated status and must not manufacture decisions or evidence gaps.

Closed combinations and derived outcomes are:

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

Any combination outside the approved closed contract is invalid rather than silently coerced.

## Seven derived customer outcomes

1. **No Change Justified** — Gate 1 establishes that intervention is not warranted.
2. **AI Automation** — AI may perform most of the activity within defined controls.
3. **AI-Assisted Work** — AI supports a person; material judgement or accountability remains human.
4. **Conventional Automation** — rules, workflow, integration, configuration, or traditional software is preferable.
5. **Process Improvement First** — an evidenced readiness blocker must be addressed before intervention selection.
6. **Keep Human-Led** — a human-led operating model is the appropriate final design, including an AI candidate rejected by Gate 4.
7. **Discovery Required** — evidence material to the active rule path is insufficient.

This seven-outcome set is the approved amendment to the formerly documented six-outcome target. The current implementation still exposes only `AUTOMATE`, `AUGMENT`, `INVESTIGATE_FURTHER`, and `DO_NOT_RECOMMEND`; the last mode collapses several successor outcomes.

## Versioning, persistence, and compatibility

Approved successor identifiers are:

- framework contract: `four-gate-framework.v0.1`;
- policy ID/version: `decision_policy.v0.3` / `0.3.0`;
- decision-output contract: `phase1-v0.4` (embedded in the successor integrated assessment);
- integrated-assessment artifact contract: `phase5-v0.2`;
- Decision Package artifact contract: `phase6-v0.2`.

Legacy and successor contracts coexist strictly:

- `decision_policy.v0.2`, legacy adapters, and legacy behavior remain available for pinned legacy workspaces.
- Workspace contract identity is immutable after creation and adapters are selected by version, not payload shape.
- Legacy artifact payload JSON, payload hashes, recorded historical outcomes, and frozen workspace files remain unchanged.
- Writable databases may receive additive migration-4 schema or contract-pin metadata. Migration 4 must not rewrite legacy artifact payloads or reinterpret legacy outcomes.
- Protected migration-1–3 frozen databases are opened read-only and receive only a virtual legacy contract pin; their file bytes do not change.
- Reports must label the contract used, preserve evidence roles, and render only the single derived customer outcome.
- GRW, DCW, and GRW M2 may not cross contract families implicitly. Any later successor support requires version-keyed adapters and separate authorization.

## Implementation and validation boundary

Approval of this target did not by itself implement it. The first authorised implementation slice was completed and verified on 2026-09-04: the persistence-free, explicitly invoked, non-default successor model, policy loader, four gates, engine, and targeted unit tests. It did not change the integrated assessment service, defaults, persistence, reports, workspaces, UI, frozen artifacts, or historical results. Later slices still require separate authorization.

The approved inherited thresholds, weights, scoring bands, and new implementation-complexity ceiling are provisional and are not academically validated. Implementation must preserve that label and must not claim predictive, recommendation, ROI, causal, or generalisation validity.
