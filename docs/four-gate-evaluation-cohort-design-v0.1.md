# Four-Gate Successor Evaluation Cohort Design v0.1

Status: **DECISION-READY SUCCESSOR EVALUATION DESIGN — NOT IMPLEMENTED**  
Date: **2026-09-06**  
Scope: a new governed evaluation cohort for the explicit four-gate successor route only.

## 1. Purpose and boundary

The successor route is implemented through `phase1-v0.4`, `phase5-v0.2`, `phase6-v0.2`, version-keyed persistence/presentation, and one narrowly controlled data-readiness reassessment path. It is explicit and non-default. The frozen Phase 8 portfolio evaluates the legacy `decision_policy.v0.2` route and remains historical evidence only.

This design creates a separate cohort, `four-gate-evaluation-cohort.v0.1`, to test whether the successor contract is executed faithfully and produces auditable, evidence-grounded outputs on new governed cases. It does **not** validate predictive accuracy, business value, ROI, deployment readiness, realised adoption outcomes, threshold quality, or generalisation.

The cohort must never:

- alter or reopen any frozen legacy portfolio artifact, database, JSON, Markdown, hash, manifest, or conclusion;
- regenerate a legacy portfolio case under the successor and present it as comparable historical evidence;
- map legacy recommendation modes to the seven successor outcomes for an accuracy score;
- change production defaults, policy values, decision logic, UI workflow, persistence schemas, or reassessment eligibility;
- use after-state material when preparing, reviewing, annotating, or freezing the before-state decision.

## 2. Cohort identity and contract pinning

Every cohort, case, run, annotation, and report must record these exact pins:

| Field | Required value |
|---|---|
| Cohort protocol | `four-gate-evaluation-cohort.v0.1` |
| Framework | `four-gate-framework.v0.1` / `0.1` |
| Decision policy | `decision_policy.v0.3` / `0.3.0` plus SHA-256 fingerprint |
| Phase 1 | `phase1-v0.4` |
| Phase 5 | `phase5-v0.2` |
| Phase 6 | `phase6-v0.2` |
| Reassessment family, if used | `grw-m2-four-gate-v0.1` |
| Source/document bytes | SHA-256 and immutable source identifier |

Unknown, mixed, malformed, or unpinned contracts fail closed and are excluded from all aggregate statements. A changed policy fingerprint, source hash, approved review, or annotation revision starts a new run or cohort revision; it never overwrites an existing result.

## 3. Case design and separation

Use two deliberately separate sets:

1. **Development fixtures** — synthetic, controlled cases used only to verify the cohort harness. They are excluded from every descriptive or confirmatory claim.
2. **Governed successor cases** — new source-provenance case packets with a case manifest, source hash, before-only boundary, review/approval record, independently prepared reference annotation, run record, and freeze manifest.

Each governed case must be labelled as one of:

- `DESCRIPTIVE_ONLY`: sufficient for contract, traceability, and workflow observations;
- `REFERENCE_ANNOTATED`: additionally has a blinded, adjudicated before-state reference suitable for predeclared agreement measures.

Do not require a numeric minimum cohort size before learning from the process. Report all case counts and case-level results. Any aggregate with too few comparable observations is **not applicable**, not zero and not a performance claim.

## 4. Before-state, human review, and reference controls

For every governed case:

1. Freeze the source document bytes and source metadata before extraction/review.
2. Preserve extraction candidates, reviewer edits, retained unknowns, evidence references, approval event, and approved-review fingerprint.
3. Freeze the approved before-state review before running the successor assessment.
4. If a reference annotation is used, prepare it from the same before-state source without engine output, policy thresholds, gate results, package text, or later reassessment artifacts.
5. Record annotator role declarations, annotation version, disagreements, adjudication rationale, and the final frozen reference.
6. Run the explicit successor policy/Phase 5/Phase 6 route only after those prerequisites are complete.

The product reviewer and the independent reference annotator may be the same person only for `DESCRIPTIVE_ONLY` cases. A `REFERENCE_ANNOTATED` case requires separation or a documented independent adjudication review. The output reader must not use outcome labels to retrospectively edit the reference.

## 5. What to measure

The primary evidence is case-level, not a single score.

### 5.1 Contract and traceability measures — required for every governed case

- exact contract/policy/version pin validity;
- approval gating validity;
- four ordered gate results with correct not-evaluated behavior;
- valid typed-field and derived-outcome combination;
- evidence-reference resolution for every decision-material claim;
- active blocker versus contextual/priority gap classification;
- retained-unknown completeness;
- deterministic semantic-JSON repeatability for identical approved input/policy;
- package/report section completeness; and
- frozen/baseline immutability checks where the data-readiness reassessment path is exercised.

### 5.2 Agreement measures — only for `REFERENCE_ANNOTATED` cases

- Gate 1 change-disposition agreement;
- Gate 2 readiness-disposition agreement and active-blocker field agreement;
- Gate 3 intervention-family agreement after conventional-first precedence;
- Gate 4 autonomy-ceiling agreement only when an AI candidate reaches Gate 4;
- derived-outcome agreement, reported alongside the typed fields rather than alone;
- material-evidence support rate; and
- unknown-retention agreement for decision-material fields.

For each measure, report numerator, denominator, missing/not-applicable reasons, and the full case-level confusion table where a categorical comparison is meaningful. Never force a Gate 3 or Gate 4 score when that gate was correctly not evaluated.

### 5.3 Safety and boundary observations — descriptive only

Report counts and case narratives for:

- unsupported automation or autonomy suggestions relative to the adjudicated reference;
- conventional-solution precedence being missed;
- process-improvement inferred from missing information;
- missing material evidence incorrectly treated as sufficient;
- contextual evidence incorrectly blocking a decision;
- AI safety veto representation; and
- cross-contract, frozen-workspace, or baseline-immutability refusal.

These observations are not rate claims until the cohort and reference process are sufficiently mature and a later protocol explicitly authorizes them.

## 6. Controlled reassessment sub-study

The `grw-m2-four-gate-v0.1` flow may be exercised only as a labelled sub-study on an eligible case. It must use one active Gate 2 `data_readiness` Discovery Required gap, an explicit human-reviewed UTF-8 supporting document, explicit resolution/request/approval, and the pinned successor contract.

Record baseline and successor separately. The result may describe a typed same-contract decision difference after one reviewed field change. It must not claim that the successor is better, correct, implemented, or commercially beneficial. All other gaps and repeated reassessment remain out of scope.

## 7. Artifact and freeze layout

Create new cohort-owned directories and manifests; never write beneath `evaluation/portfolio/` or mutate existing Phase 8 files. The later implementation should use a layout equivalent to:

```text
evaluation/four_gate_cohorts/<cohort-id>/
  cohort_manifest.v0.1.json
  protocol.md
  cases/<case-id>/
    case_manifest.v0.1.json
    source/                    # frozen before-state source copy or immutable locator
    review/                    # candidate, review, approval, and hashes
    reference/                 # only when reference-annotated; access controlled until freeze
    successor_run/             # explicit Phase 5/6 artifacts and hashes
    reassessment/              # optional controlled sub-study artifacts
    result.v0.1.json
    freeze_manifest.v0.1.json
  cohort_summary.v0.1.json
  cohort_summary.v0.1.md
```

Each case freeze must hash every listed output, record the before/after access boundary, and state whether it is development, descriptive-only, or reference-annotated. Successor cohort results are new research artifacts, not production workspace artifacts and not a replacement for the legacy portfolio.

## 8. Reporting language

Permitted language:

- “The explicit successor contract produced this pinned, auditable result on this governed case.”
- “The case showed agreement/disagreement with this predeclared before-state reference.”
- “This measure is not applicable because the required gate/path was not reached.”
- “This cohort is descriptive and does not establish effectiveness or generalisation.”

Forbidden language:

- “The successor outperformed the legacy portfolio.”
- “The policy is validated/accurate/production-ready.”
- “The reassessment improved the business outcome.”
- “The AI recommendation is safe in deployment.”

## 9. Implementation sequence and acceptance tests

Implementation is separately authorized only after the approval items below are closed.

1. Add an isolated evaluation contract/harness that imports successor contracts but is never imported by production code.
2. Add synthetic development fixtures and verify source-hash, pinning, freeze, repeatability, and report generation.
3. Add governed case manifests and the before/reference access controls.
4. Add agreement and descriptive-observation aggregation that preserves case-level denominators and not-applicable states.
5. Add an optional, separately labelled data-readiness reassessment sub-study adapter.
6. Verify the existing legacy Phase 8 portfolio hashes and frozen artifacts remain unchanged.

Minimum acceptance tests:

- a legacy Phase 8 artifact cannot be accepted as a successor cohort case;
- a missing/mixed/changed contract or policy fingerprint fails closed;
- after-state/reference access is denied before the specified freeze point;
- identical approved input and policy produce byte-stable successor semantic output;
- not-evaluated gates and not-applicable measures are preserved, not scored as failures or zeros;
- a case-level report contains all contract, lineage, and denominator disclosures;
- the optional reassessment sub-study refuses every ineligible or frozen baseline;
- production packages do not import cohort code; and
- existing Phase 8 hash/boundary tests remain unchanged.

## 10. Approval items

The following recommendations require explicit approval before Codex receives an implementation prompt:

1. Adopt `four-gate-evaluation-cohort.v0.1` as a new, separate descriptive cohort rather than modifying Phase 8. **Recommended.**
2. Use synthetic development fixtures first, then new governed cases; do not set a numeric confirmatory sample threshold now. **Recommended.**
3. Permit agreement measures only for blinded, independently adjudicated `REFERENCE_ANNOTATED` cases. **Recommended.**
4. Keep the controlled data-readiness reassessment as an optional labelled sub-study, not a core cohort requirement. **Recommended.**
5. Do not make effectiveness, ROI, deployment-safety, or generalisation claims from this cohort. **Recommended.**
