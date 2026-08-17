# Phase 9A-0c — observation plan

Status: **APPROVED — NOT YET EXECUTED**
Version: v0.1
Date: 2026-08-15
Nature: **strictly observational.** No code, UI, policy, taxonomy or threshold change occurs during 9A-0c. Any limitation discovered becomes a recorded finding for a later, separate decision.

---

## 1. Purpose

Fix 0 restored the ability to record where a criterion value came from. The 9A-0a boundary test already proves the mechanism works. 9A-0c is not a re-test of that; it exists to answer the question that decides whether further evidence-model work is required:

> **Can real source documents evidence the six gate-material criteria?**

Where they cannot, the observation must separate two failure modes with entirely different remedies:

| Failure mode | Meaning | Implied remedy |
|---|---|---|
| `STATED_BUT_UNCITABLE` | The document states the fact, but the extraction never resolved that block, so Fix 0's picker cannot offer it | Block-level evidence selection. Small; no contract change. |
| `NOT_STATED` | No process document of this kind would contain the fact | Attestation or measured data. Contract change; the §4 decision. |

Conflating these would risk concluding that attestation is needed when the real gap is a larger evidence picker. **Separating them is the primary deliverable of 9A-0c.**

9A-0c measures evidence reachability, not recommendation quality. A case that evidences its criteria and is then correctly declined by the policy is a successful observation. See §7.1.

---

## 2. Frozen baseline

| Item | Value |
|---|---|
| Commit | `de34e074eb2ec82bd34a36c23de25356660244f0` (`de34e07`) |
| Production subtree fingerprint | `3c5c86bd132d25745ee7fcba2e40c3e3d796a9ff404a36a93aecce60cbaf1a85` |
| Decision policy | `decision_policy.v0.2`, version `0.2.0`, fingerprint `b72e528b102bf893b45e6de9ec311e0888341d12b8aa3f99b8047e324d6a6d66` |
| Phase 1 contract | `phase1-v0.3` |
| Extraction configuration | `extraction.v0.1`, model `gpt-5.6-terra` |
| Phase 8 reference fingerprint | `4deca425…` — retained as the permanent reference for the frozen PORT runs |

The fingerprint must be re-verified as `3c5c86bd…` immediately before each case and recorded with the result. Any change invalidates the observation.

---

## 3. Cases

### Case A — bundled synthetic demo (plumbing check only)

Input: `data/demo/synthetic_complaint_process.txt`, SHA-256 `84d321005892a0c9071df71ed70fca13e6b0d8c3474ece82c05d213d0d3983bb`. Offline demo mode; no provider call.

Run through the **actual Streamlit UI**, since this is the only case that exercises the real product surface.

**Case A is explicitly not evidence that the product is ready.** It is an end-to-end plumbing check that Fix 0 functions when evidence exists. A synthetic fixture designed for demonstration tells us nothing about real-document reachability. If Case A fails, Fix 0 is broken and B/C are meaningless; if it passes, nothing is thereby proven about real documents.

### Case B — PORT-003 BEFORE (thin public description)

Input: `evaluation/portfolio/product_inputs/port-003.before.txt`, SHA-256 `79237f4d0164a2d6c3747fca3baf1e4f92613bc5c29b367eca0d8add7428441b`.

Operated on a **scratch copy** outside the portfolio tree. No frozen artefact is read-write, no live provider call is required, and no PORT-003 output is altered.

**Containment rules, mandatory:**

- Outputs are written to `docs/observations/9a-0c/` and **never** to `evaluation/portfolio/`.
- Every output carries a header stating it is a Phase 9A diagnostic, not a portfolio case and not a PORT-003 re-run.
- Case B does not receive a case ID in the portfolio register and is excluded from any cross-case count.

**Disclosed contamination:** the analyst has read the PORT-003 AFTER packet. This is tolerable only because the criterion rule in §5 is mechanical — *does this document literally state this fact* — rather than a judgement about what the process needs. The exposure is recorded with the result regardless.

### Case C — a real operational document (decisive case)

A genuine SOP, work instruction or runbook: the document class the product is designed for. Requires a live provider call and therefore **separate explicit approval** under the project's external-API rules.

If Case C cannot be run, 9A-0c can speak only to synthetic and thin-public documents, and the §4 decision remains partly speculative. That must be recorded as a limitation rather than glossed.

#### 3.1 Case C minimum acceptance checklist

Assessed and recorded **before** the document is ingested. A document failing any mandatory item is unsuitable and a different one is sought.

**Content — the document must plausibly exercise the product**

| # | Requirement | Mandatory |
|---|---|---|
| C1 | At least four discrete, named activities that can be enumerated or sequenced | yes |
| C2 | Actors or roles identified for at least some activities | yes |
| C3 | Inputs and outputs identifiable for at least some activities | yes |
| C4 | At least one decision point, branch or exception path | yes |
| C5 | At least one stated operational constraint — volume, frequency, timing, quality requirement, control or consequence of error | yes |
| C6 | Describes current state, not a future or proposed process | yes |

**Technical**

| # | Requirement | Mandatory |
|---|---|---|
| C7 | Text-native PDF, plain text or pasted text. **No OCR** — Phase 2 does not support scanned documents | yes |
| C8 | Within the chunking envelope, or knowingly chunked: 40,000 characters and 30 non-empty blocks per chunk | yes |

**Data handling**

| # | Requirement | Mandatory |
|---|---|---|
| C9 | Reviewed for confidential, commercially sensitive or personal data before transmission. Case C sends a real internal document to a third-party API | yes |
| C10 | Anonymised or redacted where C9 requires it, with the redaction recorded | conditional |

#### 3.2 Selection-bias control

**The checklist establishes that a document is a fair test of the product. It must not be used to select a document that will produce a favourable result.**

C1–C6 concern whether the document describes a process in enough detail to be assessed at all. None of them asks whether the document states values for the six gate-material criteria — deliberately. A document that describes its process well but states nothing about data readiness or error consequence is exactly the observation 9A-0c needs; screening such documents out would guarantee the conclusion.

Therefore:

- The document is chosen and accepted against C1–C10 **before** anyone examines whether it evidences criterion values.
- The selection, and the reason for it, is recorded before ingestion.
- If a first document is rejected, the rejection and its cause are recorded. Rejecting documents until one produces a good result is selection bias and would invalidate the observation.

---

## 4. Allowed and forbidden inputs

**Allowed**

- The case source document.
- Evidence the extraction already resolved on the step under review.
- The unchanged decision policy and extraction configuration.

**Forbidden**

- **Operator knowledge not present in the document.** This is the crux: admitting it would pre-empt the very decision 9A-0c exists to inform.
- Inference from industry norms.
- Invented risk, volume, ROI or data-readiness values.
- For Case B: AFTER material, the PORT-003 provenance manifest, leakage audit and source captures.
- Any modification to a frozen Phase 8 artefact.

---

## 5. Pre-registration

Recorded and committed **before** any case runs.

**Criterion determination rule.** A criterion may be set only where a specific sentence of the document states the fact. The sentence is recorded verbatim alongside the value. Where no sentence states it, the criterion remains unknown and is classified `NOT_STATED`. Where a sentence states it but no resolved evidence on that step exposes it, the criterion remains unknown and is classified `STATED_BUT_UNCITABLE`, with the sentence recorded.

**Prediction.** Before running, predict per case which of the ten criteria will be evidenceable and which of the six gate-material ones will be satisfied. Predictions are committed first, then compared against the result. This is the anti-tuning control and mirrors the Phase 8 AFTER-seal discipline.

**Single determination.** Criterion values are decided from the document once, before any engine output is seen. They are not revised after observing a recommendation. If a re-run occurs for a technical reason, both runs and the reason are recorded.

---

## 6. Measurement table

Recorded per case, per step.

| Field | Type | Notes |
|---|---|---|
| `case_id` | A / B / C | |
| `step_id`, `activity` | text | |
| `criteria_evidenceable` | count of 10 | plus the list |
| `material_criteria_satisfied` | count of 6 | `ai_capability_fit`, `data_readiness`, `business_value`, `human_judgement_requirement`, `risk_consequence`, `residual_risk_with_human_oversight` |
| `human_accountability_evidenced` | bool | also gate-material |
| `furthest_gate_reached` | enum | `evidence_sufficiency` → `technical_fit` → `business_value` → `risk_and_autonomy` → `scored` |
| `recommendation_mode` | enum | recorded, never targeted |
| `priority_score` | number or null | with `priority_missing_criteria` when null |
| `blocked_criteria` | list | **each classified `STATED_BUT_UNCITABLE` or `NOT_STATED`, with the source sentence where one exists** |
| `capabilities_mapped` | list | relevant because `gates.py:175` declines when empty regardless of score |
| `fingerprint_at_run` | sha256 | must equal `3c5c86bd…` |

The `blocked_criteria` classification is the deliverable. Everything else is context.

---

## 7. Decision thresholds

Fixed now, before any data exists.

1. **Any case reaches a scored recommendation on document evidence alone** → Fix 0 is materially sufficient for that document class. Attestation becomes an enhancement rather than a blocker.
2. **≥60% of blocked material criteria are `STATED_BUT_UNCITABLE`** → the next step is block-level evidence selection ("Fix 0.5"), *not* attestation.
3. **≥60% are `NOT_STATED`** → attestation or measured-data ingestion is required; proceed to the §4 contract decision in `phase9a-criterion-evidence-design-v0.1.md`.
4. **Mixed, neither reaching 60%** → both are required, sequenced by count.

The denominator is blocked *material* criteria across all executed cases, excluding Case A, which is a plumbing check and carries no evidential weight for this decision.

### 7.1 What a successful observation is — and is not

**Success is not `AUTOMATE` or `AUGMENT`.** 9A-0c measures *evidence reachability*: whether a real document can supply the criteria the policy needs. What the policy then decides is a separate matter and is recorded, never targeted.

A case is a **successful observation** when the criterion values were determined from the document under the §5 rule, the engine consumed them, and the outcome and the reason for it were recorded. That holds regardless of which recommendation appears.

In particular, this sequence is a **complete success** for 9A-0c:

1. criteria are evidenced from the document;
2. evidence sufficiency passes;
3. the engine still returns `DO_NOT_RECOMMEND`, because no capability is mapped to the activity (`gates.py:175`) or another policy rule correctly declines.

That is the product working. The evidence layer delivered what the policy asked for, and the policy exercised judgement on it. The 9A-0a domain test already produced exactly this outcome, and it was recorded as a policy result rather than a defect.

Correspondingly:

- `DO_NOT_RECOMMEND` is a valid, recorded observation. It is **not** a failure and **not** a reason to revisit criterion values, thresholds or the taxonomy.
- `INVESTIGATE_FURTHER` caused by genuinely absent evidence is the central measurement of this exercise, not a disappointing result.
- A case in which nothing at all could be evidenced is still a successful observation, and a highly informative one: it is direct evidence for the §7 decision.

The only genuine failure modes for 9A-0c are procedural: the fingerprint changing mid-run, the §5 rule not being followed, criterion values being revised after seeing an outcome, or the product being modified during the observation.

---

## 8. No tuning will occur based on these results

Explicitly and without exception, for the duration of 9A-0c:

- No decision-policy threshold, weight, gate or scoring band is changed.
- No capability-taxonomy change is made.
- No prompt, schema, model or extraction-configuration change is made.
- No production code change of any kind, including any limitation discovered mid-observation. Such a discovery is recorded as a finding and deferred.
- No criterion value is revised after seeing an engine output.
- `INVESTIGATE_FURTHER` and `DO_NOT_RECOMMEND` are valid observations, not problems to be engineered away.

The purpose is to learn what the current product can and cannot do. Changing the product during the measurement would destroy the measurement — the same reasoning that governed the Phase 8 AFTER boundary.

---

## 9. Outputs

Written to `docs/observations/9a-0c/`:

- `prediction.v0.1.json` — committed before any run
- `observation.v0.1.json` — the measurement table
- `findings.v0.1.md` — classification counts, the §7 threshold applied, and recommended next step
- `hashes.sha256`

No Phase 8 artefact is modified. No file is added to `evaluation/portfolio/`.

---

## 10. Open items before execution

1. Is a Case C document available and does it satisfy §3.1? If not, record the limitation and proceed with A and B.
2. Case A requires manual Streamlit interaction by the operator; Cases B and C will be prepared as scripts for operator execution.
3. Case C requires separate approval for a live provider call, and the §3.1 C9/C10 data-handling review must be completed before transmission.
