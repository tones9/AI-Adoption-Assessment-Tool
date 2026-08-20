# GRW M2 pre-implementation decisions

Status: **DECISION RECORD — PROPOSAL ONLY; NO M2 IMPLEMENTATION APPROVED**  
Version: v0.1  
Date: 2026-08-20  
Inputs: frozen GRW M1 governing design and implementation; [GRW M2 reassessment design v0.1](grw-m2-reassessment-design-v0.1.md); current Phase 4–7 and persistence architecture.  
Scope: resolves the 16 open decisions recorded in the M2 design into explicit
recommendations. It changes no production code, schema, migration, policy,
prompt, taxonomy, PORT/evaluation artefact, or AEL scope.

## 1. Decision posture

These recommendations are deliberately narrower than the architecture could
eventually support. They are intended to define one safe M2 M1 proof:

```text
one existing Decision Package
        ↓
one UNKNOWN data-readiness criterion
        ↓
one new supporting document
        ↓
evidence review
        ↓
criterion-resolution review
        ↓
explicit reassessment approval
        ↓
immutable successor review
        ↓
new Phase 5 assessment and Phase 6 package
        ↓
deterministic baseline-versus-successor comparison
```

The intended result is a decision that is better justified, including when it
is unchanged, less favourable, or retains uncertainty. It is not a mechanism
for making more recommendations pass.

### 1.1 Terms used in this record

| Term | Meaning in M2 M1 |
|---|---|
| Baseline | The existing immutable approved review, integrated assessment and Decision Package selected by their IDs, revisions and hashes. |
| Successor | A new formal decision lineage that exists alongside, and never replaces, the baseline. |
| Supporting document | One newly supplied, immutable, bounded document record. It is not an original process document and does not establish that the baseline activity existed. |
| Resolution | A human-reviewed proposal to change one selected criterion in the successor review. |
| Gate admissibility | Explicit permission for a resolved criterion to be used by a named gate. It is not the gate result. |
| M2 M1 | The first narrow decision-affecting M2 milestone defined in §20. |

## 2. Decision summary

| ID | Decision | Recommendation | M2 M1 status |
|---|---|---|---|
| D01 | Successor lineage | Dedicated `ReassessmentRun`, separate from the baseline workspace active chain. | BLOCKING |
| D02 | Physical persistence | Dedicated M2 tables/repository in the existing local SQLite boundary. | BLOCKING |
| D03 | Successor review/projection | M2-specific successor review and typed projection contract; do not forge Phase 4 records. | BLOCKING |
| D04 | Active-pointer semantics | Baseline stays active; successor has a separate run-scoped active chain. | BLOCKING |
| D05 | Idempotency, staleness, withdrawal | Append-only core lifecycle; baseline/hash change makes a request stale; withdrawal deferred. | BLOCKING |
| D06 | Admissibility policy/fingerprints | Approve a narrow, versioned M2 M1 policy fragment only for document-supported data readiness. | BLOCKING |
| D07 | Data-readiness instrument | Approve one versioned 0–5 instrument; document-only M2 M1 cannot assign 5. | BLOCKING |
| D08 | Structured attestation | Defer. It is not an M2 M1 evidence class. | CAN DEFER |
| D09 | Documentary sufficiency | One scoped, current supporting document plus data-owner approval may be sufficient only for data readiness. | BLOCKING |
| D10 | Decision-policy version change | Block M2 M1 if baseline and successor decision-policy fingerprints differ. | BLOCKING |
| D11 | Conflict handling | Preserve all claims; unresolved material conflict blocks M2 M1 reassessment. | BLOCKING |
| D12 | Supporting-document intake | One small plain-text document, local-only, hash-pinned, no automatic extraction. | BLOCKING |
| D13 | Dataset/privacy/retention | Defer datasets, CSV, measurements and deletion workflow. | CAN DEFER |
| D14 | Local roles/high consequence | Record labels only; exclude risk/autonomy/accountability resolutions from M2 M1. | BLOCKING |
| D15 | Customer question/routing | One fixed plain-English data-readiness question; no general priority engine. | BLOCKING |
| D16 | Comparison semantics | Immutable, deterministic, neutral baseline-versus-successor comparison. | BLOCKING |

## 3. D01 — successor lineage

**Question that must be decided**  
How should M2 represent a new formal decision without changing the original
approved review, assessment, package, or their active baseline chain?

**Why it matters**  
The current Phase 7 `reset_to_review` deactivates the active approved-review,
assessment, Decision Package and M1 sidecars. Its historic rows remain, but it
does not provide two independently active decisions. That is incompatible with
an honest baseline-versus-successor comparison.

**Realistic options**

1. Reuse `reset_to_review` in the baseline assessment workspace and create new
   normal revisions.
2. Keep the baseline workspace but add M2 artefacts as further sidecars.
3. Create a dedicated `ReassessmentRun` rooted in immutable baseline references
   with a separate successor chain.

**Recommended option**  
Option 3: a dedicated immutable `ReassessmentRun` with its own identifier and
its own successor-review/assessment/package lineage.

**Why this is recommended**  
It leaves the baseline workspace at `PACKAGE_READY`, preserves its active
pointers and M1 records, and makes the selected baseline a visible, hash-pinned
parent—not an inferred historical revision. It supports more than one future
reassessment without overwriting the meaning of “current baseline.”

**What can go wrong with the recommendation**  
It introduces new persistence and navigation concepts, so a weak design could
duplicate state or make the user select the wrong run. It needs explicit
cross-run integrity checks and clear UI labelling.

**M2 M1 implementation status**  
**BLOCKING.**

**Resulting architecture/product behaviour**  
Opening M2 from a package creates no formal change. Once explicitly approved,
a reassessment creates a new `ReassessmentRun` that points to the exact baseline
artefacts. The baseline remains visible as the existing recommendation; the
successor is visible as a separate later decision.

## 4. D02 — physical persistence boundary

**Question that must be decided**  
Where should reassessment runs and their immutable artefacts be stored?

**Why it matters**  
The current SQLite schema has one `assessments` table, generic artefacts, and
one active pointer per artefact type/assessment. A new ordinary
`AssessmentRecord` alone would inaccurately imply a new document ingestion and
candidate extraction, while a shared active-pointer scope would displace the
baseline.

**Realistic options**

1. Add successor artefacts to the existing generic artefact tables under the
   baseline assessment ID.
2. Create a second ordinary assessment and copy/recreate enough baseline data
   to run Phase 4–6.
3. Add dedicated M2 run, artefact, active-run-pointer and operation records in
   the existing local SQLite database, with a dedicated repository boundary.
4. Put M2 in a separate database/service.

**Recommended option**  
Option 3: dedicated M2 tables/repository in the existing local SQLite database.

**Why this is recommended**  
It gives M2 a separate active-pointer namespace while retaining local
transactional integrity and simple developer operation. It can store immutable
links to the baseline instead of copying baseline artefacts or misleading the
existing `AssessmentRecord` lifecycle.

**What can go wrong with the recommendation**  
It requires a future migration and careful foreign-key/hash validation. A poor
repository split could duplicate serialization or allow cross-assessment
attachment. M2 M1 must use one transaction boundary where a new artefact and
run state change together.

**M2 M1 implementation status**  
**BLOCKING.**

**Resulting architecture/product behaviour**  
The user sees a reassessment linked to the baseline package, not a newly
ingested process. Baseline and successor artefacts have separate active
pointers and may be rendered together without reactivating or deactivating
anything in the baseline workspace.

## 5. D03 — successor review and Phase 5 projection contract

**Question that must be decided**  
How does one approved M2 resolution become a valid formal input to Phase 5
without falsifying current Phase 4 provenance?

**Why it matters**  
Current `ProcessReviewService.correct_assertion` permits a
`DOCUMENT_SUPPORTED` correction only when every evidence reference belongs to
the original candidate document. Current `EvidenceReference` is also
document-oriented and cannot represent a dataset, calculation or attestation.
M2 cannot simply call the current review mutation API with a new supporting
document.

**Realistic options**

1. Bypass Phase 4 and write a changed `BusinessProcess`/criterion directly.
2. Forge or mutate a normal `ApprovedProcessReview` to look like it was based
   only on the original candidate document.
3. Change the existing Phase 4 contracts globally to accept every future GRW
   evidence class.
4. Create an M2-specific immutable successor-review and typed assessment-input
   projection contract, validated against a pinned baseline plus approved M2
   resolution(s).

**Recommended option**  
Option 4.

**Why this is recommended**  
It preserves the meaning of the frozen Phase 4 contracts and makes M2 evidence
explicit rather than disguising it as original-document evidence. The
successor projection can prove that one approved field changed and every other
formal input is exactly the baseline value.

**What can go wrong with the recommendation**  
There will be two approval/projection shapes unless a future refactor unifies
them. The M2 adapter must be exhaustively validated so it cannot inject a
criterion, evidence ID, capability signal, or policy decision not present in
the approved successor review.

**M2 M1 implementation status**  
**BLOCKING.**

**Resulting architecture/product behaviour**  
M2 M1 creates a `SuccessorApprovedReview` (name provisional) that contains an
exact baseline review reference, an immutable patch for one
`data_readiness` assertion, its typed document evidence and every reviewer
decision. Only a validated M2 projection may call a successor Phase 5
assessment; direct criterion mutation is impossible through the M2 service.

## 6. D04 — baseline and successor active-pointer semantics

**Question that must be decided**  
Which package is active after M2 M1, and how is the baseline preserved?

**Why it matters**  
Current workspace hydration assumes one active linear chain per assessment.
Calling `reset_to_review`, re-ingestion or extraction activation on the baseline
would make its package non-current and deactivate M1 records.

**Realistic options**

1. Make the successor replace the baseline as the only active package.
2. Keep both packages in generic historical rows and let the UI choose by date.
3. Keep the baseline active in its workspace; make the successor active only in
   its own reassessment-run scope; expose a named baseline/successor comparison.

**Recommended option**  
Option 3.

**Why this is recommended**  
It makes the original decision stable and avoids ambiguity. A later customer
choice may designate a successor as the preferred current decision, but that is
a separate explicit product action, not a side effect of reassessment creation.

**What can go wrong with the recommendation**  
Users could confuse “baseline active” with “baseline preferred.” The product
must label the successor as a later evidence-supported package and state that
an accountable human decides which package to act on.

**M2 M1 implementation status**  
**BLOCKING.**

**Resulting architecture/product behaviour**  
The baseline decision remains returned by ordinary workspace views. The M2 page
shows the successor only within the reassessment view, with both package IDs,
dates, hashes and a neutral comparison. No automatic “promote successor” action
exists in M2 M1.

## 7. D05 — idempotency, staleness, retries and withdrawal

**Question that must be decided**  
How should M2 prevent duplicate successors, handle a stale baseline/request,
and record evidence withdrawal or retry?

**Why it matters**  
The current Phase 7 operations are idempotent only within the current
assessment/artifact chain. M2 introduces an immutable request that can become
invalid if a referenced hash, evidence status or policy version changes.

**Realistic options**

1. Let the UI control duplicates and use the latest records at execution time.
2. Use immutable request IDs but no stale validation.
3. Use a hash-derived idempotency key for every M2 transition; validate every
   pinned reference at approval and execution; append terminal stale/withdrawn
   events instead of editing history.

**Recommended option**  
Option 3, with withdrawal limited to an auditable status marker in M2 M1 rather
than data deletion.

**Why this is recommended**  
It fails closed if a baseline, resolution, evidence review or policy reference
changes. It also handles Streamlit reruns/double-clicks without producing two
successor assessments.

**What can go wrong with the recommendation**  
Strict staleness can feel inconvenient: a customer may need to create a new
request after a legitimate edit. Ambiguous idempotency keys can accidentally
merge distinct requests, so they must cover the full canonical pinned request
payload, not user-visible labels.

**M2 M1 implementation status**  
**BLOCKING.** Basic withdrawal/deletion workflow beyond a status marker is
**CAN DEFER**.

**Resulting architecture/product behaviour**  
A reassessment request with a changed hash is marked `STALE` and cannot run.
An approved request executes once; retry returns the existing successor. A
submitted document may be marked withdrawn before approval, which blocks the
request; M2 M1 does not delete historical decision records or raw content.

## 8. D06 — admissibility policy and canonical fingerprints

**Question that must be decided**  
What formal policy permits one new document to resolve `data_readiness` and be
used by technical fit, and how is that policy pinned?

**Why it matters**  
Current decision policy v0.2 requires valid criterion value/state and evidence
IDs but does not decide whether a customer document is sufficient for a gate.
Without a separate policy, M2 would give a reviewer unbounded discretion.

**Realistic options**

1. Treat existing decision policy v0.2 as sufficient.
2. Let the reviewer state that the document is good enough in free text.
3. Approve a narrow M2 M1 admissibility-policy fragment with canonical JSON,
   version and SHA-256 fingerprint, covering only document-supported
   `data_readiness` at technical fit.
4. Approve the full future matrix for every criterion/evidence class before any
   M2 work.

**Recommended option**  
Option 3.

**Why this is recommended**  
It provides a real policy boundary without prematurely committing to the full
future matrix. The fragment can state exact permitted class, criterion, gate,
minimum review roles, scope/recency checks, conflict treatment and prohibited
uses.

**What can go wrong with the recommendation**  
The fragment may later need revision; that is acceptable only if its fingerprint
is preserved. It must not gradually expand through undocumented reviewer
convention. A narrow fragment can be mistaken for a general evidence policy;
the UI and record must name its limited scope.

**M2 M1 implementation status**  
**BLOCKING.**

**Resulting architecture/product behaviour**  
M2 M1 accepts only a document review that explicitly yields
`CRITERION_RESOLUTION` and `GATE_ADMISSIBLE_WITH_APPROVAL` for
`data_readiness`/`technical_fit` under the pinned fragment. Estimates,
free-text facts, M1 answers, datasets, measurements and derived values are
rejected or retained outside the formal path.

## 9. D07 — versioned data-readiness instrument

**Question that must be decided**  
How may a reviewer map a supporting document to a 0–5 `data_readiness` value?

**Why it matters**  
The deterministic engine accepts an ordinal value but has no mapping instrument.
Without anchors, a reviewer could select a desired score and backfill a
rationale. A value is not implied by the fact that a document exists.

**Realistic options**

1. Let reviewers enter an integer and free-text explanation.
2. Automatically infer a score from document terms or a language model.
3. Approve one deterministic, versioned data-readiness instrument with anchors,
   allowed evidence, exclusions and human-reviewed mapping.

**Recommended option**  
Option 3. For document-only M2 M1, the instrument may support values 0–4; value
5 requires a separately reviewed measured profile and is unavailable.

**Why this is recommended**  
It preserves human judgment while bounding it. It also prevents a document-only
path from implying verified data quality, completeness or performance that has
not been measured.

**What can go wrong with the recommendation**  
Anchors can be too vague, too broad, or mistakenly treated as an objective
measurement. A document can describe an intended system state rather than the
current process. The instrument must require scope, period, ownership/control
and stated limitations; it must allow the reviewer to retain `UNKNOWN`.

**M2 M1 implementation status**  
**BLOCKING.**

**Resulting architecture/product behaviour**  
The approved instrument is hash-pinned in the resolution. The reviewer sees
the raw supporting passage and each anchor, proposes one value or retains
unknown, and records rationale. No midpoint, parser, recommendation target or
automated model selects the value. The instrument does not by itself pass
technical fit.

## 10. D08 — structured attestation

**Question that must be decided**  
Should named, anchored operator/data-owner answers be allowed as structured
attestation in M2 M1?

**Why it matters**  
Structured attestation can be useful, but it needs a versioned question,
accountable role, authority declaration, scope, basis, conflict handling and
role controls. The current local application cannot authenticate or verify any
of these attributes.

**Realistic options**

1. Accept any reviewer-labelled free-text response as attestation.
2. Implement a full attestation contract in M2 M1.
3. Defer structured attestation; preserve it as a future evidence class only.

**Recommended option**  
Option 3.

**Why this is recommended**  
It prevents M2 M1 from upgrading self-reported answers into gate evidence. The
document-supported path already proves the reassessment mechanics without
requiring authority verification.

**What can go wrong with the recommendation**  
Some customers will have no useful document and will receive no formal M2 path
yet. That is preferable to implying a weak answer is independently attested.

**M2 M1 implementation status**  
**CAN DEFER.**

**Resulting architecture/product behaviour**  
M2 M1 may retain ordinary answers as non-decision GRW context but cannot use
them in a resolution, technical-fit gate, successor review or package.

## 11. D09 — documentary sufficiency and corroboration

**Question that must be decided**  
When is one supporting document sufficient for data-readiness resolution and
technical-fit use?

**Why it matters**  
Documents can be draft, stale, aspirational or from another team. Choosing the
newest or most detailed document automatically would defeat the provenance
boundary.

**Realistic options**

1. Any uploaded document is sufficient after a reviewer accepts it.
2. Require two independent documents in every case.
3. Permit one document only when it has reviewed identity/authority, exact
   passage, same-step scope, relevant period, field/control detail, limitations
   and a data-owner approval; otherwise retain unknown or request corroboration.

**Recommended option**  
Option 3.

**Why this is recommended**  
It permits the narrow M2 M1 proof without claiming universal sufficiency. The
data-owner approval provides an explicit accountability check, while the
instrument/policy can reject a merely aspirational or incomplete document.

**What can go wrong with the recommendation**  
A data-owner label is not verified in the local product, and the reviewer may
misread scope. M2 M1 must visibly state that authority is declared, not
technically verified, and must reject unclear scope rather than infer transfer.

**M2 M1 implementation status**  
**BLOCKING.**

**Resulting architecture/product behaviour**  
The evidence review requires document hash, source/authority description,
locator, exact passage, process-step/time scope, limitations and a data-owner
approval declaration. A missing material element yields
`INSUFFICIENT_FOR_THIS_USE`, not a successor run.

## 12. D10 — decision-policy version changes

**Question that must be decided**  
May an M2 successor use a different deterministic decision-policy fingerprint
from its baseline?

**Why it matters**  
If evidence and policy change together, an old-versus-new result cannot
honestly attribute a gate or recommendation difference to the new evidence.

**Realistic options**

1. Always use the currently installed decision policy.
2. Allow a new policy if the comparison mentions it.
3. Require exact baseline/successor policy fingerprint equality in M2 M1;
   treat policy-evolution comparisons as a separately approved future feature.

**Recommended option**  
Option 3.

**Why this is recommended**  
It makes the first comparison an evidence-and-approved-resolution comparison,
not a mixed policy experiment. It also avoids applying an unreviewed policy
change to a historical baseline.

**What can go wrong with the recommendation**  
An urgent policy correction would make pending requests stale or blocked. That
is the appropriate safe outcome until a separate policy-change methodology is
approved.

**M2 M1 implementation status**  
**BLOCKING.**

**Resulting architecture/product behaviour**  
The request pins the baseline decision-policy fingerprint. Approval and
execution compare it to the loaded policy; mismatch results in `STALE_POLICY`
and no successor assessment/package is generated.

## 13. D11 — conflicts and materiality

**Question that must be decided**  
Which conflicts block a data-readiness reassessment, and who may reconcile
them?

**Why it matters**  
New evidence can contradict a baseline document or describe another period,
population or system. A conflict must not be resolved by recency, numerical
precision or the desired recommendation.

**Realistic options**

1. Automatically prefer newer/newer-looking evidence.
2. Let the evidence reviewer choose a winner in free text.
3. Preserve all claims, record a fixed relationship classification, and block
   M2 M1 on unresolved material conflict; permit only a qualified reviewer plus
   data owner to record an explicit reconciliation.

**Recommended option**  
Option 3.

**Why this is recommended**  
It makes uncertainty visible and limits M2 M1 to one use case where the
materiality rule can be exact: a conflict is material if it changes whether the
document supports the target step’s data availability/control claim, or if
scope/period cannot be established.

**What can go wrong with the recommendation**  
The rule can block useful reassessments where sources are only partially
overlapping. A qualified reviewer may approve a narrower target scope only
when the successor package and comparison state that narrower scope explicitly.

**M2 M1 implementation status**  
**BLOCKING.**

**Resulting architecture/product behaviour**  
Every evidence review records `CONSISTENT`, `PARTIALLY_OVERLAPPING`,
`CONTRADICTORY`, `DIFFERENT_SCOPE`, `STALE_OR_SUPERSEDED` or `UNRESOLVED`.
`UNRESOLVED` material conflict blocks reassessment. Existing baseline evidence
is preserved even when a successor uses a reconciled narrower claim.

## 14. D12 — supporting-document intake

**Question that must be decided**  
What document may M2 M1 accept, and how is it retained safely and reproducibly?

**Why it matters**  
Current generic ingestion accepts PDF/text as a process source and can trigger
the baseline chain’s re-ingestion/re-extraction behaviour. M2 must not treat a
supporting document as a replacement process document or send it through the
extraction path.

**Realistic options**

1. Reuse the ordinary source-ingestion page and mark the upload as replacement.
2. Accept arbitrary documents and automatically extract/reason over them.
3. Accept exactly one small UTF-8 plain-text supporting document in the M2 run,
   store bytes and SHA-256 locally, require the reviewer to select/record an
   exact passage manually, and do not send it to an external provider.
4. Build full PDF/Office/document-scanning intake first.

**Recommended option**  
Option 3.

**Why this is recommended**  
It makes source identity, hashing, retention and manual semantic review
testable, while avoiding a second extraction/prompt/data-handling system. The
customer can later be offered other formats after their controls are designed.

**What can go wrong with the recommendation**  
Plain text is inconvenient and may exclude customers with only PDFs. A document
can contain sensitive text. M2 M1 needs a documented size limit, no secrets or
unnecessary personal data warning, local-only storage, escaped rendering, and
a direct prohibition on LLM/external analytics transmission.

**M2 M1 implementation status**  
**BLOCKING.**

**Resulting architecture/product behaviour**  
The M2 page accepts one text document only for the selected data-readiness
question. It stores its content hash, supplied filename/label, declared source
and exact reviewed passage. It does not run normal process ingestion/extraction,
does not accept PDF/CSV/Office files, and does not modify the baseline document.

## 15. D13 — datasets, measured evidence, privacy and retention

**Question that must be decided**  
Must M2 M1 accept operational exports/CSV or implement data-retention and
deletion workflows?

**Why it matters**  
`DATASET_SUPPLIED` is not `MEASURED`. Measured evidence requires dataset
identity, field/denominator definitions, extraction/calculation, data-quality
treatment, reproducibility, sensitive-data handling, retention and withdrawal
semantics. None currently exists in production.

**Realistic options**

1. Accept CSV and label it measured when it looks structured.
2. Build a full measurement/data-governance subsystem before M2 M1.
3. Exclude datasets, CSV, measurement, derived metrics and raw-data deletion
   from M2 M1; design them as a future separately approved milestone.

**Recommended option**  
Option 3.

**Why this is recommended**  
It avoids treating a file as a fact and keeps the first decision-affecting path
inside the document evidence boundary. It is the smallest useful test of M2
lineage, approval and comparison.

**What can go wrong with the recommendation**  
Data-readiness cannot reach document-unsupported conclusions that need a
profile, and the product will be limited for customers without documents. The
right response is `INSUFFICIENT_FOR_THIS_USE`, not a weaker evidence shortcut.

**M2 M1 implementation status**  
**CAN DEFER.**

**Resulting architecture/product behaviour**  
There is no upload for CSV/data exports, no calculation, no derived metric, no
measured class, no data retention/deletion flow and no claim of data quality or
ROI in M2 M1. Document retention is local to the M2 run; broader retention
policy remains an open future decision.

## 16. D14 — local human roles and high-consequence evidence

**Question that must be decided**  
What assurance can M2 M1 claim about reviewers/approvers, and may it resolve
risk, autonomy or accountability fields?

**Why it matters**  
The current application is local and single-user. A typed label cannot verify a
person’s identity, authority, independence, data ownership or risk ownership.
Risk/autonomy/accountability conclusions are especially unsafe if treated as
governed merely because a label was entered.

**Realistic options**

1. Treat submitted reviewer labels as verified roles and support every
criterion.
2. Build authentication, organisation roles and separation-of-duties first.
3. Record declared labels/roles and self-review warning, but limit M2 M1 to
data readiness; prohibit risk, autonomy, accountability and high-consequence
resolutions until a later approved control model exists.

**Recommended option**  
Option 3.

**Why this is recommended**  
It is honest about the product’s capability and preserves the role fields that
a later enterprise layer can verify. Data readiness is lower consequence than
removing human accountability or clearing residual risk, but even it needs a
declared data-owner approval.

**What can go wrong with the recommendation**  
An unverified data-owner declaration still carries governance risk. The UI and
record must say “declared, not verified,” and the recommendation must not
represent that declaration as enterprise control assurance.

**M2 M1 implementation status**  
**BLOCKING.**

**Resulting architecture/product behaviour**  
M2 M1 requires evidence reviewer, criterion reviewer, declared data owner and
reassessment approver labels/rationales. It displays coalesced roles/self-review
and does not allow risk, autonomy, `human_accountability_required`, business
value, or capability-fit resolutions.

## 17. D15 — customer questions and priority routing

**Question that must be decided**  
What does the customer see, and how does M2 choose the first question without
exposing raw technical gaps or a compliance questionnaire?

**Why it matters**  
Current Phase 6 gaps are technical/internal and M1 intentionally supports only
one deterministic `repetition` question. A general M2 prioritisation engine
would expand scope and may misrepresent decision materiality.

**Realistic options**

1. Expose every `InformationGap` and ask the customer to complete them.
2. Build full `DECISION_CRITICAL` prioritisation for all criteria now.
3. Use one fixed catalogue item that is eligible only when the selected package
   contains one unknown `data_readiness` criterion, and render one normal
   business-language question.

**Recommended option**  
Option 3.

**Why this is recommended**  
It follows M1’s narrow experience and makes the evidence path testable. It
does not imply that all other gaps must be answered or that M2 is generally
available for every package.

**What can go wrong with the recommendation**  
The question may be unavailable for many real packages, and customers may want
to resolve a different gap. That is acceptable for M2 M1; the UI needs a clear
“continue with your current package” path and no failure implication.

**M2 M1 implementation status**  
**BLOCKING.**

**Resulting architecture/product behaviour**  
The page says the existing package remains useful, then asks only:

> “What information is documented about the data available for this activity?
> If you have a current data dictionary, system description, or operating
> procedure that identifies the relevant fields and limits, you may provide one
> supporting document.”

It shows no raw gap list, completion percentage, CSV option or promise of a
changed recommendation.

## 18. D16 — comparison semantics

**Question that must be decided**  
What exact comparison is produced after a successor package, and how is it kept
from becoming a claim of prediction accuracy, adoption success or ROI proof?

**Why it matters**  
An unstructured narrative could hide a changed policy, dropped uncertainty,
missing evidence or less favourable conclusion. Recommendation movement alone
does not establish real-world value.

**Realistic options**

1. Show only the successor recommendation and a prose summary.
2. Report the recommendation change as “improvement” when it is more positive.
3. Create an immutable deterministic comparison with schema-bound baseline and
   successor references, criterion/evidence/gate/package deltas and neutral
   outcome language.

**Recommended option**  
Option 3.

**Why this is recommended**  
It makes comparison reproducible and exposes both change and non-change. It
allows a later package to be more cautious without treating that as product
failure.

**What can go wrong with the recommendation**  
Too much detail could overwhelm customers, and a compact view could omit a
material delta. M2 M1 should provide a short business summary backed by a
reviewer/audit view of the same immutable record.

**M2 M1 implementation status**  
**BLOCKING.**

**Resulting architecture/product behaviour**  
The comparison always includes baseline/successor IDs/hashes, addressed and
remaining gaps, old/new criterion state, document provenance/permission,
gate evaluation/results, recommendation, priority status, exact ROI/benefit
statement and package-completeness deltas. It uses descriptions such as
`NO_FORMAL_CHANGE`, `CRITERION_CHANGE`, `GATE_CHANGE`,
`RECOMMENDATION_CHANGE` or `UNCERTAINTY_INCREASED`, never “success.”

## 19. Repository findings that constrain M2

These are verified constraints from the frozen/current repository, not new
policy decisions.

1. **The M2 design must not reuse Phase 4 correction as written.**
   `ProcessReviewService.correct_assertion` requires document-supported
   correction evidence to belong to the original candidate source document.
   A supplemental supporting document would be rejected. M2 needs the
   dedicated successor-review/projection contract in D03.

2. **The M2 design must not treat current `EvidenceReference` as a general
   evidence model.** It contains source ID, locator and supporting snippet but
   cannot carry data-export identity, calculation, attestation authority,
   admissibility permission or conflict analysis. D03 and D06 are mandatory
   before evidence can affect a formal input.

3. **The baseline-preservation recommendation is technically necessary.**
   Phase 7 `reset_to_review` deactivates `APPROVED_REVIEW`,
   `INTEGRATED_ASSESSMENT_RESULT`, `DECISION_PACKAGE_RESULT`, and both M1
   artefacts. The current assessment workspace cannot host an independently
   active baseline and successor chain without a new namespace.

4. **The existing M1 frozen-workspace guard is not sufficient for M2.** It is
   enforced only at M1 submission/review service methods. A future M2 service,
   repository and every decision-affecting write must independently fail closed
   when its configured target is inside the frozen evaluation/portfolio area.

5. **A data-readiness M2 M1 fixture must have earlier technical-fit evidence.**
   The current deterministic gate order evaluates direct AI capability fit
   before data readiness. A baseline that stops on unknown `ai_capability_fit`
   cannot demonstrate a data-readiness gate change. Synthetic M2 M1 tests must
   start with admissible baseline capability evidence and mapping, then resolve
   only the unknown data-readiness criterion.

6. **The current integrated-assessment lineage needs extension, not
   replacement.** It pins a source document, approved review, validated-process
   fingerprint and decision-policy fingerprint. M2 must preserve those fields
   and add—not substitute—successor-review, resolution, evidence, instrument
   and admissibility-policy fingerprints.

7. **The current M1 guarantee must remain true for M1.** M2 may consume no M1
   estimate, preliminary understanding or recorded-only result as formal
   evidence. M1 stays a non-decision lifecycle even after M2 exists.

## 20. M2 M1 Proposed Contract

### 20.1 Plain-language promise

If these recommendations are approved, the first M2 implementation would let
a customer strengthen **one specific data-availability question** for one
existing Decision Package with **one supporting text document**.

The customer would see that the original package is still valid. They would be
asked for documentation about the data available for the selected activity,
such as a data dictionary, system description or operating procedure. The
product would explain that the document may or may not be sufficient and will
be reviewed before it affects anything.

An evidence reviewer would check what the document says, its scope, exact
passage, limitations and declared source. A criterion reviewer would apply one
published data-readiness instrument. A declared data owner and an explicit
reassessment approver would need to approve the use. Only then could the
product create a separate successor review, Phase 5 assessment, Phase 6
Decision Package and neutral comparison.

The original package would remain unchanged and readable throughout.

### 20.2 M2 M1 would do exactly this

- Start only from one successful, package-ready baseline Decision Package.
- Select only one `UNKNOWN` `data_readiness` criterion whose earlier technical
  fit prerequisites are already admissibly established in the baseline.
- Offer one optional plain-English question and one `text/plain` supporting
  document submission; retain the bytes, SHA-256, declared source and reviewed
  passage locally.
- Create immutable evidence submission, evidence review, conflict assessment,
  data-readiness resolution proposal, reassessment request and reassessment
  approval records.
- Apply one frozen M2 M1 admissibility-policy fragment and one versioned
  data-readiness 0–5 instrument.
- Allow the reviewer to retain `UNKNOWN`, reject the evidence, or propose one
  value 0–4; no document-only M2 M1 path can assign value 5.
- Require explicit declared reviewer/data-owner/approver labels and rationales;
  show that the local product does not verify their authority or independence.
- Reject/retain material conflicts rather than select a convenient answer.
- Create a separate successor run only when all pins, policy equality and
  approvals validate.
- Run a new deterministic Phase 5 assessment and Phase 6 package only from
  that validated successor input.
- Generate an immutable comparison with all formal and evidence deltas, whether
  the recommendation is unchanged, more favourable or less favourable.
- Refuse every M2 write against a frozen evaluation/portfolio target before any
  mutation.

### 20.3 M2 M1 would explicitly not do

- Change, deactivate, reset, reopen or regenerate the baseline package,
  assessment or approved review.
- Treat M1 estimates, free text, ranges, `RECORDED_ONLY` or
  `PRELIMINARY_UNDERSTANDING` as criterion/gate evidence.
- Accept PDFs, Office documents, CSV/data exports, operational datasets,
  measurements, derived metrics or files that claim to be measured evidence.
- Extract a supplemental document with an LLM or send it to external providers.
- Resolve `ai_capability_fit`, business value, conventional-solution fit,
  implementation complexity, risk, autonomy, predictability, residual risk or
  human accountability.
- Automatically score a criterion, approve evidence, approve reassessment,
  promote a successor, or resolve a conflict.
- Support policy-version changes between baseline and successor.
- Claim a recommendation change proves ROI, accuracy, safe deployment, pilot
  success, implementation readiness or realised outcome.
- Start AEL, pilots, deployment, execution governance, learning/calibration,
  multi-user access controls or enterprise retention/deletion infrastructure.

## 21. Approval set

### 21.1 Decisions recommended for approval now

Approve D01, D02, D03, D04, D05 (core stale/idempotency rules), D06, D07, D09,
D10, D11, D12, D14, D15 and D16 as the M2 M1 contract.

Together, they approve a document-only, data-readiness-only, separate-run
reassessment proof. They do **not** approve the full M2 architecture or
admissibility matrix for every criterion.

### 21.2 Decisions safe to defer

- D08 — structured attestation;
- D13 — datasets, CSV, measured evidence, derived metrics and operational-data
  retention/deletion workflows; and
- D05’s full withdrawal/deletion implementation beyond an immutable status
  record.

### 21.3 Decisions where no recommendation is yet warranted

There is no decision in the 16-item M2 M1 set for which a recommendation is
currently impossible. However, the following should **not** be selected until
their separate policy/design work exists: exact enterprise role controls,
high-consequence risk/accountability admissibility, policy-evolution
comparison, measured-data rules, full document-format/security controls, and
AEL entry governance.

No M2 implementation should begin until the blocking M2 M1 decisions have
explicit approval.
