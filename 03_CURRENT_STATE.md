# Current State

Status: **CANONICAL IMPLEMENTATION SNAPSHOT**  
Implementation snapshot verified: **2026-09-01**  
Legacy policy identity rechecked: **2026-09-03**
Successor Slice 1 verified: **2026-09-04**
Successor Phase 5 verified: **2026-09-05**
Successor Phase 6 verified: **2026-09-05**
Successor persistence and contract pinning verified: **2026-09-05**
Successor presentation projections verified: **2026-09-05**
Successor DCW contract discrimination verified: **2026-09-05**
Successor GRW/M2 same-contract core verified: **2026-09-05**
Successor DCW/GRW-M2 activation verified: **2026-09-06**
Successor synthetic evaluation-cohort harness verified: **2026-09-06**

## Repository snapshot

- Repository: `/Users/antony/Documents/Personal Projects/AI-Adoption Engine`
- Branch: `codex/validate-process-workspace`
- HEAD inspected: `d200a65` — `feat: redesign validation review workspace`
- Package: `ai-adoption-engine` version `1.0.0`
- Application: local single-user Python/Streamlit product with SQLite persistence
- Working tree: dirty before this documentation pass; existing user changes were preserved

## Implemented product

Portfolio Version 1 is substantially implemented:

- text-native PDF, plain-text, and pasted-text ingestion;
- candidate process extraction with resolved source evidence;
- human review, correction, unknown retention, structural resolution, and explicit approval;
- deterministic assessment using `config/decision_policy.v0.2.json`;
- priority scoring for eligible opportunities;
- Decision Package and HTML report;
- Decision Continuation Workspace;
- Gap Resolution Workspace M1 preliminary context;
- GRW M2 controlled data-readiness reassessment;
- separate successor Decision Package and neutral comparison;
- decision-first Streamlit presentation across eight registered pages;
- frozen evaluation-workspace write protection;
- two synthetic offline demonstrations.

The product ends at the decision. Authentication, tenancy, enterprise integrations, implementation, deployment, and measured post-adoption outcomes are not implemented.

## Decision engine actually shipped

Policy: `decision_policy.v0.2`, version `0.2.0`, status `PROVISIONAL — NOT YET ACADEMICALLY VALIDATED`.

Current evaluation order:

1. `evidence_sufficiency`
2. `technical_fit`
3. `business_value`
4. `risk_and_autonomy`

Current recommendation modes:

- `AUTOMATE`
- `AUGMENT`
- `INVESTIGATE_FURTHER`
- `DO_NOT_RECOMMEND`

Current inputs are ten 0–5 criteria plus `human_accountability_required` as a separate Boolean/unknown field. `repetition` and `implementation_complexity` affect current priority scoring but are not material decision gates. `conventional_solution_fit` is conditionally material at technical fit.

This is not yet the target four-gate framework. See `01_FRAMEWORK_SPEC.md`.

## Approved successor target — Slice 1, Phase 5/6, persistence, presentation, DCW discrimination, and narrow GRW/M2 core implemented; product migration not implemented

On 2026-09-03, `docs/four-gate-migration-design-v0.2.md` was approved as the detailed design authority for `four-gate-framework.v0.1`. O-001 through O-006 are closed in `02_DECISIONS.md`; O-007 remains open.

The approved target includes:

- seven derived customer outcomes, adding `NO_CHANGE_JUSTIFIED`;
- separate typed `change_disposition`, `readiness_disposition`, `selected_intervention_family`, and `autonomy_ceiling` fields with a derived-only `outcome_code`;
- path-specific evidence materiality and not-evaluated behavior;
- Gate 2 decision-material data readiness and implementation complexity, with repetition and predictability retained as context and priority inputs;
- conventional-solution precedence before AI capability fit at Gate 3;
- deterministic, provenance-aware capability mapping;
- an AI-candidate Gate 4 safety veto that derives only `KEEP_HUMAN_LED` when AI is not permitted;
- parallel successor identifiers `decision_policy.v0.3` / `0.3.0`, `phase1-v0.4`, `phase5-v0.2`, and `phase6-v0.2`, with immutable contract pins and version-keyed adapters;
- unchanged legacy payload JSON, hashes, historical outcomes, and frozen files, while allowing only additive migration-4 metadata in writable databases and virtual legacy pins for protected read-only migration-1–3 databases.

The opt-in, persistence-free Slice 1 successor policy, typed output models, deterministic gates, engine API, and targeted unit tests are implemented. It is not connected to application defaults, Phase 5/6, persistence, reports, UI, DCW, GRW, M2, or frozen evaluation. The inherited thresholds, weights, scoring bands, and new implementation-complexity ceiling remain provisional and are not academically validated.

Slice 1 verification on 2026-09-04 passed 29 successor tests and 31 focused legacy policy/capability/gate/engine/scoring regression tests. The successor remains explicitly invoked through `FourGateAssessmentEngine` / `assess_four_gate()` with an explicitly loaded `decision_policy.v0.3`; the shipped application continues to use `decision_policy.v0.2` by default.

The parallel, explicitly invoked Phase 5 successor route is implemented and verified: `FourGateIntegratedAssessmentService` requires an `ApprovedProcessReview` and explicit v0.3 policy loader, returns `phase5-v0.2` embedding `phase1-v0.4`, preserves structured failures/fingerprints/complete typed traces, and has no default route. On 2026-09-05, 14 successor Phase 5 tests, 25 legacy Phase 5 regression tests, and 17 adjacent successor policy/engine tests passed (56 targeted tests total). It does not alter the legacy `phase5-v0.1` route or add persistence, packages/reports, UI, or default selection.

The parallel, explicitly invoked Phase 6 successor route is implemented and verified: `FourGateDecisionSupportPackageService` accepts only successful `phase5-v0.2` successor assessments and returns deterministic `phase6-v0.2` structured package and 13-section report-domain content. It preserves typed decisions, four ordered gates, source/policy fingerprints, material evidence, complete reviewed lineage, classified gaps, priority status, and candidate-versus-safety-veto history. On 2026-09-05, 18 successor Phase 6 tests, 23 legacy Phase 6 regression tests, and 27 adjacent successor Phase 5/domain tests passed (68 targeted tests total). It does not alter legacy Phase 6/default behavior or add persistence, HTML/report views, UI, CLI/default selection, DCW, GRW, M2, or frozen-artifact work.

Version-keyed persistence adapters and workspace contract pinning are implemented and verified. Writable migration 4 adds only contract-pin/idempotency metadata and exact legacy/successor Phase 5/6 dispatch; legacy payload JSON, SHA-256 hashes, recorded outcomes/report content, parent links, active pointers, and schema-version artifact fields remain unchanged. Protected migration-1–3 databases open read-only with a virtual legacy `phase1-v0.3` pin and remain byte-invariant with no WAL/journal/SHM sidecar files. On 2026-09-05, 12 successor persistence tests, 54 legacy persistence/frozen-workspace regression tests, and 25 adjacent successor Phase 5/6 tests passed (91 targeted tests total). Defaults, UI, HTML/report views, DCW, GRW, M2, and frozen evaluation remain unchanged.

Version-aware report, HTML, and UI projections are implemented and verified. Exact contract dispatch presents the seven successor outcomes, four gates, typed technical fields, classified gaps, priority status, and candidate-versus-safety-veto history while preserving legacy presentation semantics. On 2026-09-05, 23 successor presentation tests, 92 legacy presentation/UI regression tests, and 30 adjacent successor Phase 5/6/persistence tests passed (145 targeted tests total). This did not change decision logic, policies, thresholds, defaults, persistence, schemas, workflow generation actions, CLI, DCW, GRW, M2, or frozen artifacts.

Successor DCW contract discrimination is implemented and verified. DCW recognizes a persisted four-gate baseline as a distinct immutable, read-only contract family and displays exact framework/policy/Phase 1/5/6 identities, typed decisions, and four gates. It explicitly marks legacy GRW/M2 reassessment and comparison unavailable for successor baselines, creates no continuation artifacts/runs, and fails closed for mixed, malformed, unknown, or inconsistent baselines. On 2026-09-05, 12 successor DCW tests, 55 legacy DCW/GRW/M2 domain/lifecycle tests, 78 legacy UI/persistence/frozen-workspace tests, and 16 adjacent successor presentation tests passed (161 targeted tests total).

The isolated `grw-m2-four-gate-v0.1` lifecycle is implemented and verified through successor DCW. It accepts only an active Gate 2 `data_readiness` Discovery Required gap; retains an immutable official baseline; permits only a one-field approved successor projection; uses explicit successor Phase 5/6 services and typed same-contract comparison; persists additively only in writable workspaces; and refuses frozen workspaces. The resumable UI requires explicit document submission, human evidence review, data-readiness resolution, reassessment request, and approval before creating the separate successor assessment/package. A controlled supporting document may enter the successor Phase 6 trace only after Phase 5 validation and still must resolve through consistent reviewed evidence references. On 2026-09-06, 25 successor activation tests, 26 successor-core/persistence/frozen regressions, 59 legacy GRW/DCW/persistence regressions, 70 legacy UI/report regressions, and 21 successor DCW/presentation regressions passed (201 targeted tests total). The route remains explicit and non-default; all other successor gaps and reassessment paths remain unavailable.

## Evaluation state

- The frozen descriptive portfolio v0.2 includes `PORT-001`, `PORT-002`, and `PORT-004`.
- `PORT-003` is retained historically as `SUPERSEDED_CONTAMINATED_BEFORE` and excluded from v0.2 aggregates.
- Across 20 included activities, all 20 returned `INVESTIGATE_FURTHER` at technical fit because AI capability fit remained unknown.
- The result supports cautious preservation of uncertainty. It does not validate predictive accuracy, recommendation accuracy, thresholds, weights, ROI, causal impact, deployment readiness, or generalisation.
- The portfolio spans two production-fingerprint cohorts.

Phase 9A Fix 0 was implemented on 2026-08-15 to let a reviewer attach existing document evidence to a criterion through the UI. Semantic relevance of the selected citation is still not validated automatically.

Phase 9A-0c Case C is incomplete. Stage 1 live extraction was completed on 2026-08-17 and produced a partial eight-step candidate extraction; human review, approval, assessment, freeze, prediction comparison, and threshold decision were not completed.

## Committed local Validate Process redesign

The Validate Process redesign is committed locally in `d200a65`; it is not yet pushed to GitHub or included in a new release. The main changes are in:

- `src/ai_adoption_engine/presentation/components/evidence.py`
- `src/ai_adoption_engine/presentation/pages/review.py`
- `src/ai_adoption_engine/presentation/theme.py`
- related integration and UI tests

The redesign consolidates the required-review queue and selected work area, adds clearer progress and final-approval presentation, and moves optional details out of the required path. The associated untracked brief is `docs/validate-process-redesign-audit-and-brief-v0.1.md`. A recovered synthetic pasted-text fixture was manually run successfully through the redesigned validation path.

Other pre-existing dirty or untracked material included a modified Master Bible, experimental BPI2019 evaluation artifacts, observation scratch material, UI/design handoff archives, local agent-skill links, an empty file named `....`, and external testing documents. The later cleanup record below states which items were removed or archived.

## Verification performed during reconciliation

- 27 tests passed across the five test files changed by the active Validate Process redesign.
- 44 tests passed across core policy, gates, engine, scoring, demo fixtures, and integrated assessment.
- `git diff --check` reported no whitespace errors in the pre-existing tracked changes.
- The first test run emitted one cache-write warning because the inspection environment did not have write permission for the repository's `.pytest_cache`; the tests themselves passed.

These were targeted checks, not a full-suite certification.

## Centralisation changes made on 2026-09-01

- Created the five-file canonical spine at the repository root.
- Replaced the untracked imported `AGENTS.md` with a shorter instruction file that points to the spine. Its useful safeguards were retained: preserve architecture, inspect narrowly, protect frozen evaluation, use deterministic decisions, verify before modifying, and do not commit assistant settings.
- Updated the README opening so it indexes the spine and no longer presents the stale Master Bible as the current highest authority.
- Initially left the Master Bible, technical specification, architecture blueprint, overview PDF, project map, research, design plans, evaluation artifacts, UI handoffs, archives, code, configuration, and databases in place. The 2026-09-01 cleanup subsequently moved the legacy source documents and deliveries to the external historical archive.
- Made no production-code, policy, schema, persistence, or evaluation-artifact change as part of centralisation.

## Cleanup record — 2026-09-01

- Removed generated caches, Python bytecode, packaging metadata, generated `build/` content, `.DS_Store` files, the empty `....` file, and two zero-byte demo databases.
- Kept `.venv/` so the project remains immediately runnable.
- Deleted `evaluation/experimental/bpi2019/source/extract.b.jsonl` after verifying it was byte-identical to retained `extract.a.jsonl`. This reclaimed approximately 188 MB while preserving one intermediate and the small derived/provenance records.
- Moved the legacy root specifications, research report, overview PDF, UI/UX delivery, testing PDFs, and Phase 9A scratch material to `/Users/antony/Documents/Personal Projects/AI-Adoption Engine Archive/2026-09-01-centralisation`.
- The archive location and restoration guidance are recorded here, in the README, and in the archive's own `ARCHIVE_INDEX.md`. The temporary `ARCHIVE_POINTER.md` was removed during the later metadata cleanup.
- Preserved the active code, tests, configuration, canonical documentation spine, frozen evaluation portfolio, incomplete governed Phase 9A Case C record, and `var/ai_adoption_engine.db` with its 13 assessments and 57 artifacts.

### Metadata cleanup

- Removed `.claude/` and `.agents/`; both were local assistant-specific Streamlit skill links and were not used by the application.
- Removed `ARCHIVE_POINTER.md` after moving its location guidance into the README and this current-state record.
- Kept `AGENTS.md` because Codex reads it automatically to find the canonical context and low-token working rules. It does not affect application runtime.

## Stale, duplicate, or conflicting material

| Material | Finding | Treatment |
|---|---|---|
| Archived `AI_Adoption_Engine_MASTER_BIBLE_v1.0.docx` | Claims highest authority; its current-status section says portfolio validation is in progress and its immediate action says start Phase 1. Both are stale. | Moved to the external historical archive. Canonical spine governs current direction and state. |
| Archived `AI_Adoption_Engine_Technical_Specification_v0.1.docx` | Early MVP design with eight initial criteria, three suitability gates, and four outcomes. | External historical archive; not current state. |
| Archived architecture blueprint and project map | Early seven-screen and phase-sequence architecture; useful for origin and boundaries but superseded by the eight-page Portfolio V1 implementation. | External historical archive; consult only for historical rationale. |
| Archived `AI_Adoption_Assessment_Overview.pdf` | Most complete articulation of 11 dimensions and five intervention outcomes, but it is presentation material rather than the implemented contract. | Used to form the canonical target framework, then moved to the external historical archive. |
| Historical design/implementation plans under `docs/` | Many headers still say “not implemented” even though later commits and tests show DCW, guided review, GRW M1/M2, reassessment, and Portfolio V1 were implemented. | Preserve frozen status statements as historical; use this file for current state. |
| `evaluation/portfolio/README.md` | Still describes the v0.1 composition `PORT-001/002/003`. | Treat `cross_case_summary.v0.2.md` and this current-state file as authoritative for the v0.2 composition. |
| Archived UI/UX `batch1/`, ZIPs, deck, and handoff | Design delivery/snapshot material. Two files matched current source exactly; most snapshot files differed from production. | External historical archive; never production source. |
| `config/decision_policy.v0.1.json` | Superseded by policy v0.2. | Retain for version history; do not use by default. |

## Immediate product risks and unknowns

1. The successor route remains explicit and non-default; legacy `decision_policy.v0.2` remains the application/CLI default.
2. Successor GRW/M2 supports only one idempotently reused active Gate 2 `data_readiness` reassessment per exact eligible baseline/step. Other gaps, repeated reassessment, and cross-contract comparison remain unavailable.
3. The current legacy `DO_NOT_RECOMMEND` mode still collapses conventional automation, process improvement, human-led work, and other rejection reasons.
4. Phase 9A still cannot validate that a cited snippet semantically supports the criterion value.
5. Phase 9A-0c Case C remains incomplete; O-007 remains open.
6. The Validate Process redesign is committed locally but is not yet pushed or released; its recorded verification is targeted rather than full-suite release certification.
7. Long live-document extraction is not yet resilient: a provider timeout can fail a candidate extraction without chunk-level retry, resume, or user-facing progress. Treat this as a separate scoped reliability task, not a four-gate migration change.

## Next state-changing checkpoint

The synthetic-only `four-gate-evaluation-cohort.v0.1` harness and five development fixtures are implemented and verified. They pin the exact successor contract, validate lineage and traceability, prove byte-stable repeatability, preserve not-applicable measures, generate deterministic cohort/case freeze artifacts, and refuse Phase 8 targets. Every output explicitly excludes real-world, effectiveness, ROI, deployment-safety, threshold-quality, and generalisation claims. On 2026-09-06, 18 successor cohort tests, 40 successor Phase 5/6/persistence regressions, and 22 legacy Phase 8 freeze/boundary regressions passed (80 targeted tests total).

No further successor implementation slice is authorized. The first governed-case material is prepared as `HMPO-2022-SURGE-001`, using controlled before-only packet v0.2 from a supplied NAO report. Brendan must complete the product review and Rohan must submit an independent reference using v0.2 before any assessment run or comparison is authorized. Broadening reassessment eligibility remains a separate design decision.

The local Validate Process redesign can be verified and released separately; it does not block successor work. O-007 remains a separate open sequencing decision.
