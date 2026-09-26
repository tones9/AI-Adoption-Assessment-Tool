# Four-Gate GRW/M2 Same-Contract Design v0.1

Status: **PROPOSED DESIGN — NOT IMPLEMENTED**  
Date: **2026-09-05**  
Scope: successor evidence continuation and controlled reassessment only.

## 1. Purpose and boundary

The four-gate baseline is now available through Phase 6, persistence, presentation, and read-only DCW. Existing GRW M1 and M2 remain legacy-only because they hard-code legacy recommendation, technical-fit, and `data_readiness` meanings.

This design defines a future successor-only evidence and reassessment family. It must never adapt, reinterpret, or write a legacy GRW/M2 artifact. It is not an authorization to implement code.

## 2. Recommended successor family

Use a separate schema family named `grw-m2-four-gate-v0.1`. A run accepts only a complete, hash-pinned baseline chain containing:

- `ApprovedProcessReview` (`phase4-v0.1`);
- `FourGateIntegratedAssessmentSuccess` (`phase5-v0.2`, embedding `phase1-v0.4`);
- `FourGateDecisionPackageSuccess` (`phase6-v0.2`);
- `four-gate-framework.v0.1`;
- `decision_policy.v0.3` / `0.3.0` and its exact fingerprint.

The family must use new versioned artifact models, new repository dispatch entries, and a separate successor service. Existing `grw-m2-m1-v0.1` models, services, persistence, UI, reports, and comparisons remain unchanged.

## 3. Eligibility and controlled scope

The first successor reassessment path is intentionally narrow:

1. The target activity has final `DISCOVERY_REQUIRED`.
2. The active blocking gap is at Gate 2 (`IS_IT_READY`).
3. The active blocking field is exactly `data_readiness`.
4. The run snapshots the baseline activity, blocking-gap ID/question, Gate 2 result, approved-review/process fingerprints, contract identity, policy fingerprint, and every baseline artifact ID/revision/hash.

Unknown repetition, predictability, AI fit, a priority-only gap, a contextual gap, an implementation-complexity blocker, Gate 1/3/4 discovery, and any complete non-discovery outcome are not eligible in v0.1. They remain visible as evidence needs but cannot start this controlled reassessment.

Reason: this preserves a one-field, document-supported change boundary while avoiding an accidental expansion into general framework revision.

## 4. Proposed successor artifact sequence

1. `RUN_MANIFEST` — complete same-contract baseline and one eligible Gate 2 data-readiness gap.
2. `DOCUMENT_SUBMISSION` — candidate supporting document, content hash, source label, submitter declaration.
3. `EVIDENCE_REVIEW` — human-reviewed locator, scope/time/source applicability, conflict status, limitations, and explicit permission.
4. `DATA_READINESS_RESOLUTION` — proposed `data_readiness` value/state only, mapped to `IS_IT_READY`, with required data-owner and criterion-reviewer declarations.
5. `REASSESSMENT_REQUEST` — exact one-field proposed change and all relevant artifact references.
6. `REASSESSMENT_APPROVAL` — explicit human approval; baseline remains active and immutable.
7. `SUCCESSOR_APPROVED_REVIEW` — successor projection differing only in the permitted data-readiness field, its evidence reference, and derived projection fingerprints/identifiers.
8. `SUCCESSOR_INTEGRATED_ASSESSMENT` — embeds only a successor `phase5-v0.2` success.
9. `SUCCESSOR_DECISION_PACKAGE` — embeds only a successor `phase6-v0.2` success.
10. `BASELINE_SUCCESSOR_COMPARISON` — same-contract typed comparison only.

Every artifact carries `grw-m2-four-gate-v0.1`, the baseline contract identity, and immutable references/hashes. Unknown artifact versions fail closed.

## 5. Evidence, approval, and projection rules

- A submitted document is only a candidate until human evidence review grants `CRITERION_RESOLUTION_AND_GATE_ADMISSIBLE` permission.
- Contradictory, partially overlapping, different-scope, stale, or unresolved evidence cannot directly resolve the target.
- The successor projection may change only `steps.<target>.characteristics.data_readiness` and add the reviewed document evidence needed to support it.
- All other process fields, criteria, accountability/capability inputs, activity evidence, baseline artifact payloads, baseline hashes, recorded outcomes, and frozen files remain unchanged.
- The same successor policy fingerprint must be loaded for reassessment. A changed policy, contract, baseline hash, reviewed document hash, target gap, or artifact reference makes the run stale/fail-closed before successor creation.
- Explicit human approval is required before successor projection. A successor never replaces the baseline.

## 6. Reassessment and package rules

The successor must invoke only the explicit four-gate Phase 5 and Phase 6 routes with the pinned v0.3 policy:

- `FourGateIntegratedAssessmentService` for Phase 5;
- `FourGateDecisionSupportPackageService` for Phase 6.

It must not invoke `IntegratedAssessmentService`, `DecisionSupportPackageService`, legacy M2 policy/instrument logic, or default policy loading.

The successor package may be created only after a valid successor integrated assessment. Existing baseline results are never recomputed, rewritten, or relabelled.

## 7. Same-contract comparison contract

The comparison records baseline and successor as two immutable snapshots of the same four-gate contract. It may compare:

- the one approved `data_readiness` value/state/evidence change;
- decision status;
- change disposition;
- readiness disposition;
- selected intervention family;
- autonomy ceiling;
- derived outcome;
- four ordered gate statuses and only their persisted rationale/evidence references;
- priority status and score where applicable.

It must not compare legacy recommendation modes with successor outcomes, call one framework “better,” infer a positive movement from a changed outcome, or make deployment/ROI claims.

## 8. DCW and UI behavior

After implementation, successor DCW may expose this path only when the eligibility conditions in section 3 are met. For every other four-gate baseline, DCW continues to show the current explicit deferred/unavailable state.

The UI must state that the baseline remains the official immutable decision and that a successor is a separately approved, same-contract reassessment. Contract IDs, artifact IDs, hashes, evidence locators, and comparison details remain in technical detail.

## 9. Persistence and frozen boundaries

- Use new successor GRW/M2 serialization and repository dispatch keyed by type plus `grw-m2-four-gate-v0.1`.
- Do not modify migration-1–3 protected files, legacy M2 payloads, legacy M2 tables/meaning, or frozen portfolio artifacts.
- Do not create successor continuation in a protected frozen workspace.
- Keep writable successor-run data additive and parent-chain constrained to the exact four-gate baseline.

## 10. Required future acceptance tests

1. A legacy baseline cannot create a successor-family run; a successor baseline cannot create a legacy M2 run.
2. Non-discovery and non-Gate-2-data-readiness successor baselines are unavailable without writes.
3. A valid same-contract baseline snapshots every contract ID, policy fingerprint, artifact ID/revision/hash, target step, and gap.
4. Evidence conflict, scope, authority, permission, document hash, policy fingerprint, baseline hash, or target-gap mismatch fails closed.
5. Projection changes exactly one data-readiness field and only the required evidence set.
6. Reassessment invokes only explicit four-gate Phase 5/6 services.
7. Successor Phase 5/6 artifacts retain exact versions and same-contract lineage.
8. Comparison covers typed fields/four gates only and never legacy modes.
9. Baseline payloads/hashes/outcomes and protected frozen database bytes remain unchanged.
10. Legacy GRW/M2, DCW, UI, persistence, and frozen-workspace tests remain unchanged.

## 11. Approval required before implementation

Approve or amend all of the following before sending an implementation prompt:

- the separate `grw-m2-four-gate-v0.1` schema family;
- Gate 2 `data_readiness` discovery as the sole v0.1 eligibility path;
- the exact one-field projection boundary;
- same-contract typed comparison only;
- explicit v0.3 Phase 5/6 invocation and policy pinning;
- continued unavailability for every other successor gap/path;
- additive writable persistence and absolute frozen-workspace exclusion.
