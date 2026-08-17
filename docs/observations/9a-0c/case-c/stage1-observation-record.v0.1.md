# Phase 9A-0c Case C — Stage 1 observation record

Status: **STAGE 1 COMPLETE — NOT REVIEWED, NOT ASSESSED, NOT COMPARED**
Version: v0.1
Date: 2026-08-17
Governing protocol: `docs/phase9a-0c-observation-plan-v0.1.md`
Run directory: `docs/observations/9a-0c/case-c/production-run-v0.1/`

This record documents execution only. It draws no conclusion, compares nothing against the pre-registered prediction, and reaches no §7 threshold decision.

---

## 1. Safety gates

All gates passed before any state was created or transmitted.

| Gate | Value | Result |
|---|---|---|
| Frozen document SHA-256 | `2a8fba60b7264fb38dd6cd3e0308f6673245beffd47e82d855c423bb333a5f3f` | VERIFIED |
| Production subtree fingerprint | `3c5c86bd132d25745ee7fcba2e40c3e3d796a9ff404a36a93aecce60cbaf1a85` | VERIFIED |
| `OPENAI_API_KEY` present | — | PASS |
| Run directory absent or empty | — | PASS |
| Chunk plan count | 2 | MATCH |

Payload identity confirmed against the reviewed dry run:

| Payload | SHA-256 |
|---|---|
| system prompt | `39af13beb624c8c2c6fc2715e22864bf739d0bf41e83ca826a49b9ff97eab9dd` |
| chunk 1 user prompt | `ff19236e676909f844a509ffe70a40c1bb38ffdb68e0413d5f7617ecf35fa3bd` |
| chunk 2 user prompt | `d784518a16575cc14db3e0b146418e0eb9b289e370e04d285ad6dca34993fae7` |

The live run transmitted byte-identical prompts to those reviewed. This was expected by construction — the prompts derive only from `src/`, `config/` and the frozen document, all covered by the two hash gates — and is recorded as empirical confirmation.

---

## 2. Execution record

| Field | Value |
|---|---|
| `case_id` | C |
| `document_id` | `doc-2a8fba60b7264fb38dd6cd3e0308f6673245beffd47e82d855c423bb333a5f3f` |
| `ingestion_status` | `success` |
| `extraction_status` | **`partial`** |
| `extraction_run_id` | `extraction-631ddf7e-e1b3-45ab-b29b-18f840cdc3be` |
| `workflow_stage` | `candidate-ready` |
| `candidate_status` | `CANDIDATE / UNCONFIRMED PROCESS EXTRACTION` |
| `prompt_version` / `schema_version` | `process-extraction.v0.1` / `candidate-process.v0.1` |

---

## 3. Provider record

**3 application-level calls.** Expected 2; declared maximum with repair 4. Within the approved limit.

| # | Chunk | Attempt | Model | Request ID | Input | Output |
|---|---|---|---|---|---|---|
| 1 | `…f-chunk-0001` | 1 | `gpt-5.6-terra` | `resp_06cd08afa7580fbb016a8321ef53c081a28b849f85625b5e19` | 5,552 | 16,382 |
| 2 | `…f-chunk-0002` | 1 | `gpt-5.6-terra` | `resp_0f577df3ce7689ca016a8322596ebc87d2ab3c3cc3f3382179` | 2,588 | 6,522 |
| 3 | `…f-chunk-0002` | 2 | `gpt-5.6-terra` | `resp_0ad006d8343475f0016a83228c029c819d88e6f4007f9d8887` | 2,616 | 6,212 |

Totals: 10,756 input, 29,116 output tokens.

**Repair fired once, on chunk 2 only.** Chunk 1 succeeded on first attempt. `repair_attempts` is 1 and one repair was consumed, so the configured budget was exhausted for that chunk and not exceeded.

---

## 4. Extraction result

**8 candidate steps.** Five carry a known document order; three do not.

| Seq | `document_order` | Activity |
|---|---|---|
| 1 | known, 1 | Requesting to Fill a Position |
| 2 | known, 2 | Hiring Manager and Hiring Committee Identified |
| 3 | known, 3 | Candidate Approval |
| 4 | known, 4 | Offer of Employment |
| 5 | known, 5 | Onboarding a New Employee |
| 6 | **unknown** | developing a plan |
| 7 | **unknown** | provide feedback regarding expectations and performance |
| 8 | **unknown** | meet with the Hiring Manager |

Steps 1–5 correspond to the document's five numbered Steps. Steps 6–8 correspond to bullet points inside Step 5's onboarding list, promoted to activities without a document order.

### 4.1 Issues

**3 errors, all `ambiguous-snippet`, all on chunk 2:**

| Field path | Chunk |
|---|---|
| `steps[1].outputs` | chunk 2 |
| `steps[1].outputs.items[0]` | chunk 2 |
| `steps[2].actors.items[1]` | chunk 2 |

These errors are why `extraction_status` is `partial` rather than `success`.

**5 warnings, all `ambiguous-dependency`**, with no chunk or field path attached. Every dependency the extraction produced has an unresolved target:

| From step | Target label as extracted | Relationship knowledge state |
|---|---|---|
| 1 | `Approved ERF` | known |
| 2 | `Office of Human Resources` | known |
| 3 | `President or President's Designee` | inferred |
| 4 | `Candidate approval by the President or President's designee` | known |
| 5 | `Completion of new employee orientation training` | inferred |

All five name a document, a role or an event rather than another extracted step, so none resolved to a `target_candidate_step_id`. Recorded as an observation; no action taken.

---

## 5. Artefact hashes

| SHA-256 | File |
|---|---|
| `db4506279f9bf1fc0ed9a8f013398ad07264525b50994e53087cf4d7d5cbe133` | `candidate_extraction.json` |
| `a41a6bf386574303e087999cff2d7b6c46eb90732efec829864174e7ea7d7fd7` | `ingestion_result.json` |
| `f3355117791a4784f56f1c3e243510e6a24a44c30579fb25fef9cac1176e6bc0` | `run_state_after_extraction.json` |
| `419441f8469f4cbbafe21ff1c5e645466d2b196358caa77895b96cee8e8a144e` | `workspace.db` |

All four are confined to `production-run-v0.1/` as designed. Nothing was written elsewhere.

---

## 6. Deviations from the expected Stage 1 plan

Recorded as observations. None was acted on; nothing was changed in response.

**D1 — `extraction_status` is `partial`, not `success`.** Caused by the three `ambiguous-snippet` errors on chunk 2. The status is a legitimate contract value and the candidate was still produced.

**D2 — 3 provider calls, not 2.** One repair on chunk 2. Within the approved maximum of 4, and disclosed in the approval as a possibility.

**D3 — three `ambiguous-snippet` errors.** All on chunk 2, all concerning outputs and actors. Not present in either prior single-chunk portfolio run; whether that relates to chunking, document structure or content is not determined here.

**D4 — all five dependencies unresolved.** Every extracted dependency names an artefact, role or event rather than a step. This will matter at Phase 4, since the approval boundary requires a retained dependency to target another retained step. Noted for Stage 2 planning only; no decision taken.

**D5 — chunk 1 output near the configured ceiling.** 16,382 output tokens against `max_output_tokens` of 20,000, roughly 82% of cap. It did not truncate, but the margin is thinner than a reader might assume.

**D6 — three of eight steps have unknown `document_order`.** Steps 6–8 were promoted from a bullet list and carry no order value.

**D7 — operator-script reporting defect, in this script, not the product.** The live step list prints `{document_order.value}. {activity.value}`, so an unknown order renders as `None.` immediately before the activity text — e.g. `None. developing a plan`. This reads as though the activity is named "None." It is a display defect in `_run_case_c_stage1.py`, inherited from the PORT-003 operator script pattern. The underlying artefact is correct. **Not fixed**, per observation plan §8, which forbids any change during 9A-0c including one discovered mid-observation. Recorded for a later decision.

---

## 7. Boundary confirmation

| Boundary | State |
|---|---|
| Phase 4 human review | **NOT RUN** |
| Explicit approval | **NOT PERFORMED** |
| Assessment engine | **NOT RUN** |
| Decision-support package | **NOT GENERATED** |
| Any recommendation | **NOT PRODUCED** |
| Pre-registered prediction | **NOT OPENED, NOT COMPARED** |
| §7 threshold decision | **NOT REACHED** |
| Production code, policy, prompt, schema, taxonomy, thresholds | **UNCHANGED** |
| Production fingerprint after run | `3c5c86bd132d25745ee7fcba2e40c3e3d796a9ff404a36a93aecce60cbaf1a85` |

`workflow_stage` is `candidate-ready`, which is the stage this script is designed to stop at.

---

## 8. Not yet done

The observation is incomplete. Remaining, in order, each requiring its own decision:

1. Phase 4 source-bounded review and explicit approval.
2. Assessment engine and decision-support package.
3. Freeze of the complete Stage 2 output.
4. Opening the pre-registered prediction and comparing it against the observed result.
5. Classification of every blocked criterion as `STATED_BUT_UNCITABLE` or `NOT_STATED`.
6. Application of the §7 decision thresholds.

Steps 4 to 6 must not begin before step 3 is complete, on the same freeze-before-reveal principle the portfolio evaluation used.
