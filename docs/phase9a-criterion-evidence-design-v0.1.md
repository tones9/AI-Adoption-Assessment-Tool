# Phase 9A — Criterion evidence layer: design proposal

Status: **PROPOSAL — NOT APPROVED, NOT IMPLEMENTED**
Version: v0.1, amended 2026-08-15 (see Amendment A)
Depends on: Phase 8 complete (`phase8-complete`), production fingerprint `4deca425…`
Scope: design discussion only. No production code, policy, prompt, schema, taxonomy or test has been changed.

---

## Amendment A — the original premise was too large

This document was written assuming an evidence-contract change was needed before the product could function. **That assumption was wrong**, and is superseded by `phase9a-decision-review-v0.1.md`.

`correct_assertion(origin=DOCUMENT_SUPPORTED, evidence=[...])` already exists and works — the PORT-002 operator script used it. The review UI simply never calls it, passing no origin so every value defaults to `HUMAN_SUPPLIED`, whose evidence is then stripped during projection.

Empirically confirmed 2026-08-15: 43 ideal criterion values supplied through the real service projected as `value=5` with `evidence_ids=[]`, and all four activities returned `INVESTIGATE_FURTHER` on *"`ai_capability_fit` has no evidence reference"*.

Consequences for this document:

- **The first decision point is Fix 0** — exposing the existing `DOCUMENT_SUPPORTED` path in the review UI. No contract, policy, schema or taxonomy change. See §2A.
- **§3 and §4 are deferred.** `OPERATOR_ATTESTED`, measured data and tiered provenance are *future evidence-model work*, not decisions on the table now. They are retained here as design thinking, not as a proposal awaiting approval.
- Nothing in §3 or §4 should be implemented, versioned or costed until Fix 0 has landed and the product has been observed working as originally intended.

---

## 1. The defect Phase 8 exposed

Phase 8 concluded that the deterministic decision engine was never exercised because public BEFORE evidence lacks operational criterion values. That is true but it is a symptom. The underlying defect is structural:

> **No criterion value supplied by a human operator can ever satisfy a gate. The product cannot produce `AUTOMATE` or `AUGMENT` from operator input under any circumstances.**

### 1.1 Reproducible evidence chain

| # | Location | Behaviour |
|---|---|---|
| 1 | `config/decision_policy.v0.2.json` → `evidence.require_material_criterion_evidence_reference: true` | The six gate-material criteria must carry non-empty `evidence_ids`. |
| 2 | `presentation/pages/review.py:233, 241` | `Correct` and `Resolve unknown` call the service with no `origin` and no `evidence`, so both default to `HUMAN_SUPPLIED`. |
| 3 | `review/service.py:126` | `correct_assertion` raises if a `HUMAN_SUPPLIED` correction carries evidence. Human-supplied values *cannot* have evidence. |
| 4 | `review/approval.py:372` | `_collect_assertion_evidence` returns `[]` when origin is `HUMAN_SUPPLIED`. |
| 5 | `decision/gates.py:70-74` | `_input_problem` returns `"<criterion> has no evidence reference"` → gate fails. |

Net effect: operator input → `evidence_ids == []` → gate failure → `INVESTIGATE_FURTHER`. Always.

The only currently viable path for a criterion value is `DOCUMENT_SUPPORTED` with a resolved source snippet — and the review UI exposes no way to attach document evidence to a criterion even when the source document does state the fact.

### 1.2 Why the test suite did not catch it

`data/sample_processes/synthetic_customer_complaint_process.json` hand-authors criterion evidence:

```json
"ai_capability_fit": {
  "value": 5, "knowledge_state": "known",
  "evidence_ids": ["E1", "E2"]
}
```

The unit tests exercise all four recommendation modes against fixtures the real pipeline cannot construct. Engine logic is correct; the integration boundary between Phase 4 and Phase 1 is not. This is a genuine gap in test design, not in engine implementation.

### 1.3 Why this is not a Phase 8 failure

Phase 8 was correct to forbid inventing criterion values, and correct to report `INVESTIGATE_FURTHER`. Had the protocol permitted operator-supplied values, the runs would have produced the *same* result for a different reason, and the defect would have stayed hidden behind a plausible explanation. The negative result was informative precisely because it was clean.

**Consequence for Phase 8 artefacts:** none. They remain accurate and frozen. This document supersedes the *root-cause explanation* in XC-2, not its finding or its counts. No Phase 8 file should be edited.

---

## 2A. Fix 0 — the actual first decision point

**Expose the existing document-supported criterion path in the review UI.**

Add an origin selector and an evidence picker to the criterion review widget, so a reviewer setting a criterion value can cite a block already resolved in the ingested document. This calls a service method that already exists and is already tested at the unit level.

| Aspect | Impact |
|---|---|
| Contracts | none |
| Policy | none |
| Schema | none |
| Taxonomy | none |
| Files | `presentation/pages/review.py`, plus a new integration test |
| Fingerprint | changes (any `src/` edit does) |

Semantics restored: *"You may set a criterion value when the source document states the fact."* That was always the intended design; it was simply never wired to the interface.

**What Fix 0 does not solve.** Criteria that no process document ever states — `data_readiness`, `risk_consequence`, `residual_risk_with_human_oversight`, and usually `business_value` — remain unreachable. Fix 0 restores the intended capability; it does not complete the evidence model. Expect it to unblock some real cases partially and few completely.

**Why it still comes first.** It is the smallest change that makes the product behave as designed, it carries no contract risk, and it lets the §4 question be decided against an observed working system rather than in the abstract. It also forces the integration test whose absence allowed this defect to ship.

---

## 2. Design principles

1. **Symmetry.** Criterion judgements must carry provenance as rigorous as process facts already do.
2. **Non-equivalence.** An operator estimate must never be indistinguishable from a measured value or a document-supported fact.
3. **Anchored, not free-form.** A value must derive from a recorded observation, not an unexplained integer.
4. **Unknown stays unknown.** Nothing in 9A may make it easier to guess. It must become easier to *justify*, and no easier to fabricate.
5. **No hindsight tuning.** Thresholds must not move to make cases pass.

---

## 3. FUTURE EVIDENCE MODEL — deferred, not proposed

> Sections 3 and 4 describe possible future work. Per Amendment A they are **deferred until Fix 0 has landed**. Nothing here is awaiting a decision.

### 3.0 Where criterion values legitimately come from

Three sources, deliberately distinguishable:

| Source | Definition | Traceable to |
|---|---|---|
| `DOCUMENT_SUPPORTED` | The operational fact is stated in the ingested source document | Block ID, offsets, snippet (existing Phase 2/3 machinery) |
| `MEASURED` | Computed from operational data supplied by the operator (event log, ticket export, timing data) | Dataset identity, hash, computation method, computed figure |
| `OPERATOR_ATTESTED` | Anchored human judgement, recorded with the question asked and the answer given | Instrument ID, anchor question, operator answer, attestation timestamp |

`OPERATOR_ATTESTED` is the new concept. It is *not* today's `HUMAN_SUPPLIED`, which is an unstructured free-text rationale attached to a bare integer. It is a structured record: *this question was asked, this answer was given, that answer maps to this band under this instrument version.*

### 3.1 Proposed allocation per criterion

| Criterion | Primary source | Notes |
|---|---|---|
| `repetition` | `MEASURED` → attested fallback | Event-log case count, or an anchored volume question ("times per week"). |
| `predictability` | `MEASURED` → attested fallback | Variant analysis over an event log is the natural measure. |
| `data_readiness` | `OPERATOR_ATTESTED` | Organisational fact; no document will state it. |
| `ai_capability_fit` | **Candidate for derivation** — see §3.2 | Currently the single criterion that blocked all 16 activities. |
| `human_judgement_requirement` | `OPERATOR_ATTESTED` | |
| `business_value` | `OPERATOR_ATTESTED`, anchored to computable inputs | volume × handling time × loaded rate, recorded as inputs not a verdict. |
| `risk_consequence` | `OPERATOR_ATTESTED`, anchored to consequence categories | Legal / safety / financial / customer harm bands. |
| `residual_risk_with_human_oversight` | `OPERATOR_ATTESTED` | |
| `implementation_complexity` | `OPERATOR_ATTESTED` | |
| `conventional_solution_fit` | `OPERATOR_ATTESTED` | |

### 3.2 The `ai_capability_fit` opportunity

This criterion stopped all sixteen Phase 8 activities, and it is the one the product is best placed to determine itself. The pipeline already extracts capability signals with resolved document evidence — `creates_new_content` on the summary step of PORT-003, for example, cited a literal snippet.

A derived `ai_capability_fit`, computed from which capability signals are present and how directly they match the activity, would be **document-grounded and legitimately evidenced**, inheriting the signals' own evidence IDs.

This is the highest-value idea in this document and also the most dangerous. It changes policy semantics, and the temptation to calibrate the derivation so that Phase 8 cases would have passed is exactly the hindsight error the whole evaluation was built to avoid.

**Proposed constraint:** design the derivation from the taxonomy definitions alone, freeze it, and only then re-run the Phase 8 BEFORE inputs as a *observational* check. Whatever happens, do not adjust the derivation in response. If it still returns `INVESTIGATE_FURTHER`, that is a result, not a failure.

---

## 4. FUTURE — the evidence-contract question (deferred)

`require_material_criterion_evidence_reference: true` currently means *document evidence*. Three options, and this decision determines everything downstream:

**Option A — Attestation satisfies the requirement.**
`OPERATOR_ATTESTED` produces a first-class evidence record (instrument, question, answer, timestamp) that counts toward `evidence_ids`. Gates pass.
*Pro:* the product becomes usable as designed. *Con:* weakens "evidence" unless attestation is visibly second-class in every output.

**Option B — Attestation is tracked but does not satisfy the gate.**
Preserves current strictness. *Con:* the product remains structurally unable to recommend anything, for any real user. This is the status quo defect made explicit rather than fixed.

**Option C — Tiered evidence, per gate.**
The policy declares, per gate, which provenance tiers are acceptable. Low-consequence gates accept attestation; `risk_and_autonomy` might require measured or document evidence.
*Pro:* most defensible and most interesting to explain. *Con:* most work; policy schema change; new version.

**Recommendation: Option C**, with Option A as the pragmatic fallback if scope needs cutting. Option C is the design a reviewer would respect, and it makes the product's caution *configurable and explicit* rather than accidental.

All three require a new policy version and change the production fingerprint. That is expected and correct for Phase 9.

---

## 5. The elicitation instrument

A versioned artefact (`criterion_instrument.v0.1`), separate from the policy, containing per criterion:

- an **anchor question** with an observable referent;
- **band definitions** mapping answers to 0–5;
- an **explicit "I don't know"** that produces `UNKNOWN`, never a default;
- a **provenance prompt** asking how the operator knows.

Sketch for `repetition`:

> *How many times is this activity performed, and over what period?*
> `0` — less than monthly · `1` — monthly · `2` — weekly · `3` — daily · `4` — many times daily · `5` — continuously / high volume batch
> *How do you know? [system report | direct observation | estimate]*

The instrument version is recorded on every value, so a recommendation traces to *recommendation → gate → criterion → band → question → answer → operator → timestamp*. That completes the traceability chain that currently terminates at an unexplained integer.

---

## 6. Non-circular validation design (9B)

The circularity risk: if the same person supplies criterion values *and* judges whether the recommendation is right, nothing is measured.

Controls, reusing the Phase 8 freeze machinery:

1. **Role separation.** Value supplier ≠ judgement rater, wherever possible.
2. **Pre-registration.** Each rater records their own recommendation (`AUTOMATE` / `AUGMENT` / `INVESTIGATE_FURTHER` / `DO_NOT_RECOMMEND`) plus rationale, hash-frozen and committed, **before** seeing engine output. Identical discipline to the AFTER seal.
3. **Order of operations.** elicit values → freeze → rater judgements → freeze → run engine → compare.
4. **Measures.** Exact-agreement rate, adjacent-category agreement, and a written analysis of every disagreement. With a handful of processes, disagreement analysis is worth more than any percentage.
5. **Sensitivity (9C).** Perturb each criterion ±1 and record whether the recommendation flips. This measures threshold robustness and needs no raters at all.
6. **No tuning in the measuring pass.** Measure, freeze, then propose changes as separate, motivated work.

**If raters are unavailable,** Tier 2 collapses into self-assessment and must be abandoned rather than fudged. The honest fallback is 9C plus measured inputs from public process-mining logs, with a narrower claim.

---

## 7. Minimum viable milestone

**9A-M1: the first non-`INVESTIGATE_FURTHER` recommendation produced through the real pipeline.**

One real process the operator knows first-hand, end to end: ingest → extract → review → elicit criterion values through the instrument → approve → assess → package, producing a recommendation other than `INVESTIGATE_FURTHER` with a complete traceability chain from the recommendation to a recorded anchor answer.

That single run would demonstrate the product working as designed for the first time. It is small, unambiguous, and directly answers Phase 8's central limitation.

Sequence:

| Step | Deliverable | Status |
|---|---|---|
| **9A-0a** | Integration test asserting a reviewer-supplied criterion value reaches a gate — the test whose absence let this defect ship. Written first, expected to fail. | **decision point** |
| **9A-0b** | Fix 0 — review UI exposes origin selection and document-evidence attachment for criteria (§2A) | **decision point** |
| **9A-0c** | Observe: re-run a real process end to end and record what is now reachable and what still is not | **decision point** |
| 9A-1 | Decide the §4 contract question, informed by 9A-0c | deferred |
| 9A-2 | `criterion_instrument.v0.1` — ten anchored questions with bands | deferred |
| 9A-3 | Criterion provenance model + attestation evidence record | deferred |
| 9A-4 | Policy `v0.3` implementing the chosen evidence tiering | deferred |
| 9A-5 | Review UI exposes the elicitation instrument | deferred |
| 9A-6 | 9A-M1 run, frozen | deferred |

Only 9A-0a/b/c are live. Everything from 9A-1 onward is contingent on what 9A-0c shows.

Note on 9A-M1: with Fix 0 alone, a non-`INVESTIGATE_FURTHER` result requires a source document that states enough operational fact to evidence all six material criteria. That is uncommon but not impossible, and it is worth attempting before assuming the attestation model is required.

---

## 8. Constraints

- Do not modify any Phase 8 artefact. This document supersedes XC-2's root-cause explanation; the finding, counts and frozen bundles stand.
- Do not touch the capability taxonomy. The speech/transcription gap is a separate phase and must never be justified by PORT-003's AFTER evidence.
- Do not tune thresholds during 9B.
- The production fingerprint will change. Record the new one and the reason; the Phase 8 fingerprint remains the reference for those frozen runs.
- Add tests before changing behaviour, specifically 9A-6 — the current suite's blind spot is the reason this shipped.

---

## 9. Open decisions

**Live now:**

1. **Approve Fix 0** (§2A) as an isolated change, test-first, with no contract, policy, schema or taxonomy change?

**Deferred until 9A-0c is observed — do not decide these yet:**

2. §4 contract question — A, B or C.
3. Derive `ai_capability_fit` from extracted capability signals? High value, high hindsight risk; requires the freeze-then-observe discipline in §3.2.
4. Are raters available for 9B Tier 2? Determines whether the instrument must be reproducible by a stranger.
5. Is measured-data ingestion in scope, or deferred further?
