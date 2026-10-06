# Project Decisions

Status: **CANONICAL DECISION LOG**  
Last updated: **2026-10-05**

## Adopted decisions

### D-001 — Use a lightweight canonical documentation spine

Date: 2026-09-01  
Status: Adopted

`00_PROJECT_CONTEXT.md` through `04_CODEX_HANDOFF.md` are the central project memory. The former Master Bible, technical specification, architecture blueprint, research report, PDFs, decks, and milestone plans are preserved as historical or supporting sources. They no longer override a later adopted decision recorded here.

Reason: the repository contains useful but time-stamped documents whose authority and status statements conflict with the shipped code and later commits.

### D-002 — Use one product across two working surfaces

Date: 2026-09-01  
Status: Adopted

ChatGPT Project chats are used for planning, discussion, decision formation, framework/design documentation, and canonical-memory updates. Codex is used for repository inspection, production implementation, and code/test verification. Codex reports verified implementation facts for the ChatGPT Project chat to record in this spine unless explicitly tasked otherwise. A chat transcript is not a source of truth.

### D-003 — Adopt the four-gate model as the target framework

Date: 2026-09-01  
Status: Adopted for target design; not implemented

The target decision architecture is:

1. Should We Change It?
2. Is It Ready?
3. What Is the Best Intervention?
4. How Much Autonomy Is Safe?

The implementation continues to use policy v0.2 and its existing gates until a separately approved migration is designed, implemented, and verified.

### D-004 — Retain the 11 dimensions as lower-level inputs

Date: 2026-09-01  
Status: Adopted

The 11 assessment dimensions remain evidence-bearing inputs beneath the four gates. They are not discarded and are not presented as 11 equal top-level decisions. The current model implements ten ordinal criteria plus a separate human-accountability field.

No twelfth dimension, including `strategic_criticality`, is adopted in framework v0.1.

### D-005 — Make Discovery Required a first-class target outcome

Date: 2026-09-01  
Status: Adopted for target design; not implemented as a new enum

Canonical label: **Discovery Required — insufficient evidence for the active decision**.

It is a completed result, can occur at any material evidence boundary, must state what is missing, and must not imply that AI is suitable or unsuitable. The existing `INVESTIGATE_FURTHER` result remains unchanged until successor behavior is separately implemented and verified.

### D-006 — Preserve current and frozen behavior during the framework redesign

Date: 2026-09-01  
Status: Adopted

Do not retroactively change policy v0.2, historic assessments, frozen portfolio artifacts, or evaluation conclusions to make them look like four-gate outputs. Successor behavior must be versioned and coexist with historical records.

### D-007 — Verify narrowly before inspecting deeply

Date: 2026-09-01  
Status: Adopted

For each Codex task: read the compact canonical context, inspect Git state, inspect only directly relevant files, and run targeted tests first. Expand to boundary tests, broad searches, historical documents, or the full suite only when the change crosses contracts or a material ambiguity remains.

### D-008 — Preserve historical material; document supersession instead of deleting

Date: 2026-09-01  
Status: Adopted

No historical document, archive, evaluation artifact, or design snapshot is deleted in the centralisation pass. Duplicate or stale material is classified in `03_CURRENT_STATE.md`. Cleanup, renaming, or archival can happen later as a separate, reviewable task.

### D-009 — Centralisation does not authorize production-code changes

Date: 2026-09-01  
Status: Adopted

This documentation pass updates project memory and Codex instructions only. The four-gate production migration requires its own explicit implementation task.

### D-010 — Make the four-gate migration the next framework priority

Date: 2026-09-01  
Status: Adopted; design stage completed 2026-09-03

Preserve Git tag `v1.0.0` as the historical Portfolio V1 baseline. The locally committed Validate Process usability redesign is a separate release decision and does not block the four-gate successor.

The design-only four-gate migration was completed and approved on 2026-09-03. Implementation and verification remain separately versioned and authorized, beginning only with the Slice 1 boundary in D-019. Do not call the successor Portfolio V1. After separately authorized migration work, resume remaining reliability and productisation work; authentication, tenancy, hosted commercialisation, and the Adoption Execution Layer remain future scope.

### D-011 — Use “Update the Brain” for durable project-memory updates

Date: 2026-09-01  
Status: Adopted

The explicit phrase **“Update the Brain”** authorises a concise update to the relevant canonical project-memory files after a verified technical result or an agreed product decision. It does not authorise production-code changes, commits, or pushes. The response must state what was updated and the next task. When a technical task changes a contract, release state, policy, schema, persistence, or test scope, recommend this update before progressing further.

### D-012 — Constrain four-gate work to the decision framework

Date: 2026-09-02  
Status: Adopted

The four-gate migration must preserve the existing system architecture, UI/UX rules, evidence model, auditability, persistence, and established product behaviour. Changes outside the decision framework are out of scope unless strictly required by the approved migration contract. Approval of the contract does not by itself authorise implementation beyond a separately named slice.

### D-013 — Approve the four-gate migration contract

Date: 2026-09-03  
Status: Adopted target design; not implemented

`docs/four-gate-migration-design-v0.2.md` is the approved detailed design authority for the successor `four-gate-framework.v0.1` contract. It closes O-001 through O-006 and governs later successor implementation unless superseded by an explicit recorded decision. The shipped product remains the legacy `decision_policy.v0.2` system until separately implemented and verified.

### D-014 — Use seven derived outcomes and separate typed decision fields

Date: 2026-09-03  
Status: Adopted target design; not implemented  
Closes: O-001, O-002

Add `NO_CHANGE_JUSTIFIED` as a separate Gate 1 disposition and seventh customer outcome. The successor result uses separate typed `change_disposition`, `readiness_disposition`, `selected_intervention_family`, and `autonomy_ceiling` fields, with `outcome_code` derived only from their valid closed combinations. `selected_intervention_family` is the Gate 3 candidate, not necessarily the final approved intervention.

Reason: no-change is not synonymous with human-led work, and separate gate outputs preserve meaning, traceability, not-evaluated behavior, and safety-veto semantics without overloading one enum.

### D-015 — Adopt rule-path-specific evidence materiality and implementation-complexity dual use

Date: 2026-09-03  
Status: Adopted target design; not implemented  
Closes: O-005, O-006

Missing information produces `DISCOVERY_REQUIRED` only when it could change the active decision. A sufficiently evidenced terminal decision is not suppressed by unrelated unknowns. `PROCESS_IMPROVEMENT_FIRST` requires a sufficiently evidenced known Gate 2 blocker and is never inferred from missing information.

At Gate 2, data readiness and implementation complexity are decision-material. Implementation complexity also contributes to priority scoring for eligible AI outcomes. Repetition remains readiness context and a priority input, never a Gate 2 discovery blocker. Predictability remains readiness context and a priority input, becoming decision-material only if Gate 4 still needs to distinguish AI Automation from AI-Assisted Work.

### D-016 — Apply conventional precedence, deterministic capability mapping, and the AI safety veto

Date: 2026-09-03  
Status: Adopted target design; not implemented

Gate 3 evaluates conventional-solution fit before AI capability fit. Missing AI evidence cannot block a sufficiently evidenced conventional solution. If the AI path remains active, AI capability fit and deterministic, provenance-aware capability mapping select the Gate 3 candidate.

When Gate 3 selects `AI`, Gate 4 may set `autonomy_ceiling=AI_NOT_PERMITTED`. The sole derived customer outcome is then `KEEP_HUMAN_LED`; reports describe an AI candidate rejected at the safety gate and must not present simultaneous final AI and human-led recommendations.

### D-017 — Use parallel versioned contracts and preserve historical artifacts

Date: 2026-09-03  
Status: Adopted target design; not implemented  
Closes: O-003

Use strict parallel contracts, immutable workspace contract pinning, and version-keyed adapters. Approved successor identifiers are `four-gate-framework.v0.1`, `decision_policy.v0.3` / `0.3.0`, `phase1-v0.4`, `phase5-v0.2`, and `phase6-v0.2`.

Writable databases may receive additive migration-4 schema or contract-pin metadata, but migration 4 must not rewrite legacy artifact payload JSON, payload hashes, or recorded historical outcomes. Protected migration-1–3 frozen databases are opened read-only with only a virtual legacy pin and no file-byte changes. Historical results are not converted or reinterpreted.

### D-018 — Keep strategic criticality out of framework v0.1

Date: 2026-09-03  
Status: Adopted  
Closes: O-004

Do not add `strategic_criticality` as a dimension in `four-gate-framework.v0.1`. Strategic considerations may appear only within evidence-backed business-value rationale.

### D-019 — Keep calibration provisional; complete and verify persistence-free Slice 1

Date: 2026-09-03  
Status: Adopted implementation boundary; Slice 1 verified 2026-09-04

Inherited thresholds, weights, scoring bands, and the new implementation-complexity ceiling remain provisional and are not academically validated. The authorized persistence-free Slice 1 was implemented and independently verified on 2026-09-04: 29 successor tests and 31 focused legacy regression tests passed. It is explicitly invoked and non-default, with no integration, persistence, reports, workspaces, UI, frozen-artifact changes, or full product migration.

### D-020 — Authorize, complete, and verify Phase 5 successor integration and traceability only

Date: 2026-09-04  
Status: Adopted implementation boundary; verified 2026-09-05

Authorize a separate, explicit Phase 5 successor orchestration path that accepts only `ApprovedProcessReview`, invokes only an explicitly loaded `decision_policy.v0.3` through `FourGateAssessmentEngine`, and returns a new `phase5-v0.2` integrated-assessment contract embedding `phase1-v0.4`. It must preserve approval gating, validated input consistency, immutable input/policy fingerprints, ordered per-step traceability, material evidence lineage, structured failures, and deterministic repeatability. The implementation was independently verified on 2026-09-05: 14 successor Phase 5 tests, 25 legacy Phase 5 regression tests, and 17 adjacent successor policy/engine tests passed (56 targeted tests total).

The completed slice coexists with the legacy `phase5-v0.1` route without changing its models, defaults, output, reader, or tests. It did not add persistence, workspace artifacts, schema/database migrations, Phase 6 package/report contracts, UI, DCW, GRW, M2, frozen-artifact work, default policy selection, commits, or pushes. Later slices remain separately authorized.

### D-021 — Authorize Phase 6 successor package/report-domain contract only

Date: 2026-09-05  
Status: Adopted implementation boundary; verified 2026-09-05

Authorize a separate, explicit `phase6-v0.2` decision-package domain route that accepts only `FourGateIntegratedAssessmentSuccess` (`phase5-v0.2` embedding `phase1-v0.4`) and produces deterministic structured package and 13-section report content. It must preserve source lineage, policy fingerprint, typed decision fields, ordered four-gate results, active blocking gaps, contextual/priority gaps, priority status, material evidence, and candidate-versus-safety-veto history. The implementation was independently verified on 2026-09-05: 18 successor Phase 6 tests, 23 legacy Phase 6 regression tests, and 27 adjacent successor Phase 5/domain tests passed (68 targeted tests total).

The route uses one derived outcome as the final recommendation. In particular, it does not portray `AI` and `KEEP_HUMAN_LED` as simultaneous final outcomes, or portray missing contextual evidence as a decision blocker. It coexists with, and does not alter, the legacy `phase6-v0.1` package models, service, defaults, output, reader, or tests.

This authorization excludes persistence, workspace artifacts, schema/database migrations, HTML/report views, Streamlit/UI, CLI/default selection, DCW, GRW, M2, frozen artifacts, successor evaluation, commits, and pushes. Later slices remain separately authorized.

### D-022 — Authorize version-keyed persistence adapters and workspace contract pinning only

Date: 2026-09-05  
Status: Adopted implementation boundary; verified 2026-09-05

Authorize the additive persistence slice that can store, read, and dispatch exact legacy or successor Phase 5/6 contracts by artifact type and schema version. Writable workspaces may receive migration-4 contract-pin metadata and successor artifact support, but must not rewrite legacy artifact payload JSON, payload hashes, recorded outcomes, or historical report content. Contract pinning must be immutable once approval or a downstream assessment artifact exists, and operation idempotency material must include the pinned decision contract and policy fingerprint. The implementation was independently verified on 2026-09-05: 12 successor persistence tests, 54 legacy persistence/frozen-workspace regression tests, and 25 adjacent successor Phase 5/6 tests passed (91 targeted tests total).

Protected migration-1–3 frozen databases remain byte-invariant and read-only. They received no migration, schema row, payload change, hash change, WAL/journal side effect, active-pointer change, or outcome relabelling; the read adapter supplies only a virtual legacy `phase1-v0.3` pin. Unknown `(artifact_type, artifact_schema_version)` pairs fail closed, and a parent chain cannot mix legacy and successor Phase 5/6 contract families.

This authorization excludes default route changes, HTML/report views, UI, CLI selection, DCW, GRW, M2, successor evaluation, commits, and pushes.

### D-023 — Authorize version-aware report, HTML, and UI projections only

Date: 2026-09-05  
Status: Adopted implementation boundary; verified 2026-09-05

Authorize version-dispatched read and presentation projections for existing legacy and successor Phase 5/6 artifacts. The successor projection may render the seven derived outcomes, four ordered gates, typed fields, path-specific gaps, material/context lineage, and candidate-versus-safety-veto history in the Results, Decision Package, structured report view, HTML report, process-flow component, and direct vocabulary/narrative helpers. Legacy projections remain semantically identical. The implementation was independently verified on 2026-09-05: 23 successor presentation tests, 92 legacy presentation/UI regression tests, and 30 adjacent successor Phase 5/6/persistence tests passed (145 targeted tests total).

The successor presentation must use one derived final outcome; preserve `DISCOVERY_REQUIRED` as insufficient evidence for the active decision; distinguish active blockers from contextual/priority gaps; state Process Improvement First only with established blockers; avoid implying AI evidence blocked a conventional decision; distinguish priority status from decision status; and show an AI safety veto as an AI candidate rejected at Gate 4 with `KEEP_HUMAN_LED` as the sole final recommendation.

This authorization excludes decision-engine changes, policy/default selection changes, new assessment/package workflow actions, persistence/schema changes, DCW, GRW, M2, successor evaluation, commits, and pushes.

### D-024 — Authorize successor Decision Continuation Workspace contract discrimination only

Date: 2026-09-05  
Status: Adopted implementation boundary; verified 2026-09-05

Authorize DCW to recognize and present a four-gate baseline package as a distinct contract family, retaining its exact framework, policy, Phase 1/5/6 versions, typed decisions, and artifact identity. The workspace clearly states that current GRW/M2 reassessment and comparison workflows are legacy-only and unavailable for a four-gate baseline until separately authorized successor contracts exist. The implementation was independently verified on 2026-09-05: 12 successor DCW tests, 55 legacy DCW/GRW/M2 domain/lifecycle tests, 78 legacy UI/persistence/frozen-workspace tests, and 16 adjacent successor presentation tests passed (161 targeted tests total).

DCW never creates, resumes, routes, or compares a legacy and successor continuation as like-for-like. It provides a read-only same-contract status and an explicit unavailable/deferred state for successor controlled reassessment. Legacy DCW behavior, M1, M2, persistence, decision logic, UI defaults, and frozen artifacts remain unchanged.

### D-025 — Approve, implement, and verify successor GRW/M2 same-contract data-readiness reassessment core

Date: 2026-09-05  
Status: Adopted implementation boundary; verified 2026-09-05

Approve `docs/four-gate-grw-m2-design-v0.1.md` as the authority for the first successor evidence/reassessment family, `grw-m2-four-gate-v0.1`. The first path is restricted to an active Gate 2 `data_readiness` discovery gap, with a separately approved one-field successor projection, explicit v0.3 Phase 5/6 services, new versioned artifacts, typed same-contract comparison, additive writable persistence, and absolute frozen-workspace exclusion.

All other successor gaps, including implementation complexity, Gate 1/3/4 discovery, context, and priority gaps remain unavailable. The new family must not extend or reinterpret legacy M1/M2 artifacts, invoke legacy default services, compare legacy modes with successor outcomes, or replace the immutable baseline.

The isolated core was independently verified on 2026-09-05: 15 successor GRW/M2 tests, 72 legacy GRW/M1/M2 tests, 38 legacy/successor DCW tests, and 77 successor Phase 5/6, persistence, and frozen-workspace regressions passed (202 targeted tests total). A narrow Phase 6 lineage correction permits a controlled supporting document already validated by Phase 5 while retaining trace-reference consistency checks. No DCW/UI route was activated; legacy/default behavior, frozen workspaces, canonical design documents, commits, and pushes remain unchanged.

### D-026 — Authorize successor DCW/GRW-M2 activation for the completed data-readiness path only

Date: 2026-09-05  
Status: Adopted implementation boundary; verified 2026-09-06

Authorize the Decision Continuation Workspace to expose only the completed `grw-m2-four-gate-v0.1` lifecycle for an eligible successor baseline: an active Gate 2 `data_readiness` Discovery Required gap. The UI must preserve the baseline as the official immutable decision; make eligibility and the separately approved same-contract successor status clear; keep technical identifiers, artifact hashes, evidence locators, and comparison detail behind technical detail; and fail closed without writes for every ineligible, malformed, mixed-contract, unknown, or frozen baseline.

This authorization permits composing the existing successor service and rendering/persisting its existing lifecycle actions. It excludes all other gaps, altered decision policy/engine behavior, legacy DCW/M1/M2 changes, default/CLI changes, cross-contract comparison, automatic approval, automated evidence acceptance, new persistence schemas, frozen artifacts, evaluation runs, commits, and pushes.

The activation was independently verified on 2026-09-06: 25 successor activation tests, 26 successor-core/persistence/frozen regressions, 59 legacy GRW/DCW/persistence regressions, 70 legacy UI/report regressions, and 21 successor DCW/presentation regressions passed (201 targeted tests total). The result is one idempotently reused reassessment per exact eligible baseline/step. The successor route remains explicit and non-default; no commit or push occurred.

### D-027 — Approve successor evaluation cohort and authorize harness/development-fixtures slice

Date: 2026-09-06  
Status: Adopted implementation boundary; verified 2026-09-06

Approve `docs/four-gate-evaluation-cohort-design-v0.1.md` and its NTT companion as the authority for a separate descriptive successor evaluation cohort. It uses new cohort/run identities, strict before-state and contract-pin controls, case-level traceability measures, and optional independently prepared reference annotations. It does not modify or reinterpret the frozen legacy Phase 8 portfolio, and it does not establish effectiveness, ROI, deployment-safety, threshold-quality, or generalisation claims.

Authorize only the first implementation slice: an isolated evaluation harness, cohort/case/freeze contracts, synthetic development fixtures, contract/lineage/repeatability/report checks, and tests proving that production and frozen legacy evaluation artifacts remain separate. Do not add governed real-world cases, reference annotations, the optional reassessment sub-study, external data collection, production imports, policy/default changes, or evaluation claims. Those later stages require separately authorized case material and review governance.

The initial harness was independently verified on 2026-09-06: 18 successor cohort tests, 40 successor Phase 5/6/persistence regressions, and 22 legacy Phase 8 freeze/boundary regressions passed (80 targeted tests total). It produces five synthetic fixtures covering no change, Gate 2 Discovery Required, conventional-first automation, Gate 4 safety veto, and Process Improvement First; all are expressly excluded from real-world or effectiveness claims. Production packages and existing Phase 8 artifacts remain untouched. No commit or push occurred.

### D-028 — Register HMPO 2022 Surge as a governed successor-cohort candidate

Date: 2026-09-07  
Status: Case-material preparation authorized; no assessment run authorized

Register `HMPO-2022-SURGE-001` from the supplied National Audit Office report as a proposed governed successor-cohort case. The full retrospective report is not admissible as an assessment input because it includes later outcomes. Only the controlled, paraphrased before-only packet may be used for review/reference preparation.

Brendan is the product reviewer. Rohan is the independent reference reviewer because he has not read or seen the full report or system output. No successor assessment, reference comparison, or real-world claim is authorized until Brendan’s review/approval and Rohan’s independently prepared reference are both supplied and frozen.

The initial role assignment was recorded incorrectly; the user confirmed that Brendan supplied the product review and Rohan supplied the independent reference, with no prior Rohan exposure to the full report. The v0.1 packet was not approved, so both v0.1 submissions remain feedback only. Packet v0.2 corrects the product-review findings; Brendan must review/approve v0.2 and Rohan must independently reference v0.2 before the case can proceed.

### D-029 — Adopt the Preliminary Assessment journey and verify its first contract-only slice

Date: 2026-09-26
Status: Adopted journey design; persistence-free domain contracts verified 2026-09-26

After candidate process extraction, the user explicitly chooses either `EXPLORE_PROCESS` or `ORGANISATIONAL_ASSESSMENT`. Both routes retain the existing human validation and explicit approval of the current-state process. A user without supporting organisational evidence can choose Explore this process, or return to it from the organisational route, without uploading or extracting the source process again.

A Preliminary Assessment is provisional exploration only. It uses the seven separate customer-facing directions Likely no change, Likely process improvement first, Likely conventional automation, Likely human-led, Potential AI-assisted work, Potential AI automation, and Insufficient basis to suggest a direction. Confidence is Low, Medium, or High and describes evidence coverage, not statistical probability. A Preliminary Assessment never creates an official four-gate outcome, Decision Package, organisational approval, or implementation authority, and it never silently satisfies strict evidence requirements.

The minimum user-facing evidence classes are documented fact, reasonable inference, and unknown. Documented facts require exact source-document lineage; reasonable inferences retain their fact references, rationale, and confidence without becoming facts; unknowns carry no imputed value and identify the evidence or owner needed to resolve them. Supporting organisational documents remain separate from the approved source process and may enter a later formal assessment only through reviewed, versioned evidence lineage and a separate formal-assessment input snapshot. The approved source process remains immutable.

The opt-in `journey-selection.v0.1` and `preliminary-assessment.v0.1` domain contracts were implemented without an evaluator, persistence, UI, policy, formal assessment, Decision Package, or default-route change. Independent verification passed 42 focused Preliminary Assessment tests and 34 regressions across candidate-process models, review approval, four-gate orchestration, and the four-gate engine. The application and CLI defaults remain unchanged, and no commit or push was made.

### D-030 — Approve the deterministic Preliminary Assessment evaluator design

Date: 2026-09-28
Status: Adopted and implemented; persistence-free evaluator verified 2026-09-28
Closes: O-008, O-009, O-010

Adopt `preliminary-evaluator-rules.v0.1` / `0.1.0` as a separately versioned, fingerprinted rule artifact with status `PROVISIONAL CONTINUITY — NOT VALIDATED`. Its canonical fingerprint covers evidence admissibility, the treatment of human-supplied information, ordered precedence, thresholds, capability handling, safety-unknown behavior, confidence rules, deciding-rule codes, direction mappings, and fixed rationale/question templates. Continuity values copied from `decision_policy.v0.3` remain separate runtime rules and make no validation or policy-equivalence claim.

The evaluator uses five ordered stages: change case, readiness, conventional fit, AI fit/capability, and safety/autonomy. Approved thresholds are business value `>=2`, data readiness `>=2`, implementation complexity `<=4`, conventional fit `>=4`, AI fit `>=3`, residual-risk veto `>=4`, judgement/consequence assistance `>=3`, and strict automation only with data readiness `>=4`, complexity `<=3`, residual risk/judgement/consequence `<=2`, accountability false, and predictability `>=4`. Repetition is context only. Readiness blockers precede intervention selection; conventional fit precedes AI; residual risk precedes assistance versus automation. Unknown or conflicted residual risk produces `PA-051`, Insufficient basis, and Low confidence. Only after residual risk is resolved below veto may incomplete autonomy evidence produce the narrow Low-confidence assisted-work fallback `PA-053`.

Stable deciding-rule codes `PA-001` through `PA-054` select exactly one provisional direction through a closed rule manifest. Before evaluator activation, `preliminary-assessment.v0.1` must add a mandatory rule-set reference and each activity must add a deciding-rule code plus an ordered, immutable decision-input trace. Trace entries use preliminary-only input names, reviewed field paths, normalized values, evidence classification, `evidence_item_ids`, materiality/stage, and a recomputable rule comparison. `activity_identity` is included in every applicable material manifest. The trace must resolve within the same activity, preserve deterministic ordering, reject invalid values/evidence/classes, and import no formal gate, outcome, policy, or Decision Package model.

Evidence is admissible only as reviewed documentary information from the approved source document or as an explicitly accepted/corrected, traceable model inference. Unreviewed suggestions, model confidence alone, rejected/non-retained values, other-document evidence, conflicts, and unknowns are not admissible values. Human-supplied information is context-only: it may create an unknown and evidence request but cannot satisfy a threshold, select a direction, remove an unknown, or raise confidence.

Activity confidence is path-material: High when every material input is documented; Medium when all are resolved and exactly one is a reviewed inference; Low for two or more material inferences, any insufficient-basis rule, or `PA-053`. Individual admissible inferences are Medium coverage and never High. Process confidence is the weakest activity confidence. Non-material later inputs do not affect direction or confidence.

`created_at` uses an injected UTC clock and the assessment receives a run-specific injected ID. Substantive repeatability excludes those two creation fields; full-envelope repeatability uses fixed injected dependencies. The evaluator accepts only `ApprovedProcessReview`, calls no LLM or formal engine, performs no persistence or UI work, and returns typed failure with no partial result for malformed structure or lineage while valid evidence gaps remain successful preliminary results containing unknowns.

The persistence-free evaluator and required `preliminary-assessment.v0.1` amendments were implemented and verified on 2026-09-28. The separately versioned rule artifact is `preliminary-evaluator-rules.v0.1`, version `0.1.0`, with fingerprint `3db8a54561bcfe263a5483e5d4c49e203bfac40eafbc8bc778cf773ed6ad1790`; it contains the five-stage precedence and stable deciding codes `PA-001` through `PA-054`. Verification passed 112 focused contract/rule/evaluator tests, the same 34 existing candidate-process/review/four-gate regressions used for the contract slice, and 5 fingerprint regressions. No persistence, UI activation, supporting-evidence workflow, formal conversion, default-route change, commit, or push was made.

### D-031 — Approve isolated Preliminary Assessment persistence and journey-state design

Date: 2026-09-29
Status: Adopted design; all five Preliminary Persistence slices implemented and verified 2026-09-29

Adopt `preliminary-journey-store.v0.1` as an additive, explicitly constructed SQLite persistence namespace isolated from strict `assessment_artifacts`, active pointers, workflow stages, contract pins, formal engines, and application/CLI defaults. One journey is anchored to one exact approved-review artifact and pins its source assessment, source document, review/approval identity and hash, validated-process identity, and extraction lineage. A later approved-review artifact creates a new journey; existing history is never rewritten or backfilled.

Journey state has three independent derived dimensions: `current_route`, `preliminary_status`, and `formal_lifecycle_status`. `current_route` is derived only from the highest-sequence `ROUTE_SELECTED` or `ROUTE_CHANGED` event. Other journey events cannot alter or invalidate the route. `preliminary_status` follows the exact precedence `RUNNING`, `AVAILABLE`, `RETRY_AVAILABLE`, `RERUN_REQUIRED`, then `NOT_STARTED`, independently of route and formal state. A compatible result is exposed as current only while the route is Explore; route changes retain all preliminary and formal history.

Every journey event uses a closed, versioned payload schema; only route-choice events carry `journey-selection.v0.1`. Event sequences are per-journey, gap-free, monotonic, and append-only. Each evaluator run has an immutable manifest that pins the latest Explore route-choice event, approved-review/source identity, output/evaluator/rule identities and fingerprint, request token, and optional retry predecessor. Run lifecycle events are append-only, with one start and at most one terminal event. Each journey permits at most one non-terminal run. Mutable status columns, if used, are non-authoritative projections that must agree with the immutable record or fail closed.

Completed runs have exactly one immutable result; failed or abandoned runs have none. An abandoned run is never reopened. A retry always uses a new run ID and request token and records `retry_of_run_id`; replaying the original token returns the original operation, including an abandoned one. Deliberate reruns always create new runs and results. Supersession links are immutable, acyclic, and journey-local. Result/run/journey/source/evaluator identities must agree, rule fingerprint drift under the same version is corruption, and no rerun is automatic.

Formal-start persistence is a separate sibling lifecycle with status `AWAITING_FORMAL_INPUTS`. It may reference a preliminary result only as `CONTEXT_ONLY_NOT_FORMAL_EVIDENCE`. Creating it must pin the latest organisational-assessment route event and must not create a core assessment, copy the source process, create or mutate strict artifacts, invoke an engine, advance workflow, satisfy evidence, or produce an outcome, approval, or Decision Package. Preliminary content never enters or satisfies the formal lifecycle.

Migration is additive, explicit, and has no backfill. Protected and frozen paths fail before DDL or sidecar creation. Safe backout disables explicit Preliminary service construction while retaining the isolated tables and immutable history; strict code continues to ignore them. Implementation is ordered into five controlled slices: (1) persistence contracts and additive schema, (2) journey choices and three-dimensional state, (3) evaluator-run/result persistence, (4) interrupted-run recovery, and (5) the isolated formal-start boundary. UI and supporting-document extraction/review remain later work. The ordered slices require bounded execution and verification one at a time, but no further product-owner decision is required to advance after a slice completes without a blocking issue.

Preliminary Persistence Slice 1 was implemented and verified on 2026-09-29. The isolated `preliminary-journey-store.v0.1` / `0.1.0` foundation adds eight versioned persistence record contracts, exact serialization and compatibility registration, and additive migration 1 solely under `preliminary_journey_schema_migrations`. Existing strict migrations, rows, active pointers, repository behavior, and defaults remain unchanged. Verification passed 133 focused Preliminary tests, 34 domain regressions, 31 persistence/frozen-workspace regressions, and 5 fingerprint regressions; compilation and `git diff --check` also passed. Writable legacy databases migrated additively, while frozen paths were rejected before database or sidecar mutation. Journey services, derived state, evaluator execution, recovery, formal-start services, and UI remain unimplemented.

Preliminary Persistence Slice 2 was implemented and verified on 2026-09-29. The explicitly constructed `PreliminaryJourneyService` creates or reuses one journey for one exact active approved-review artifact, persists idempotent route requests through `preliminary-route-request.v0.1` and isolated additive migration 2, appends only real route transitions, and derives the three independent state dimensions with the approved precedence and latest-route-choice semantics. It validates exact approved-review ownership, revision, schema, payload hash, parent review, source-document/process/review/approval/extraction lineage; selects compatible results independently of route; exposes a current result only under Explore; and fails closed for unsupported, corrupt, or inconsistent history. Verification passed 164 focused Preliminary tests, the same 34 domain regressions, 31 strict persistence/frozen-workspace regressions, and 5 fingerprint regressions; compilation and `git diff --check` passed. Writable Slice 1 and legacy databases migrated additively, frozen bytes and sidecars remained invariant, and strict workflow state, artifacts, pointers, migrations, policies, engines, and defaults remained unchanged. At that checkpoint, evaluator-run/result persistence, recovery, formal-start services, UI, and later slices were still unimplemented.

Preliminary Persistence Slice 3 was implemented and verified on 2026-09-29. The explicitly constructed `PreliminaryRunResultService.evaluate_and_persist(...)` invokes only the deterministic `PreliminaryAssessmentEvaluator`, uses the persisted run ID as the Preliminary Assessment ID, and atomically records the immutable manifest, exact Explore route/source/evaluator/rule/output pins, `RUN_LINKED`, `RUN_STARTED`, constrained projection, terminal history, immutable result, result-recorded event, and deliberate-rerun supersession. Same-token transport replay never reevaluates; new-token reruns receive new run/result identities. Typed evaluator failures record `RUN_FAILED` without a result, and failed final transactions leave one valid non-terminal run for Slice 4. Isolated additive migration 3 hardens one-predecessor supersession and unique result-audit events without changing the `preliminary-journey-store.v0.1` / `0.1.0` identity. Verification passed 184 focused Preliminary tests, 34 domain/approved-review regressions, 5 fingerprint regressions, and 24 strict-persistence/frozen-workspace regressions; compilation and `git diff --check` passed. Writable legacy, Slice 1, and Slice 2 databases remain compatible; strict state/defaults and frozen bytes/sidecars remain unchanged. Recovery/retry orchestration, formal-start services, UI, and later slices remain unimplemented.

Preliminary Persistence Slice 4 was implemented and verified on 2026-09-29. `PreliminaryRunResultService.abandon_interrupted_run(...)` explicitly terminates only a genuinely non-terminal run by atomically appending `RUN_ABANDONED`, updating the constrained projection, and recording a closed `preliminary-run-recovery.v0.2` abandonment event without changing its manifest or original request token. `retry_and_persist(...)` accepts only a failed or abandoned current-compatible same-journey predecessor, requires a new request token and run ID, pins the current Explore route and source/evaluator/rule/output identities, records exact `retry_of_run_id` lineage plus a `preliminary-run-recovery.v0.2` retry event, and then reuses the deterministic Slice 3 lifecycle. Original and recovery-token replays do not reevaluate or create history. Isolated additive migration 4 enforces recovery-token, one-abandonment, one-retry, same-journey, terminal-event, and retry-manifest constraints without changing `preliminary-journey-store.v0.1` / `0.1.0`. Verification passed 208 focused Preliminary tests, 34 domain/approved-review regressions, 5 fingerprint regressions, and 24 strict-persistence/frozen-workspace regressions; compilation and `git diff --check` passed. Writable legacy and Slice 1–3 databases migrate additively; strict state/defaults and frozen bytes/sidecars remain unchanged. Formal-start services, UI, and later slices remain unimplemented.

Preliminary Persistence Slice 5 was implemented and verified on 2026-09-29. The explicitly constructed `PreliminaryFormalStartService.start_formal_lifecycle(...)` atomically creates or replays one immutable `preliminary-formal-lifecycle.v0.1` sibling under the existing source assessment and journey, pins the latest Organisational Assessment route and exact active approved-review lineage, and persists only `AWAITING_FORMAL_INPUTS` plus the closed `FORMAL_LIFECYCLE_STARTED` event. `preliminary-formal-start-request.v0.1` provides immutable request-token idempotency through isolated additive migration 5. An optional same-journey compatible Preliminary result is retained only as `CONTEXT_ONLY_NOT_FORMAL_EVIDENCE`; no content is copied into formal evidence or strict artifacts. Same-token replay returns the original lifecycle, conflicting requests fail without writes, and route changes after creation do not hide or mutate either lifecycle. Verification passed 227 focused Preliminary tests, 34 domain/approved-review regressions, 5 fingerprint regressions, and 24 strict-persistence/frozen-workspace regressions; compilation and `git diff --check` passed. Writable legacy and Slice 1–4 databases migrate additively; strict assessments, stages, artifacts, active pointers, migrations, policies, engines, defaults, frozen bytes, and sidecars remain unchanged. All five approved persistence slices are complete; UI activation, supporting-evidence workflows, and formal conversion remain unimplemented.

### D-032 — Make canonical project-memory maintenance automatic and Codex-owned

Date: 2026-09-29
Status: Adopted; supersedes the explicit-trigger requirement in D-011

Codex must update the relevant canonical project-memory files automatically after verified work materially changes a contract, release state, policy, schema, persistence boundary, test scope, or immediate handoff, and after an approved durable product or design decision. The user no longer needs to issue or relay a separate “Update the Brain” command. Updates remain limited to verified or explicitly agreed facts and do not authorize production changes, commits, or pushes. The completing or verifying Codex turn performs the update before handing off the next task and reports **Updated** and **Next task**. The explicit phrase remains available as a manual request but is not required.

### D-033 — Approve Preliminary Assessment product activation and UI design

Date: 2026-09-30
Status: Implemented and verified behind a default-off activation flag

Adopt one conditional **Process journey** page, one deployment-wide default-off activation flag, and an explicit unchecked option to reference the latest compatible Preliminary result at formal start only as `CONTEXT_ONLY_NOT_FORMAL_EVIDENCE`. Route choice appears immediately after successful candidate extraction and before Validate process, but remains presentation/session intent until the exact current-state process review is approved. Both routes use the same validation and explicit approval path. After approval, the application creates or reuses the journey for that exact approved-review artifact and persists the selected route. Lost temporary intent is requested again; no journey may be persisted against an unapproved process.

The Process journey presents the three independent state dimensions without cancelling, hiding, relabelling, or converting history. Explore supports explicit run, compatible rerun, immutable history, typed failure, explicit interrupted-run abandonment, and new-run retry. The organisational route supports only creation or resumption of the isolated sibling lifecycle at customer-facing status **Awaiting formal inputs**. Preliminary content never becomes formal evidence, a gate result, formal outcome, organisational approval, implementation authority, or Decision Package. Customer-facing copy uses **Preliminary Assessment history** and evidence-coverage labels such as **Medium evidence coverage**; raw enum values are technical-detail content only.

Adopt journey-scoped strict-action protection. With the feature disabled, or enabled with no materialised Preliminary journey, existing strict behavior is unchanged. Once a journey is materialised, there is no automatic navigation to Assessment Results. Assessment Results must not offer a new legacy **Run AI-adoption assessment** action for that journey, and Decision Package must not offer new package generation from it. If strict results or packages already existed before journey materialisation, they remain available read-only and are never deleted or rewritten. Those protected pages provide a clear return action to Process journey. The organisational route remains at **Awaiting formal inputs** until a later separately approved evidence and formal-conversion workflow exists.

The approved empty and recovery states include: a post-approval **Journey setup incomplete** state that confirms approval remains valid and offers **Continue journey setup** without requiring reapproval or offering a strict fallback; an Assessment Results protected state stating **This assessment continues in Process journey** with only **Open Process journey** as its journey action; and Process journey prerequisite states for before extraction, after extraction before route choice, during validation, and after approval while materialisation is incomplete. The state mapping, navigation rules, tests, lo-fi wireframes, default-off activation, accessibility safeguards, idempotency behavior, and safe backout are closed with no further product-owner decision required.

The approved product-activation design was implemented and verified on 2026-09-30 as one bounded localhost-testable vertical slice. `AI_ADOPTION_ENGINE_PRELIMINARY_UI=1` conditionally composes the Preliminary services and registers Process journey; omission of the setting remains the unchanged default and does not construct those services or invoke their migrations through the UI. Source & Extraction records lineage-scoped session intent, Validate process retains the existing review/approval rules and materialises the exact approved-review journey idempotently, and Process journey exposes the persisted route, Preliminary, and formal dimensions plus explicit run, result, history, interruption, retry, rerun, route-switch, and awaiting-inputs formal-start states. Journey-scoped protection suppresses new strict assessment/package generation while retaining pre-existing strict artifacts read-only. The implementation adds no supporting-document workflow, formal evidence conversion, strict-engine invocation, formal outcome, approval, or new Decision Package generation.

Verification passed 13 focused Preliminary UI tests, 227 existing Preliminary contract/evaluator/persistence/service tests, and 79 selected approved-review, strict persistence, fingerprint, navigation, strict UI, and frozen-workspace regressions. Compilation and `git diff --check` passed. A feature-enabled Streamlit launch reached `http://localhost:8501` and returned HTTP 200. No default route, policy, strict artifact, frozen workspace, commit, or push changed.

On 2026-10-01, the first-time post-approval UX was simplified. The pre-approval route choice plus explicit process approval now authorises the initial route action without repeating intent. **Explore this process** automatically materialises the journey, starts exactly one idempotent Preliminary run, and opens its result or recovery state. **Run an organisational assessment** automatically materialises the journey, starts the isolated sibling lifecycle without Preliminary context, and opens **Awaiting formal inputs**. The internal Process journey route remains the persistent status, history, recovery, rerun, and route-switching hub, but it is hidden from navigation before materialisation and is labelled **Preliminary Assessment** or **Organisational Assessment** after route selection. It is no longer exposed as a mandatory customer step. Setup or run failure never invalidates process approval, never retries silently, and remains recoverable through the existing journey states. This refinement changes no evaluator, persistence contract, formal evidence boundary, strict workflow, default activation, policy, or Decision Package behavior. Verification passed 16 focused Preliminary UI tests, all 227 Preliminary regressions, and the same 79 adjacent regressions; compilation, whitespace checks, and live feature-enabled localhost rendering passed.

On 2026-10-04, the approved UI was extended with an explicit, default-off v0.2 compatibility selector. Omitted `AI_ADOPTION_ENGINE_PRELIMINARY_EVALUATOR`, or its exact v0.1 value, retains the complete v0.1 service identity; the exact v0.2 value selects the complete approved v0.2 evaluator, rule, fingerprint, and output identity. Every other value fails closed before Preliminary service construction or database writes. With both activation flags explicit, first-time Explore approval runs exactly one v0.2 assessment and renders it through `preliminary-result-presentation.v0.1`; the Organisational Assessment route still creates no Preliminary run and remains **Awaiting formal inputs**. v0.1 rendering is unchanged, audit identity is collapsed by default, and the formal-start service remains v0.1-only. No migration, evaluator, rule catalogue, fingerprint, persistence, strict-route, frozen-workspace, application-default, or CLI-default change was made. Verification passed 59 focused activation/persistence/presentation tests, 873 relevant compatibility and boundary regressions, and 28 application-default/strict-route UI regressions; compilation, whitespace checks, and live localhost Explore and Organisational route smoke tests passed.

### D-034 — Adopt explicit guided confirmation for Validate Process

Date: 2026-10-02
Status: Implemented and verified locally; not committed or pushed

Required current-state process review uses explicit, truthful actions rather than a preselected review-action dropdown. An unreviewed documented value offers **Confirm and continue**, **Correct this**, and the applicable exclusion/removal action; the displayed state must always match the persisted review disposition. Confirmation remains an explicit human-review event. Corrections and exclusions retain rationale, origin, evidence, and audit requirements. No default widget value may imply review, correction, rejection, unknown retention, or approval.

The required checklist keeps completed and unfinished items visible, opens the next unfinished item after a saved action, preserves unsaved correction drafts across deliberate item navigation, and treats step order as its own confirmable and correctable required check. Optional details remain outside the approval blockers and no bulk action may confirm all extracted details. Final approval is a separate summary and explicit approval action for the reviewed current-state process only. This interaction decision changes no approved-review schema, approval eligibility rule, provenance classification, unknown semantics, immutable approval, Preliminary lineage, strict route, policy, persistence schema, configuration, or default.

### D-035 — Approve Preliminary Assessment v0.2 evidence-grounded multi-opportunity evaluator design

Date: 2026-10-02
Status: Implemented and verified locally; explicit and non-default

Adopt the explicit, non-default `preliminary-assessment.v0.2`, `preliminary-evaluator.v0.2` / `0.2.0`, and `preliminary-evaluator-rules.v0.2` / `0.2.0` successor design. v0.1 remains frozen, independently runnable, and unchanged. The v0.2 evaluator still accepts exactly one immutable `ApprovedProcessReview`, remains provisional exploration only, cannot invoke the formal four-gate engine, and cannot create formal evidence, a gate result, organisational outcome, Decision Package, approval, or implementation authority.

Unlike v0.1's formal-field-first single-direction evaluation, v0.2 deterministically derives source-grounded atomic activity components, work needs, dependencies, and one to five independently governed opportunities. Exact guarded `PD2-001` through `PD2-021` rules map documented or explicitly reviewed source wording into conventional, process-improvement, human-led, AI-assisted, AI-automation, no-change, or Discovery Required directions using stable `PA2-*` precedence. Missing formal organisational evidence lowers evidence coverage and creates typed discovery needs without suppressing an independently supported exploratory opportunity. Conventional sufficiency wins only for the same work need; accountable human decisions, explicit assistance vetoes, material discretion, relational work, conflicts, and process friction retain their approved scope-specific precedence.

The design requires exact approved-document spans, closed literal/inflection manifests, normative-procedural `should` safeguards, deterministic clause segmentation, atomic multi-action construction, stable provenance, canonical signatures and ordering, content-derived SHA-256 IDs, immutable decision traces, and Low/Medium/High evidence-coverage aggregation. `PA2-050` requires complete documentary assistance governance; `PA2-052` requires the stricter positive documentary autonomy bundle. More than five independently governed opportunities produces Discovery Required with a split/clarify request rather than truncation or technical failure.

The binding mechanical errata close deterministic identities and construction: `pri2-` rule-derived inference IDs exclude component IDs to avoid circularity; every accepted literal family has an immutable `PD2-nnn-Lnnn` code; work needs are constructed by a canonical greedy non-backtracking merge; and `PD2-001` may mechanically derive `RECORDED_FORM:<normalized_object_key>` when an explicit recording output is absent. These rules change no product policy or formal boundary. Implementation must remain additive, explicitly dispatched, separately fingerprinted, safely disableable, and must prove v0.1/default/frozen-state invariance before activation. No v0.2 production code, test, configuration, persistence, UI, database, commit, or push change is authorized by this design decision alone.

On 2026-10-02, the binding Example 3 sentence was mechanically corrected to: “Using the complaint issue, the officer determines the category of the complaint as Stage 1 or Stage 2.” The existing `PD2-010` catalogue remains unchanged: the sentence supplies the contiguous `determines the category` literal, explicit `complaint` object, explicit Stage 1/Stage 2 output values, and the existing `complaint issue` dependency. No product policy, direction, precedence, or literal family was added.

The additive persistence-free v0.2 Slice 1 implementation is verified. Frozen contracts, the complete 124-family literal/dependency manifest, deterministic construction and selector, canonical content IDs, typed failures, byte-stable serialization, and exact version dispatch are implemented under the approved identities. The canonical v0.2 rule fingerprint is `1c06b6a9ce1fe9ee3f68c9b16a452ca2c283e3423a39ae6ef43bd5ccecb855c6`. Verification passed 528 focused v0.2 tests plus the targeted v0.1, fingerprint, approval/architecture, persistence/journey/UI-boundary, and strict-engine regression groups. v0.1 remains the default and retains fingerprint `3db8a54561bcfe263a5483e5d4c49e203bfac40eafbc8bc778cf773ed6ad1790`. No persistence, journey execution, UI, strict engine, frozen artifact, commit, or push change occurred.

On 2026-10-02, the separately authorized version-keyed persistence and journey compatibility slice was implemented and verified. Explicitly configured run/journey services now execute, serialize, persist, replay, recover, retry, and select either exact v0.1 or exact v0.2 compatibility identities; omitted configuration remains v0.1. Isolated additive Preliminary migration 6 adds parallel v0.2 run, event, projection, result, and supersession tables plus exact cross-version integrity views/triggers, without rebuilding v0.1 tables or rewriting historical rows. Tokens, retries, recovery, active-result selection, and supersession are exact-identity scoped; unknown, mixed, drifting, or corrupt identities fail closed. Stored histories coexist immutably and safe backout is disabling explicit v0.2 construction. v0.2 remains disconnected from formal start, Streamlit, rendering, automatic post-approval execution, and application/CLI defaults.

On 2026-10-03, the separately authorized version-aware result-presentation slice was implemented and verified. Frozen `preliminary-result-presentation.v0.1` projects exact persisted v0.1 or v0.2 results only after full evaluator/rule/fingerprint/output dispatch and integrity validation. The default customer view is nontechnical and audit-free; optional audit retains the exact persisted result, source, evaluator, rule, fingerprint, code, identifier, and decision-trace identity. v0.1 meaning is preserved, while v0.2 presents process evidence coverage, ordered activity states, independent opportunities, scoped discoveries, documented/reviewed/engine-derived evidence, unknowns, conflicts, next evidence, and exact excerpts/locators. Unknown, mixed, drifting, unresolved, or corrupt records fail closed with typed presentation errors. The projector remains callable only and is not imported by Streamlit, execution, persistence, strict routes, application defaults, or CLI defaults.

On 2026-10-04, the separately authorized activation slice connected that projector to Streamlit only behind `AI_ADOPTION_ENGINE_PRELIMINARY_UI=1` plus the exact `AI_ADOPTION_ENGINE_PRELIMINARY_EVALUATOR=preliminary-evaluator.v0.2` selector. Omission remains the complete v0.1 identity, invalid selectors fail before service construction or writes, and the cached service composition is keyed by the selected evaluator identity. Explicit v0.2 Explore approval runs and persists the exact v0.2 identity; v0.1 and v0.2 history remain immutable and version-aware. The Organisational Assessment route still invokes no Preliminary evaluator, and formal start remains v0.1-only. Safe backout is removal of the explicit v0.2 selector while retaining stored v0.2 history.

### D-036 — Approve the supporting-evidence review and formal-input conversion design

Date: 2026-10-04
Status: Approved design; implementation requires separate slice authorization

Adopt an isolated, versioned supporting-evidence workflow under the existing `preliminary-formal-lifecycle.v0.1`. Supporting documents are additional organisational evidence linked to the exact formal lifecycle, approved-review artifact, approved-process fingerprint, and source lineage. They never replace or re-extract the approved process. Supporting evidence is independent of the selected Preliminary evaluator version; Preliminary v0.1 and v0.2 results remain context only and can never satisfy a formal evidence requirement. The formal-start boundary remains v0.1-only.

The initial workflow accepts text-native PDF and plain-text files only, with limits of 10 MiB per file, 200 PDF pages, 1,000,000 extracted characters, 20 current documents, and 50 MiB total per formal lifecycle. Scanned, encrypted, active-content, malformed, executable, archive, Word, spreadsheet, and presentation files are unsupported. Accepted original bytes are retained immutably for v0.1 with no silent cleanup or per-document hard deletion. Document category is required descriptive metadata, using the approved closed organisational-evidence catalogue, but complete category coverage is not required and missing categories are warnings only. A configured external extraction provider may receive a document only after clear disclosure and explicit acknowledgement; absence of consent prevents external transmission and the product must not claim unavailable local extraction.

Extraction may propose plain-English claims, exact source spans, categories, activities, formal-field relevance, and explanatory gate relevance, but it never assigns or approves a formal value. Deterministic code resolves every trusted excerpt against the stored document and preserves exact source lineage. Mandatory human review records accept, correct, reject, or unresolved actions with a locally declared reviewer name, organisational role, acknowledgement that identity is not authenticated, and timestamp. Accepted evidence is classified exactly as documented fact, reviewed inference, unknown, or conflict. Corrected claims preserve the original excerpt. A reviewed inference links to documented facts and uses a reviewer-approved numeric confidence from `0.0` to `1.0` plus rationale. Unknowns and conflicts have null values and no confidence. A rejected proposal retains its original proposed classification, excerpt, reviewer declaration, action, and rationale for audit, but it does not become reviewed evidence and cannot enter a candidate set.

Before conversion, the reviewer must explicitly approve the exact existing process activity, exact closed formal target, typed value, knowledge state, evidence classification, mapping rationale, and supporting reviewed evidence. The target catalogue is limited to the ten existing `CriterionName` fields, `human_accountability_required`, the ten existing `CapabilitySignalName` fields, and activity-level supporting evidence without a scalar value. Criterion values are reviewer-approved integers `0–5` or unknown; accountability and capability-signal values are reviewer-approved `true`, `false`, or unknown. Suggested gate relevance is explanatory only. The conversion service snapshots these approvals without deriving values from prose, model suggestions, document categories, or Preliminary results and without mutating the approved process, satisfying a gate, invoking an engine, or creating an outcome, approval, or Decision Package.

`READY_TO_ATTEMPT` means only that processing is complete or explicitly excluded; every current proposal has a terminal human-review disposition; every accepted or corrected item has an approved formal mapping or is explicitly context-only; at least one mapped documented fact or reviewed inference has a human-approved non-null formal value; the immutable candidate set contains every current review revision; and lineage and integrity checks pass. Unknowns and conflicts remain visible and allowed but do not count as the required positive mapped candidate. Readiness never claims evidence sufficiency or predicts a gate result. A user without supporting evidence is offered **Explore this process instead**; route switching preserves the formal lifecycle, documents, reviews, conversions, and all Preliminary history.

Implementation remains ordered and separately authorizable: (1) frozen domain contracts, (2) isolated additive persistence, (3) upload and evidence extraction, (4) human review, (5) formal-input conversion, (6) default-off UI activation, and only later (7) separately authorized strict-assessment invocation. Persistence must be additive under the isolated Preliminary migration history, append-only and idempotent, reject stale or mixed lineage, and reject frozen workspaces before DDL, writes, or sidecars. Safe backout disables explicit supporting-evidence service/UI construction while retaining immutable history. Supporting Evidence Slice 1—domain contracts only—is designed and ready for separate implementation authorization; no implementation is authorized by this decision alone.

### D-037 — Approve optional-evidence formal-run authorization and strict-execution design

Date: 2026-10-05
Status: Approved design; implementation requires separate slice authorization

Additional supporting documents are optional for an Organisational Assessment. After the existing process document is extracted and its process is validated and approved, the user is asked whether to **Add supporting evidence** or **Continue with current document**. The latter path may explicitly attempt the strict four-gate assessment from the exact active approved-process review and its source/extraction lineage alone. This binding correction supersedes only D-036's requirement to offer Explore instead when no supporting evidence exists; `formal-evidence-readiness.v0.1` remains unchanged as readiness for a prepared supporting-evidence candidate set and is never fabricated for a source-only run.

Adopt two exact authorization modes: `APPROVED_PROCESS_ONLY` and `APPROVED_PROCESS_WITH_SUPPORTING_EVIDENCE`. Both require the active `preliminary-formal-lifecycle.v0.1`, exact approved-review/process/source lineage, explicit user confirmation, and pinned policy, engine, input-adapter, guidance-catalogue, and output identities. Process-only authorization requires null candidate/readiness references and records whether no supporting evidence existed or the exact current supporting history was explicitly excluded for that run. Supporting-evidence authorization additionally requires the exact current `formal-input-candidate-set.v0.1` and its matching current `READY_TO_ATTEMPT` `formal-evidence-readiness.v0.1`. Uploaded but incomplete, stale, unresolved, or unused evidence is never silently ignored: the user must finish and use it or explicitly exclude it from that run; all records remain immutable for future use.

The approved frozen contract family comprises `formal-assessment-input-choice.v0.1`, `formal-assessment-authorization.v0.1`, `formal-input-conflict-resolution.v0.1`, `formal-assessment-input-projection.v0.1`, `formal-assessment-run-manifest.v0.1`, `formal-assessment-run-event.v0.1`, `formal-assessment-result.v0.1`, `formal-assessment-result-supersession.v0.1`, `formal-assessment-run-request.v0.1`, and `formal-evidence-guidance.v0.1`, under `formal-assessment-run-store.v0.1` / `0.1.0`. The explicit deterministic adapter identities are `formal-four-gate-input-adapter.v0.1` / `0.1.0` and `formal-four-gate-input-adapter-rules.v0.1`; the strict run pins `four-gate-assessment-engine.v0.1` / `0.1.0`, existing `decision_policy.v0.3` / `0.3.0`, and the existing `phase1-v0.4` engine result contract. Any persistence is a later separately authorized isolated additive migration 8 and must not alter migration 7, strict migrations, historical rows, or active strict pointers.

The adapter preserves the approved process structure, activity order, identities, and immutable review. Supporting mappings may fill an unknown approved-process target, while identical values may combine provenance without an additional resolution. If a known approved-process value conflicts with a reviewed supporting mapping, or reviewed supporting mappings conflict with each other, run authorization remains blocked until a human explicitly selects the effective value for that assessment run. The immutable run-scoped resolution records every competing typed value and its exact evidence/mapping provenance, the selected typed value, reviewer identity and locally declared authority, rationale, timestamp, request identity, and exact formal lifecycle/authorization/projection/run lineage. It is embedded in both authorization and the effective input projection and never rewrites the approved process, mappings, reviews, documents, or evidence history. Unresolved, context-only, rejected, unknown, conflict, or activity-evidence-without-value records never become positive scalar inputs.

The strict engine and four-gate rules remain unchanged. Unknowns remain null and may deterministically produce Discovery Required. `formal-evidence-guidance.v0.1` derives only from exact strict-engine blocking gaps through a fingerprinted catalogue; it is guidance for a future attempt, never accepted evidence and never LLM-authored. A later successful explicit run supersedes the prior current result by immutable lineage without deleting it; failed or interrupted attempts do not supersede results. Supporting-history changes do not retroactively corrupt a source-only result, while a supporting-evidence result becomes stale when its exact candidate/readiness lineage is no longer current. Safe backout disables explicit formal-run service/UI construction and retains immutable history. Preliminary behavior, application/CLI defaults, formal approval, implementation authority, and Decision Package generation remain unchanged and disconnected. The corrected design is closed with no remaining product decisions.

## Resolved decisions

| ID | Resolution | Closed |
|---|---|---|
| O-001 | Add `NO_CHANGE_JUSTIFIED` as a separate Gate 1 disposition and seventh derived outcome. See D-014. | 2026-09-03 |
| O-002 | Use separate typed gate fields and a derived-only `outcome_code`. See D-014. | 2026-09-03 |
| O-003 | Use parallel strict versions, immutable pins, version-keyed adapters, additive writable migration-4 metadata, and virtual read-only pins for protected frozen databases; never convert historical results. See D-017. | 2026-09-03 |
| O-004 | Keep `strategic_criticality` out of framework v0.1; allow strategic considerations only in evidence-backed business-value rationale. See D-018. | 2026-09-03 |
| O-005 | Use rule-path-specific evidence materiality; known readiness blockers produce Process Improvement First and missing decision-material evidence produces Discovery Required. See D-015. | 2026-09-03 |
| O-006 | Use implementation complexity both as a Gate 2 readiness blocker and as an eligible-AI priority component. See D-015. | 2026-09-03 |
| O-008 | Use the versioned five-stage deterministic preliminary rule set, stable deciding codes, corrected residual-risk handling, and auditable decision-input trace. See D-030. | 2026-09-28 |
| O-009 | Use path-material activity confidence and weakest-activity process aggregation. See D-030. | 2026-09-28 |
| O-010 | Treat non-documentary human-supplied information as context only. See D-030. | 2026-09-28 |

## Open decisions

| ID | Decision required | Why it matters |
|---|---|---|
| O-007 | Should the incomplete Phase 9A-0c Case C observation be completed before or after the four-gate migration design? | It may inform evidence design, while the four-gate work changes a broader product contract. |

## Decision protocol

When an open decision is resolved:

1. Add a dated decision entry with status and reason.
2. Mark the corresponding open item resolved; do not erase it.
3. Update the affected canonical files.
4. If behavior changes, assign a new policy/schema/version where applicable.
5. Record approved-but-unimplemented target state explicitly; record implemented state only after implementation and verification.

Historical decision records inside older documents remain valid descriptions of their own time unless explicitly superseded here.
