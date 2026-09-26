# Project Decisions

Status: **CANONICAL DECISION LOG**  
Last updated: **2026-09-05**

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

## Resolved decisions

| ID | Resolution | Closed |
|---|---|---|
| O-001 | Add `NO_CHANGE_JUSTIFIED` as a separate Gate 1 disposition and seventh derived outcome. See D-014. | 2026-09-03 |
| O-002 | Use separate typed gate fields and a derived-only `outcome_code`. See D-014. | 2026-09-03 |
| O-003 | Use parallel strict versions, immutable pins, version-keyed adapters, additive writable migration-4 metadata, and virtual read-only pins for protected frozen databases; never convert historical results. See D-017. | 2026-09-03 |
| O-004 | Keep `strategic_criticality` out of framework v0.1; allow strategic considerations only in evidence-backed business-value rationale. See D-018. | 2026-09-03 |
| O-005 | Use rule-path-specific evidence materiality; known readiness blockers produce Process Improvement First and missing decision-material evidence produces Discovery Required. See D-015. | 2026-09-03 |
| O-006 | Use implementation complexity both as a Gate 2 readiness blocker and as an eligible-AI priority component. See D-015. | 2026-09-03 |

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
