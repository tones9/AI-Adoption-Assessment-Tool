# Phase 9A — Fix 0 pre-implementation brief

Status: **APPROVED AND IMPLEMENTED** (2026-08-15). Implemented at the §3 scope with sub-decision §3.1 option (b); capability signals excluded by decision. The §6 limitation is accepted and remains deferred.
Version: v0.1
Date: 2026-08-15
Basis: `docs/phase9a-decision-review-v0.1.md` (§1.3 empirical confirmation, §1.4 9A-0a test result)
Characterisation tests: `tests/integration/test_phase9a_criterion_evidence_boundary.py` (1 passing, 1 `xfail(strict=True)`)

---

## 1. Final defect statement

The AI Adoption Engine cannot produce any recommendation other than `INVESTIGATE_FURTHER` for a criterion value supplied by a human operator, because three individually defensible decisions combine into a dead end: `decision_policy.v0.2` requires gate-material criteria to carry an evidence reference; `correct_assertion` forbids a `HUMAN_SUPPLIED` value from claiming document evidence, and `_collect_assertion_evidence` strips it during projection; and the review page calls the Phase 4 service without an `origin`, so every value a reviewer enters through the product surface becomes `HUMAN_SUPPLIED`. The domain model is sound — a `DOCUMENT_SUPPORTED` correction with resolved evidence survives projection and is read by the engine, as the 9A-0a domain test proves — so the defect is confined to the presentation layer, which exposes no way to record where a criterion value came from.

---

## 2. Files and components requiring change

| Component | Change | Necessity |
|---|---|---|
| `presentation/pages/review.py` → `_assertion_editor` | Add origin selection and an evidence picker; pass `origin` / `evidence` to the service | **Required** |
| `review/service.py` → `resolve_unknown` | Additive optional `origin` / `evidence` kwargs forwarded to `correct_assertion` | **Required** unless the §3 audit-trail compromise is accepted |
| `presentation/components/evidence.py` | Optional: render selectable evidence rather than display-only | Nice-to-have |
| `tests/integration/test_phase9a_criterion_evidence_boundary.py` | Extend the xfail test to operate the new controls; remove the marker | **Required** |
| `tests/ui/test_streamlit_app.py` | Only if a widget-layout assertion breaks — none currently look fragile | Contingent |

No policy, schema, taxonomy, gate, scoring or Phase 8 file is touched.

---

## 3. Smallest possible Fix 0 scope

For an unknown or correctable criterion, let the reviewer choose an origin and, when `DOCUMENT_SUPPORTED`, select one or more `ResolvedEvidenceReference` objects **already present on that step** — from its activity, description, collections or dependencies. Pass them to the Phase 4 service.

No new evidence-resolution code is required, and `correct_assertion`'s `document_id` check is guaranteed to pass because the references originate from the same candidate.

**Scope limitation, accepted:** a reviewer can only cite blocks the extraction already cited somewhere on that step. If the operational fact sits in a paragraph the extraction ignored, it remains uncitable. Block-level selection against the ingested document is larger work and is deliberately out of Fix 0.

### 3.1 Sub-decision required before implementation

`resolve_unknown` has no `origin` parameter today.

**(a) Presentation-only.** Call `correct_assertion` directly for unknown criteria. Zero service change, but the audit trail records `correct` where `resolve-unknown` is semantically correct, muddying an event vocabulary used consistently across three portfolio cases.

**(b) Additive service change — recommended.** Give `resolve_unknown` optional `origin` / `evidence` kwargs defaulting to current behaviour. Approximately three lines; no existing caller is affected; audit semantics are preserved.

Option (b) makes Fix 0 marginally more than presentation-only. The evidence *contract* is unchanged; a service *signature* is additively extended. The "no contract change" claim elsewhere in the Phase 9A documents should be read with that footnote.

---

## 4. Tests that change from xfail to pass

Exactly one: `test_review_ui_can_produce_an_evidence_backed_criterion`. It is marked `xfail(strict=True)`, so it fails loudly the moment Fix 0 works; the marker is removed in the same commit.

Its body must change to operate the new controls. Its assertion does not change: a reviewer working only through the product must be able to reach a state where a document-supported criterion carries evidence.

`test_document_supported_criterion_survives_projection_and_reaches_the_engine` must continue to pass untouched. It is the regression guard proving the domain path still works.

---

## 5. Risks of changing behaviour

### 5.1 Principal risk — semantic evidence validity is not addressed

Fix 0 lets a reviewer attach a document citation that does not actually support the value. `correct_assertion` validates only that the evidence belongs to the reviewed document; it never validates semantic relevance. A reviewer could set `data_readiness = 5` while citing a sentence about meeting frequency, and the engine would accept it as document-supported.

**Fix 0 therefore makes fabrication easier, not only justification easier.** This is in tension with the governing principle that unknowns remain unknown unless legitimately resolved.

Accepted mitigation for now: the citation is recorded, rendered in the decision report and fully auditable, so a wrong citation is visible rather than hidden. Detection is possible; prevention is not. See §6.

### 5.2 Secondary risks

- `tests/architecture/test_phase7_boundaries.py` asserts `".origin =" not in review.py`. Passing `origin=` as a keyword argument is safe; direct attribute assignment would break the guard. This is a useful existing constraint and must be respected.
- Existing UI tests rely on key-prefix widget lookups and session-derived metrics (`Required items: 9`, 200 assertion targets, 52 document-supported). Added widgets are additive and should not disturb them; confirm on first run.
- The production subtree fingerprint will change. Phase 8 frozen bundles continue to verify by hash but stop being reproducible against `HEAD`. Already recorded in `phase9a-decision-review-v0.1.md` §5.
- No change to gate logic, thresholds, scoring or the capability taxonomy, so no Phase 8 conclusion is affected.

### 5.3 Explicit non-risk

Fix 0 will not alter PORT-001, PORT-002 or PORT-003 results. Those runs are frozen artefacts, and the evaluation protocol forbade operator-supplied criterion values in any case.

---

## 6. What Fix 0 does and does not solve

**Solves — provenance path and UI exposure.** A reviewer can record *where* a criterion value came from, and a document-supported value survives projection and reaches the decision engine. The intended design is restored.

**Does not solve — semantic evidence validity.** Nothing checks that the cited snippet actually supports the asserted value. A technically valid but semantically irrelevant citation is accepted.

**Consequence.** After Fix 0 the product distinguishes *evidenced* from *unevidenced*, but not *well-evidenced* from *badly evidenced*. That is a strictly better position than today, where a reviewer cannot evidence anything at all, but it is not the finished state.

**Deferred.** Semantic validity belongs to a future evidence-quality control layer, alongside the attestation model, measured-data ingestion and tiered provenance rules described in `phase9a-criterion-evidence-design-v0.1.md` §3–§4. That work must not begin until Fix 0 has landed and 9A-0c has observed the corrected product behaviour.

**This limitation is accepted temporarily and knowingly.** It should be stated in the Fix 0 commit message and carried into any recruiter-facing description of the review step, rather than being discovered later.

---

## 7. Open decisions before implementation

1. Approve Fix 0 at the §3 scope?
2. §3.1 — option (a) presentation-only, or (b) additive `resolve_unknown` signature? Recommendation: (b).
3. Confirm the §6 limitation is accepted for now rather than blocking Fix 0.
