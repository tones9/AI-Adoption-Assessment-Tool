# Codex Handoff

Status: **CANONICAL OPERATING HANDOFF**  
Last updated: **2026-09-05**

## Fast start

For an ordinary task:

1. Read `AGENTS.md`, this file, `03_CURRENT_STATE.md`, and only the governing contract cited by the task.
2. Check branch, HEAD, Git status, and the relevant diff before changing files.
3. Inspect only the requested implementation files and directly relevant tests.
4. Read broader canonical documents only if a material ambiguity or cross-boundary conflict remains.
5. Run the narrowest relevant verification first.

For successor framework work, read only the cited detailed authority (normally `docs/four-gate-migration-design-v0.2.md`; for GRW/M2 core, `docs/four-gate-grw-m2-design-v0.1.md`). Preserve design documents unchanged.

## Source-of-truth rule

- Approved successor intent: `01_FRAMEWORK_SPEC.md`, `02_DECISIONS.md`, and `docs/four-gate-migration-design-v0.2.md`.
- Implemented reality: code, versioned configuration, tests, and Git, summarized in `03_CURRENT_STATE.md`.
- Historical rationale: older documents, plans, reports, decks, and archives.

The approved target is not shipped behavior. Production remains the legacy four-outcome `decision_policy.v0.2` / `0.2.0` system until a separately authorized migration is implemented and verified.

## Verification ladder

Use the smallest level that can answer the task safely:

1. **Targeted check:** relevant diff, configuration validation, and direct unit tests.
2. **Boundary check:** architecture and adjacent lifecycle tests when a public contract or layer boundary changes.
3. **Broad check:** full suite only for cross-cutting production changes, policy/schema/persistence migrations, release verification, or unresolved interactions.
4. **Historical deep check:** only when a material decision cannot be resolved from canonical memory and current implementation.

## Change rules

- Preserve the dirty working tree and unrelated user changes.
- Do not edit frozen evaluation artifacts or historical outputs in place.
- Do not change `decision_policy.v0.2`, legacy recommendation enums, legacy schemas, persistence contracts, or frozen methodology.
- New behavior must use the approved successor identifiers and exact version-keyed contracts.
- Never replace deterministic decisions with unconstrained LLM judgement.
- Preserve unknowns, evidence lineage, human approval, baseline immutability, and the product boundary at the adoption decision.
- A named slice authorizes only that slice. Do not infer authorization for later integration or migration work.
- Report verified implementation facts to the ChatGPT Project chat for canonical-memory updates. Do not modify canonical-memory or framework-design documents unless explicitly tasked.
- Do not commit or push unless explicitly asked.

## Agreed work order

1. **Completed:** persistence-free Slice 1 was implemented and verified on 2026-09-04. It remains explicitly invoked and non-default.
2. **Completed:** Phase 5 successor integration and traceability was implemented and verified on 2026-09-05. The parallel `phase5-v0.2` contract embeds `phase1-v0.4`, is explicit and non-default, requires `ApprovedProcessReview`, preserves validation/fingerprints/ordered typed traceability and structured failures, and leaves legacy `phase5-v0.1` untouched.
3. **Completed:** Phase 6 successor package/report-domain work was implemented and verified on 2026-09-05. The explicit, parallel `phase6-v0.2` contract accepts only successful `phase5-v0.2` successor assessments, creates structured deterministic package and 13-section report content using one derived final outcome, and preserves typed fields, path-specific gaps, candidate/veto history, policy fingerprint, and evidence lineage. Legacy `phase6-v0.1` and all defaults remain untouched.
4. **Completed:** version-keyed persistence adapters and workspace contract pinning were implemented and verified on 2026-09-05. Writable migration-4 metadata and successor artifacts are additive only; legacy payload JSON, hashes, outcomes, report content, parent links, and active pointers remain unchanged. Protected migration-1–3 databases are byte-invariant/read-only with only a virtual legacy pin. Dispatch is exact by `(artifact_type, artifact_schema_version)`, unknown versions fail closed, mixed legacy/successor parent chains are rejected, and pins become immutable after approval or downstream history.
5. **Completed:** version-aware report, HTML, and UI projections were implemented and verified on 2026-09-05. Exact contract dispatch renders successor seven-outcome/four-gate/typed-field/gap/priority/candidate-veto content while preserving legacy presentation semantics. No decision, policy/default, persistence/schema, or workflow-action change occurred.
6. **Completed:** successor Decision Continuation Workspace contract discrimination was implemented and verified on 2026-09-05. DCW recognizes and read-only presents a four-gate baseline with exact contract identity and typed decisions; GRW/M2 reassessment and comparison remain legacy-only/unavailable for successor baselines. It never creates, resumes, routes, or compares cross-contract continuations as like-for-like.
7. **Completed:** the isolated `grw-m2-four-gate-v0.1` same-contract data-readiness reassessment core was implemented and verified on 2026-09-05. It accepts only active Gate 2 data-readiness discovery, changes only that approved field in a successor projection, uses explicit successor Phase 5/6 services, performs typed same-contract comparison, and keeps baseline/frozen workspaces immutable. The focused set comprised 202 passing tests. It does not activate a DCW or UI route.
8. **Completed:** successor DCW/GRW-M2 activation was implemented and verified on 2026-09-06. It exposes only the existing same-contract Gate 2 data-readiness lifecycle, retains an immutable official baseline, requires explicit human evidence review and reassessment approval, fails closed without writes for ineligible/malformed/mixed/unknown/frozen baselines, and preserves legacy DCW/M1/M2/default behavior. The focused set comprised 201 passing tests.
9. **Completed:** the initial `four-gate-evaluation-cohort.v0.1` synthetic-development harness was implemented and verified on 2026-09-06. It has exact successor pins, contract/lineage/repeatability/freeze checks, deterministic development-only outputs, and visible claim exclusions. It does not import into production or alter legacy Phase 8 artifacts. The focused set comprised 80 passing tests.
10. **Current governed-case checkpoint — no Codex run authorized:** `HMPO-2022-SURGE-001` has controlled packet v0.2 material in `evaluation/four_gate_cohorts/governed_case_materials/HMPO-2022-SURGE-001/`. Wait for the separately prepared Brendan product review/approval and Rohan independent reference using v0.2; do not run, compare, or implement governed-case support until both are frozen and the next slice is explicitly authorized. A separately designed expansion of reassessment eligibility remains later work.
11. Decide separately whether to verify, release, and push the committed Validate Process redesign; do not combine it with the successor or relabel it as Portfolio V1.
12. Keep O-007 open until separately resolved.
13. Resume separately scoped reliability and productisation work only when authorized. Authentication, tenancy, hosted commercialisation, and the Adoption Execution Layer remain future scope.

## Verified completed Codex task — Slice 1

**Task type: implementation — persistence-free Slice 1 only (completed 2026-09-04).**

This section is the retained completion record for Slice 1, not authorization to repeat it or begin a later slice.

Implement the pure deterministic successor domain contract from `docs/four-gate-migration-design-v0.2.md`. Given an approved `BusinessProcess` and an explicitly loaded `decision_policy.v0.3`, return a validated `FourGateProcessAssessment` while leaving every legacy default and integrated path unchanged.

### Required Slice 1 deliverable

- Exactly four ordered gate results per activity, with later gates marked not evaluated after a substantive or evidence stop.
- Separate typed `change_disposition`, `readiness_disposition`, `selected_intervention_family`, and `autonomy_ceiling`, with derived-only `outcome_code` and closed-combination validation.
- All seven outcomes reachable, including `NO_CHANGE_JUSTIFIED`.
- Gate 2 known-blocker short-circuiting, data-readiness and implementation-complexity materiality, and non-blocking repetition/predictability readiness context.
- Gate 3 conventional precedence before AI-fit materiality and deterministic provenance-aware capability mapping.
- Gate 4 AI-candidate safety veto and dynamic predictability materiality.
- Preserved criterion, accountability, capability-signal, confidence, and evidence lineage.
- Complete, incomplete, and not-applicable priority states, with implementation complexity included for eligible AI priority.
- Deterministic repeatability.
- A new explicit domain API only; no default route may invoke it.

### Preferred additive files

- Add `config/decision_policy.v0.3.json`.
- Add `src/ai_adoption_engine/models/four_gate_assessment.py`.
- Add `src/ai_adoption_engine/decision/four_gate_policy.py`.
- Add `src/ai_adoption_engine/decision/four_gate_gates.py`.
- Add `src/ai_adoption_engine/decision/four_gate_engine.py`.
- Add `tests/unit/test_four_gate_policy.py`.
- Add `tests/unit/test_four_gate_gates.py`.
- Add `tests/unit/test_four_gate_engine.py`.
- Add focused v0.2 regression assertions only if required to prove non-regression.

Keep successor enums in the new model module unless sharing is proven necessary. Do not edit legacy `decision/gates.py`, reinterpret `RecommendationMode`, broaden the legacy policy validator, or change the CLI/default.

### Slice 1 acceptance focus

Test every approved terminal and discovery path, including:

- Gate 1 discovery and `NO_CHANGE_JUSTIFIED`;
- each known Gate 2 blocker winning over unrelated unknowns, and missing material readiness evidence producing discovery only when no blocker is established;
- repetition, predictability, and AI fit not causing Gate 2 discovery;
- conventional fit deciding without AI evidence;
- AI-fit and capability-mapping branches at Gate 3;
- Gate 4 residual-risk discovery and known safety veto;
- independently sufficient assistance constraints, missing constraint inputs, strict non-predictability assistance, and conditionally material predictability;
- every valid output-field combination plus nearby invalid combinations;
- exactly four ordered gate results and correct not-evaluated behavior;
- priority completeness/applicability states;
- byte-equivalent semantic JSON for repeated identical inputs;
- unchanged legacy v0.2 policy, capability, gate, engine, and scoring expectations.

Run the three new unit-test files first, then only the focused legacy regression tests needed by the implementation. Do not run the full production suite unless a discovered cross-boundary effect makes it necessary and the task scope is revisited.

### Explicit non-scope

Slice 1 must not change:

- the integrated assessment service or its `phase1-v0.3` default;
- Phase 5, Phase 6, Decision Package, reports, HTML, or customer-facing UI;
- SQLite schemas, migrations, databases, adapters, contract pins, or persistence;
- DCW, GRW, or GRW M2 contracts and comparisons;
- frozen evaluation artifacts, manifests, payloads, hashes, outcomes, or workspace bytes;
- legacy policy/configuration behavior or historical results;
- application/CLI defaults;
- thresholds, weights, bands, or the complexity ceiling beyond encoding the approved provisional contract;
- the Adoption Execution Layer, enterprise integrations, commercialisation, Validate Process release work, or O-007.

This task is Slice 1, not the full product migration.

## Historical prompt used for Slice 1

> Read `AGENTS.md`, the five canonical project-memory files, and `docs/four-gate-migration-design-v0.2.md`. Implement only the persistence-free, explicitly invoked, non-default Slice 1 in `04_CODEX_HANDOFF.md`. Add the v0.3 successor policy, pure four-gate model/policy/gates/engine modules, and targeted unit tests. Preserve all legacy v0.2 defaults and behavior. Do not touch integrated assessment, Phase 5/6, persistence, schemas, databases, reports, UI, DCW, GRW, M2, frozen evaluation, or historical design files. Run targeted Slice 1 tests and focused legacy regression checks only; do not commit or push.
