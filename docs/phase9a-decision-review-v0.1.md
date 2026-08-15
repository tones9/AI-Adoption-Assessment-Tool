# Phase 9A — Design review and decision document

Status: **REVIEW ONLY — NO IMPLEMENTATION DECISION TAKEN**
Version: v0.1
Phase 8 status: frozen at tag `phase8-complete`. Nothing in this document alters it.
Empirical confirmation: **completed 2026-08-15 — finding confirmed** (see §1.3).

---

## 1. Verification

### 1.1 Can a `HUMAN_SUPPLIED` criterion ever satisfy a material evidence requirement?

**No.** Confirmed by static analysis of four files.

| Step | Location | Behaviour |
|---|---|---|
| 1 | `review/approval.py:372` | `_collect_assertion_evidence` returns `[]` unconditionally when `origin is HUMAN_SUPPLIED`. |
| 2 | `review/approval.py:288, 325` | `_criterion` and `_boolean_data` both populate `evidence_ids` from that function. |
| 3 | `decision/gates.py:70-74` | `_input_problem` fails any material criterion whose `evidence_ids` is empty while `require_material_criterion_evidence_reference` is true. |
| 4 | `decision/scoring.py:_missing_priority_criteria` | Applies the *same* evidence rule independently to all seven scoring criteria. |

Two independent blocks, one root cause. Even a criterion that somehow cleared the gates could not be scored.

Affected: the six gate-material criteria (`ai_capability_fit`, `data_readiness`, `business_value`, `human_judgement_requirement`, `risk_consequence`, `residual_risk_with_human_oversight`), `human_accountability_required`, and all seven scoring criteria.

### 1.2 Are existing tests validating inputs the pipeline cannot produce?

**Yes.** `data/sample_processes/synthetic_customer_complaint_process.json` hand-authors criterion evidence:

```json
"ai_capability_fit": { "value": 5, "knowledge_state": "known", "evidence_ids": ["E1", "E2"] }
```

It is loaded directly as a `BusinessProcess`, bypassing Phase 4. Every `AUTOMATE` and `AUGMENT` assertion in the unit suite rests on this fixture. The engine is correct; the Phase 4 → Phase 1 integration boundary is untested.

### 1.3 Empirical confirmation — CONFIRMED

Executed 2026-08-15 against the frozen PORT-003 review session, read-only, writing nothing. The script supplied ideal criterion values through the real `ProcessReviewService`, approved via `approve_review`, and assessed with the unchanged `decision_policy.v0.2`.

Method: load `review_session.json`, call `resolve_unknown` for every unknown criterion with the most favourable admissible value (`5` for favourable criteria, `0` for unfavourable) and `human_accountability_required = False`, then approve and assess.

Recorded result:

| Observation | Value |
|---|---|
| Ideal values supplied through the real service | **43** |
| Projected criterion state | `value=5`, `knowledge_state=known`, **`evidence_ids=[]`** |
| Activities returning `INVESTIGATE_FURTHER` | **4 of 4** |
| Failing gate | `technical_fit` — *`ai_capability_fit` has no evidence reference* |

This is the strongest available demonstration of the defect: an operator supplying **perfect** values for every criterion, through the product's own service layer, still cannot obtain any recommendation other than `INVESTIGATE_FURTHER`. The gate does not reject the values on their merits — it never evaluates them, because the projection strips their provenance.

The conclusions in this document are no longer provisional.

---

## 2. Is this a real defect or an interpretation issue?

**A real defect — but an emergent one.** No single component is wrong:

1. The policy requires evidence for material criteria. *Defensible.*
2. `HUMAN_SUPPLIED` corrections may not claim document evidence. *Defensible — it prevents a human from fabricating a citation.*
3. The review UI only ever produces `HUMAN_SUPPLIED`. *An incomplete implementation.*

Any two of the three are fine. All three together make the product structurally unable to issue any recommendation other than `INVESTIGATE_FURTHER` to any user.

An important qualification: `correct_assertion(origin=DOCUMENT_SUPPORTED, evidence=[...])` **does** work and is used by the PORT-002 operator script. The dead end is in the product surface, not the domain model. This is therefore closer to *incomplete UI plus an unstated contract assumption* than to *broken architecture* — which materially reduces the cost of the fix.

---

## 3. Smallest possible fix

**Fix 0 — expose document-supported criterion correction in the review UI.**

Add an origin selector and evidence-picker to the criterion review widget so a reviewer can set a criterion value citing a block already resolved in the ingested document.

- Contracts changed: **none.**
- Policy changed: **none.**
- Schema changed: **none.**
- Taxonomy changed: **none.**
- Files touched: `presentation/pages/review.py` and a new integration test.
- Semantics: *"You may set a criterion when the source document states the fact."* Honest, already the intended design, merely unimplemented.

This is smaller than anything proposed in `phase9a-criterion-evidence-design-v0.1.md`, and it supersedes that document's assumption that a contract change is required first.

**What Fix 0 does not solve:** operator knowledge absent from the document — data readiness, risk consequence, business value. Those are precisely the criteria no process document ever states, so Fix 0 alone will rarely unblock a real case. It restores the intended design; it does not complete it.

**Recommended sequencing:** Fix 0 first, as its own small change with the integration test that should have existed. Then decide §4 with the product actually working as designed, rather than deciding it in the abstract.

---

## 4. The three options

### Option A — Operator attestation counts as evidence

Attestation produces a first-class evidence record satisfying the material requirement.

- **Contracts:** new `InformationOrigin` member; `correct_assertion` evidence rule relaxed for the attested origin; `EvidenceReference.provenance` extended.
- **Policy:** none strictly required.
- **Pro:** product becomes usable; smallest change that unblocks operator knowledge.
- **Con:** dilutes "evidence" unless attestation is visibly second-class in every downstream output. Risk that a report reads as document-backed when it is one person's opinion.
- **Mitigation:** attested values must be labelled in the decision package and report sections, not only in the data model.

### Option B — Attestation never satisfies gates

Attested values are recorded and displayed but cannot clear a gate.

- **Contracts:** minimal; formalises current behaviour.
- **Pro:** maximum evidential strictness; no dilution.
- **Con:** the product remains unable to recommend anything to any real user. This is the status quo defect promoted to a design decision.
- **Assessment:** only defensible if the product is repositioned as a *documentation and uncertainty-mapping* tool rather than a recommendation engine. That is a product-strategy decision, not a technical one, and it contradicts the stated purpose.

### Option C — Tiered evidence by gate

The policy declares acceptable provenance tiers per gate. `business_value` may accept attestation; `risk_and_autonomy` may require measured or document evidence.

- **Contracts:** `InformationOrigin` extension, plus provenance tier carried through `CriterionInput`.
- **Policy:** schema change — a new `evidence.acceptable_provenance_by_gate` block; version `v0.3`.
- **Pro:** most defensible. Makes the product's caution explicit, configurable and explainable rather than accidental. Directly addresses the "provisional" status the policy has carried since inception.
- **Con:** largest scope; requires the provenance tier to be threaded through projection, gates, scoring and reporting.

**Preliminary lean:** Fix 0 now; then C, with A as the scope-cut fallback. **No implementation decision is taken in this document.**

---

## 5. Production fingerprint impact

Current: `4deca4251d4a9840d6948411544fdf506f1953c16a56eaca803099d2cf81be5a`, covering tracked `config/**`, `src/**`, `streamlit_app.py`, `pyproject.toml`.

| Change | Fingerprint | Policy version | Notes |
|---|---|---|---|
| Fix 0 | **Changes** (`src/` edit) | unchanged | Smallest possible delta. |
| Option A | **Changes** | unchanged or `v0.3` | Contract change in `models/review.py`, `review/approval.py`. |
| Option B | Unchanged if documentation-only | unchanged | No code change required. |
| Option C | **Changes** | `v0.3` required | Policy schema plus projection, gates, scoring, reporting. |

Any fingerprint change must be recorded with its reason. **The Phase 8 fingerprint remains the permanent reference for the PORT-001/002/003 frozen runs** and must continue to verify against the artefacts committed at `15ee707` and earlier. A changed current fingerprint does not invalidate those runs; it marks the boundary after which they are no longer reproducible against `HEAD`.

---

## 6. What must remain unchanged

- All Phase 8 artefacts: frozen bundles, comparison artefacts, cross-case summary, hash listings, `phase8-complete`.
- The capability taxonomy. The speech/transcription gap is a separate phase and must never be justified by PORT-003 AFTER evidence.
- Gate ordering and recommendation semantics.
- Existing regression coverage. Tests are added, never weakened.
- The principle that unknown remains unknown. No option here may make guessing easier — only justification easier.

---

## 7. Consequence for Phase 8 records

The Phase 8 conclusions stand. XC-2's *finding* — that the decision engine was never exercised by a real case — is correct and unaffected. Its *root-cause explanation* attributed this to thin public evidence. That explanation is now known to be incomplete: the engine could not have been exercised by any input, from any source, through the product surface.

**Recommendation: do not edit Phase 8 artefacts.** Record the superseding explanation in Phase 9 documentation and cross-reference it. A frozen evaluation that is later better understood is normal; retro-fitting the record is not.

---

## 8. Open decisions

1. Approve Fix 0 as an isolated change with its integration test?
2. Option A, B or C — deferred until Fix 0 lands and §1.3 is empirically confirmed.
3. Derive `ai_capability_fit` from extracted capability signals? High value, high hindsight risk. See `phase9a-criterion-evidence-design-v0.1.md` §3.2.
4. Is measured-data ingestion in Phase 9A scope, or deferred?
