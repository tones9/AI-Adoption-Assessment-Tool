# GRW M2 reassessment design

Status: **DESIGN ONLY — NOT APPROVED, NOT IMPLEMENTED**  
Version: v0.1  
Date: 2026-08-20  
Depends on: GRW workspace design v0.1, evidence-contract design v0.1,
evidence-admissibility policy design v0.1, and the frozen GRW M1 design and
implementation.  
Scope: a proposed, controlled route from approved additional evidence to a
successor formal assessment and Decision Package. This document changes no
production code, schema, migration, policy, prompt, taxonomy, portfolio or
frozen evaluation artefact.

## 1. Purpose and product principle

GRW M1 demonstrates an intentionally non-decision lifecycle: a customer can
answer one optional question, a human can review it, and the existing formal
decision remains unchanged.

M2 is the later, separately approved capability that would allow an
organisation to submit *sufficiently trustworthy new evidence*, have its
permitted use reviewed, explicitly approve a reassessment, and receive a new
formal Decision Package. It exists to make a recommendation **more justified**,
not more positive.

The governing principle remains:

> The customer receives useful value from the first process-document upload.
> Gap Resolution strengthens the next decision when warranted; it is not a
> prerequisite for an initial Decision Package.

A reassessment may leave the result at `INVESTIGATE_FURTHER`, make it more
cautious, or make it more actionable. None is intrinsically a success.

```text
baseline Decision Package
        ↓
optional, prioritised stronger evidence
        ↓
provenance, scope and admissibility review
        ↓
reviewed criterion-resolution proposal
        ↓
explicit reassessment approval
        ↓
successor approved review → Phase 5 assessment → Phase 6 package
        ↓
deterministic baseline-versus-successor comparison
```

This document treats [GRW evidence-admissibility policy design v0.1](grw-evidence-admissibility-policy-design-v0.1.md)
as the governing design input. It does not approve that proposed policy as
production policy.

## 2. Verified current starting point

The frozen M1 implementation uses two immutable sidecar artefacts:

- `GRW_EVIDENCE_SUBMISSION`, with the active Decision Package as parent; and
- `GRW_EVIDENCE_REVIEW`, with that submission as parent.

They deliberately remain at `PACKAGE_READY`, pin the approved-review,
assessment, and package hashes, and contain an `assessment_effect` of `NONE`.
They do not enter the formal Phase 4 → Phase 5 → Phase 6 parent chain.

The present production architecture also has these constraints:

| Current construct | Verified behaviour | M2 consequence |
|---|---|---|
| Phase 4 reviewed assertion | Has `KNOWN`, `INFERRED` or `UNKNOWN`, an `InformationOrigin`, rationale, and document-oriented evidence. | It cannot honestly encode an operational dataset, a calculation, a scoped attestation, or an admissibility decision without a new contract. |
| `InformationOrigin` | Recognises `DOCUMENT_SUPPORTED`, `MODEL_INFERRED`, `HUMAN_SUPPLIED`, and `UNKNOWN`; a human-supplied assertion cannot carry document evidence. | M2 must not relabel a customer answer as existing `DOCUMENT_SUPPORTED`, or use `HUMAN_SUPPLIED` as a shortcut to gate evidence. |
| Phase 4 approval | Projects approved reviewed assertions to the narrow process/criterion inputs consumed by the assessment engine. Document evidence becomes the current `EvidenceReference`; human-supplied evidence IDs are stripped. | M2 needs an explicit reviewed projection contract that preserves new-evidence provenance without corrupting the existing meaning of Phase 4 fields. |
| Phase 5 assessment | Pins source document, approved review, validated-process fingerprint and decision-policy fingerprint. | A successor must additionally pin the M2 evidence, admissibility policy, criterion instrument, resolutions and approval. |
| Phase 6 package | Is generated from an integrated assessment and exposes unknowns as `InformationGap`s. | Gaps remain a prompt-selection aid; they are not evidence or a claim that any answer resolves the gap. |
| Current workspace revisions | `reset_to_review` deactivates the active approved review, assessment, package and GRW sidecars, though immutable historical rows remain. | This is unsafe as the M2 reassessment mechanism because the customer would lose a stable active baseline and the sidecar lineage is not a reassessment chain. |
| SQLite active pointers | One active artefact per type is validated as a linear Phase 2–6 chain. | M2 needs explicit successor lineage rather than relying on a replacement active pointer in the baseline workspace. |

Therefore M2 must not call the current `reset_to_review` operation as a way to
make new evidence count. It would preserve old bytes but conflate a new
decision with reopening and deactivating the baseline decision.

## 3. Separate four questions that must never collapse

M2 must record four different things, even when they originate in one customer
interaction:

| Question | Example | What it does not mean |
|---|---|---|
| **Information supplied** | “About 10–15% of tickets are transferred at least once.” | It is not necessarily an accurate fact, an approved score, or gate evidence. |
| **Evidence strength/provenance** | An immutable export, a reviewed document passage, or an accountable structured attestation. | A stronger label does not itself establish criterion relevance or policy permission. |
| **Criterion resolution** | A reviewer maps a scoped, reviewed source through an approved instrument to `data_readiness = 4`. | The mapping is not automatic and is not necessarily gate-admissible. |
| **Gate admissibility** | The policy allows the specific resolved `data_readiness` claim to be used by technical fit after data-owner approval. | It does not mean the gate passes or the recommendation must improve. |

The M2 data model, UI and audit record must maintain this separation. A plain
customer answer may remain `RECORDED_ONLY` or `PRELIMINARY_UNDERSTANDING`; a
well-formed measurement may still be off-scope or inadequate for a particular
gate; a resolved criterion may still fail a gate for another reason.

## 4. Evidence that may change a decision

### 4.1 Evidence classes and default M2 posture

M2 should adopt the following classes from the evidence-admissibility design as
future GRW concepts. They do not replace the existing Phase 4
`InformationOrigin` enum.

| Evidence class | M2 record requirement | Default effect on a decision |
|---|---|---|
| `UNKNOWN` | Preserve the explicit absence of an answer, including “I do not know.” | Never resolves a criterion or gate; can close a question honestly. |
| `OPERATOR_PROVIDED_ESTIMATE` | Preserve verbatim wording, qualifier, range, unit, period, responder role when known, scope and time. | Record/preliminary only. Never silently becomes measured, document-supported, a midpoint or a score. |
| Free-text `OPERATOR_PROVIDED_FACT` | Preserve the exact claim, scope, source hint and author identity/role if volunteered. | Reviewable but not independently verified merely because it sounds precise. Not directly gate-admissible by default. |
| `STRUCTURED_ATTESTATION` | Versioned anchored question, exact answer, accountable responder and authority, scope, period, basis, known limitations and explicit attestation declaration. | May support a named criterion resolution only where a future policy row permits it, with the required accountable review. It is not measurement. |
| `DOCUMENT_SUPPORTED` | Immutable document identity/hash, version/date/authority where known, reviewed locator, exact supporting passage, scope/period and semantic-support rationale. | Candidate for criterion resolution and specified gate use only if the policy row and required review permit it. |
| `DATASET_SUPPLIED` | Dataset identity/hash, owner/access declaration, scope, sensitivity classification and minimisation record. | A handling state only. It is never a criterion or gate result by itself. |
| `MEASURED` | A reviewed reproducible measurement record over a specified dataset or system query, including method, fields, denominator, calculation, limitations and result. | Candidate for criterion and specified gate use only if the measurement addresses the exact policy claim. |
| `DERIVED` | Immutable inputs, accepted upstream evidence IDs/hashes, deterministic calculation/mapping rule and version, result and applicability check. | Cannot be stronger than its least sufficient input and cannot hide a subjective or circular mapping. |

No arbitrary percentage of answered gaps, amount of uploaded data, or evidence
count makes a reassessment eligible. One unresolved material uncertainty may
matter more than many complete low-priority answers.

### 4.2 Permission levels

Every reviewed evidence-to-criterion proposal must record one use-specific
permission. These are not a numeric confidence score.

| Permission level | Meaning |
|---|---|
| `RECORDED_ONLY` | Retained for audit, discussion or a later request; no formal input changes. |
| `PRELIMINARY_UNDERSTANDING` | Improves explanation, question routing or a future evidence request only. |
| `CRITERION_RESOLUTION` | Supports a named criterion or accountability resolution through a named instrument and required review. |
| `GATE_ADMISSIBLE_WITH_APPROVAL` | May satisfy a named material criterion for one specified gate under the pinned policy, scope and roles. |
| `INSUFFICIENT_FOR_THIS_USE` | Retained evidence that cannot support the requested claim. The record identifies the lightest credible next route. |

M2 may only include a proposed resolution in a successor formal assessment when
the supporting record is at least `CRITERION_RESOLUTION` and, if the criterion
is material to a reached gate, it is also explicitly
`GATE_ADMISSIBLE_WITH_APPROVAL` for that criterion/gate combination.

### 4.3 Criterion-specific posture

The admissibility-policy design supplies the proposed matrix. M2 should retain
its asymmetry rather than invent a global minimum-strength rule:

- `repetition` and `implementation_complexity` are currently priority-only.
  They cannot create priority or ROI before a recommendation is otherwise
  eligible for scoring.
- `ai_capability_fit`, `conventional_solution_fit`, and `data_readiness` are
  technical-fit material. Volume, cost or customer enthusiasm cannot clear
  them.
- `business_value` is gate material but an estimate alone cannot prove ROI or
  clear the business-value gate.
- `predictability`, `human_judgement_requirement`, `risk_consequence`,
  `residual_risk_with_human_oversight`, and
  `human_accountability_required` require heightened scrutiny. Weak evidence
  may justify caution; it must not lower an autonomy safeguard.

The exact allowed source/role combination per criterion and gate remains an
open policy-approval decision before implementation.

## 5. Criterion resolution

### 5.1 Eligibility

An M2 criterion-resolution proposal may target only:

1. an `UNKNOWN` input that appears in the pinned baseline approved review,
   integrated assessment and package gap record; or
2. an existing known/inferred criterion where new evidence is materially
   contradictory, stale, off-scope, or otherwise requires a successor review
   to revise the claim conservatively.

It must identify the process step, original gap where applicable, criterion,
baseline value/state, intended gate use, and all relevant evidence items. An
M2 answer must not establish that the historical process activity existed; that
continues to require baseline process evidence.

### 5.2 Who maps a resolution

The customer does not map their own answer to a criterion. M2 needs distinct
recorded acts:

| Act | Responsible party | Required record |
|---|---|---|
| Evidence acceptance | Qualified evidence reviewer | Provenance class, integrity, authority, scope, recency, semantic relevance, conflicts and permitted use. |
| Criterion mapping | Qualified domain reviewer | Criterion, raw evidence references, approved mapping instrument/version, proposed value/state, rationale, limitations and unresolved uncertainty. |
| Gate-admissibility decision | Reviewer plus required accountable owner | Exact gate/criterion use, policy row/fingerprint, whether requirements are met, rationale and role approval. |
| Reassessment approval | Explicit reassessment approver | Whole pinned request, material resolutions, conflicts, policy/instrument fingerprints and consent to create a successor formal decision. |

In the current local single-user product, labels do not prove independence or
authority. M2 must visibly record this limitation and show when the same person
performed multiple acts. It must not claim segregation of duties. A future
enterprise product may enforce roles, but M2 design must preserve the actor,
role, scope and approval data needed for that later control.

### 5.3 Ordinal criteria (0–5)

No natural-language answer, document passage, range or measurement automatically
becomes a 0–5 value. Each M2-supported criterion needs a separately approved,
versioned *criterion instrument* that defines:

- the intended construct and process-step scope;
- ordered anchors for values 0–5, including boundary cases;
- permitted source classes and review roles;
- whether a single source can suffice and required corroboration;
- handling for ranges, missing denominator, uncertainty and conflicting scope;
- prohibited mappings; and
- a stable identifier and canonical fingerprint.

The mapper proposes the value using that instrument; an approval record accepts
or rejects it. The raw range remains raw. M2 must never choose its midpoint,
round an approximate estimate, infer an optimistic band, or derive a score from
the target recommendation.

The successor criterion is normally `KNOWN` only when an approved resolution
has an allowed evidentiary basis. `INFERRED` remains reserved for the existing
model-inference semantics unless a separately approved future model changes
that contract. If no permitted resolution is reached, it stays `UNKNOWN` with a
rationale that explains why.

### 5.4 Accountability fields

`human_accountability_required` is a boolean but is no less consequential than
an ordinal criterion. M2 must keep its value separate from the evidence about
who approved it. A resolution needs, at minimum:

- an explicit statement of the accountable role and decision boundary;
- documented governance/procedure and, where policy permits, accountable-owner
  structured attestation;
- scope and conditions under which the boolean applies;
- a risk/compliance/legal review where the policy or context requires it; and
- a rationale that does not equate proposed human checking with low residual
  risk.

An estimate or unstructured statement cannot resolve that accountability is not
required, and an unresolved conflict must retain the conservative/unknown
state rather than remove the safeguard.

### 5.5 Projection and traceability

The approved M2 resolution must produce a successor reviewed assertion and a
successor Phase 1 criterion input with:

- its exact baseline value/state and successor value/state;
- resolution ID and all accepted/rejected/conflicting evidence IDs;
- evidence provenance, source hashes, locators, scope and measurement/calc
  records where relevant;
- mapping-instrument ID/fingerprint and admissibility-policy ID/fingerprint;
- named human decisions and rationales; and
- a precise statement of the gate uses for which the resolution is admissible.

The existing `EvidenceReference` is document-oriented and must not be
overloaded to imitate a dataset or attestation. M2 requires a new, explicitly
typed evidence/projection contract before implementation. Phase 5 must reject
any successor approval that claims a resolution without its pinned contract.

## 6. Conflict, scope and staleness handling

M2 must retain every submitted and reviewed claim. It never overwrites an old
claim with a newer one, or automatically favours the more precise, newer, or
apparently stronger source.

Before a criterion can be resolved, the reviewer compares claim, activity,
population, organisation, time period/timezone, unit, denominator, method,
authority and known limitations. The relationship is recorded as one of:

- `CONSISTENT`;
- `PARTIALLY_OVERLAPPING`;
- `CONTRADICTORY`;
- `DIFFERENT_SCOPE`;
- `STALE_OR_SUPERSEDED`; or
- `UNRESOLVED`.

| Situation | Required M2 behaviour |
|---|---|
| Customer answer conflicts with a document | Preserve both. Review their dates, authority and scope. The answer may be current context while the document supports historical scope, or neither may resolve the target. |
| Two documents conflict | Compare version, authority, draft/final status and scope. Newer does not automatically win. Record a reconciliation or retain the conflict. |
| Measurement conflicts with operator knowledge | First validate the population, filters, exclusions, time period, metric definition and data quality. The measurement may be off-scope or incomplete. |
| Sources cover different periods/scopes | Mark `DIFFERENT_SCOPE` or `PARTIALLY_OVERLAPPING`, not contradictory. A transfer to the target requires a recorded approved rationale. |
| New evidence contradicts baseline | Create a successor resolution only after qualified review. It may result in a lower score, retained unknown or `DO_NOT_RECOMMEND`; it must not be suppressed because it is inconvenient. |
| Material conflict cannot be reconciled | The requested resolution is `INSUFFICIENT_FOR_THIS_USE`; block reassessment for that resolution or produce a successor that explicitly preserves/introduces uncertainty if approval permits. |

An M2 request must list unresolved material conflicts. The reassessment approver
either rejects/defer the request, approves an explicitly narrower scope, or
approves a successor that retains the conflict as unknown. They cannot silently
choose the favourable interpretation.

## 7. Reassessment boundary and lifecycle

### 7.1 M1 is not a trigger

An M1 `PRELIMINARY_UNDERSTANDING`, `RECORDED_ONLY`, or rejection never
automatically starts M2. It may help select a next question, but it has no
formal decision effect. A customer may continue with the baseline package
without entering M2.

### 7.2 Proposed lifecycle

| State | Permitted action | Formal decision effect |
|---|---|---|
| `DRAFT` | Customer/reviewer collects optional evidence in a working area. | None. Drafts are not assessment inputs. |
| `SUBMITTED` | Immutable evidence submission is created. | None. |
| `EVIDENCE_REVIEWED` | Provenance, integrity, scope, conflict and permission level are reviewed. | None unless a later resolution is approved. |
| `RESOLUTION_PROPOSED` | A reviewer proposes a criterion or accountability resolution using an approved instrument. | None. |
| `REASSESSMENT_REQUESTED` | Immutable request pins the complete proposed successor input. | None. |
| `APPROVED_FOR_REASSESSMENT` | Explicit human approval authorises creation of the successor run. | Authorises, but does not itself change the baseline. |
| `SUCCESSOR_GENERATED` | New Phase 4 approval, Phase 5 assessment, Phase 6 package and comparison are persisted. | New formal decision exists alongside the baseline. |
| `REJECTED`, `BLOCKED_CONFLICT`, `STALE`, `WITHDRAWN` | The proposal is retained with reason. | None. |

The status record must be append-only or event-sourced. A correction creates a
new submitted item/review/resolution rather than editing the historical one.

### 7.3 Immutable reassessment request

The request is the only object that can authorise a successor assessment. It
must pin, at minimum:

| Pinned item | Reason |
|---|---|
| Baseline assessment/workspace identity and execution mode | Prevents cross-case attachment. |
| Baseline approved-review, integrated-assessment and Decision-Package IDs, revisions, canonical payload hashes and package ID | Makes the old decision immutable and independently comparable. |
| Baseline source document/candidate provenance and validated-process fingerprint | Preserves the before-process lineage. |
| Selected InformationGap IDs, step IDs and baseline criterion snapshots | Limits the request to reviewed scope. |
| Submitted evidence, evidence-review and conflict records, including hashes | Prevents later substitution of an apparently stronger source. |
| Accepted criterion-resolution proposals and rejected/retained uncertainty | Prevents a successor from using hidden assumptions. |
| Admissibility-policy ID/version/fingerprint and criterion-instrument ID/version/fingerprint | Makes permission and mapping rules reproducible. |
| Decision-policy ID/version/fingerprint expected for execution | Separates changed evidence from changed policy. A policy change requires a separately declared comparison boundary. |
| Human reviewers, required accountable-owner approvals, approver label, rationale and time | Makes authorisation explicit rather than inferred. |
| Dataset/document retention and withdrawal state where applicable | Keeps data use bounded and auditable. |

At approval, M2 validates every pinned hash and active baseline relationship.
If any changes, the request becomes `STALE`; it cannot silently bind to the
newer artefact. Approval must also reject an empty set of admissible,
decision-relevant resolutions.

## 8. Successor lineage and persistence boundary

### 8.1 Required lineage

The baseline remains immutable and independently readable:

```text
baseline workspace (remains PACKAGE_READY)
  APPROVED_REVIEW ──→ INTEGRATED_ASSESSMENT ──→ DECISION_PACKAGE
        │                         │                       │
        └──── pinned baseline references in M2 request ───┘
                                  ↓
    reviewed M2 evidence → approved criterion resolutions
                                  ↓
                     explicit reassessment approval
                                  ↓
successor reassessment run (separate active chain)
  SUCCESSOR_APPROVED_REVIEW ─→ SUCCESSOR_ASSESSMENT ─→ SUCCESSOR_PACKAGE
                                  ↓
                     deterministic comparison artifact
```

All arrows must be explicit parent references plus canonical payload hashes,
not inferred from timestamps, a title, or whichever active pointer happens to
be current.

### 8.2 Recommended architecture: a dedicated reassessment run

M2 should use a **dedicated reassessment-run/revision mechanism** in the same
local persistence boundary, not the existing `reset_to_review` path and not a
simple extra sidecar.

The exact physical design remains open, but the recommended logical design is:

- a new immutable `ReassessmentRun` root with its own ID;
- an exact baseline reference and approved reassessment request as its parents;
- a distinct successor-review snapshot derived from the pinned baseline review
  plus approved resolutions, not an in-place edit of that review;
- a distinct successor Phase 5/6 chain and its own active pointers; and
- a comparison artefact owned by the reassessment run, with the baseline and
  successor both pinned.

This may be implemented as a dedicated repository/table family or as a new
revision namespace with separate active-pointer scope. A new ordinary
`AssessmentRecord` alone is insufficient unless it preserves an explicit,
validated link to the baseline and avoids pretending that the baseline source
was newly ingested or extracted.

The present single-workspace active-pointer model can store historical
revisions, but it cannot safely represent two simultaneously active formal
decisions for one customer case without a new scope. Reusing it would make the
baseline non-current, deactivate M1 sidecars, and weaken the meaning of
“compare the current package with the new package.” M2 should choose auditability
over minimal code reuse.

### 8.3 Successor Phase 4 review

The successor approved review must be a new immutable review revision. It
includes:

- a byte-for-byte reference to the baseline approved review, not mutation of it;
- a restricted patch containing only approved M2 resolutions;
- the unmodified baseline values for every untouched assertion;
- a review event trail naming each changed criterion/accountability field;
- evidence/provenance/admissibility references for every changed field; and
- explicit retention of unknowns, rejected evidence and conflicts.

It must be possible to reconstruct the successor approved process from the
baseline review plus the approved patch and validate that no unapproved field
changed. An assessment service must fail closed if the projection contains a
value not justified by that patch.

## 9. Deterministic old-versus-new comparison

M2 must generate one immutable comparison after the successor package is
created. It is a read-only comparison; it cannot alter either package.

### 9.1 Comparison requirements

| Area | Required comparison |
|---|---|
| Baseline and successor identity | IDs, revisions, hashes, policy/instrument fingerprints, timestamps and reassessment request ID. |
| Gaps | Addressed, retained, newly discovered, rejected, conflicting and no-longer-applicable gaps, with reason. |
| Criteria | Old and new value, knowledge state, rationale/evidence IDs, resolution ID and provenance/permission change. |
| Evidence | Newly supplied evidence, class, scope/time, integrity hash, review result, conflicts and permitted use. |
| Gates | Gate order, evaluated/not-evaluated state, outcome, material criteria and rationale deltas. |
| Recommendation | Old/new recommendation modes and a factual explanation of the causal chain through criterion/gate deltas. |
| Priority | Old/new eligibility, status and factors. No priority is fabricated when gates remain blocked. |
| ROI/benefit statement | Exact before/after statement, availability and limitations. A new number is not labelled realised ROI. |
| Package completeness | Information-gap counts/categories and whether significant decision-critical uncertainty remains. |

The comparison should distinguish:

- `NO_FORMAL_CHANGE` — admissible evidence did not alter a mapped input or did
  not alter the eventual package;
- `EVIDENCE_OR_PROVENANCE_CHANGE_ONLY` — a traceability change without a
  policy-result change;
- `CRITERION_CHANGE`;
- `GATE_CHANGE`;
- `RECOMMENDATION_CHANGE`; and
- `UNCERTAINTY_INCREASED`.

These are descriptive labels, not performance measures.

### 9.2 Honest language

For example:

> `INVESTIGATE_FURTHER → AUGMENT` means the formal recommendation changed
> after specifically approved additional evidence under the pinned policy and
> instrument. It does not establish successful AI adoption, realised benefit,
> return on investment, safe deployment, or a future outcome.

Likewise, `AUGMENT → DO_NOT_RECOMMEND` is a valid and useful result when
stronger evidence identifies a limitation or risk. The UI must never badge a
more favourable recommendation as “success.”

## 10. Customer experience and progressive evidence collection

M2 should be progressive, optional and plain-English.

### 10.1 Customer-facing flow

1. **Start with the baseline.** Show the existing Decision Package and explain:
   “Your current information is enough for an initial assessment. These are the
   few facts that could most strengthen this decision.”
2. **Show prioritised questions, not raw gaps.** Start with decision-critical
   gaps; do not expose all internal `InformationGap` rows or a completion score.
3. **Invite a simple answer first.** For example: “Approximately how often does
   this activity happen? A range is fine.” Clearly label it as an estimate and
   explain it does not change the current formal decision.
4. **Explain the lightest stronger option only when relevant.** For example:
   “If available, an operational report or export for a defined period could
   provide stronger support for this point.” Do not default to requesting CSV.
5. **Collect bounded supporting evidence.** State the requested period, scope,
   fields or document passage, why it matters, and that it will be reviewed.
6. **Show review status transparently.** Customer sees whether evidence was
   accepted, insufficient, off-scope, conflicting, recorded only, or eligible
   for a proposed formal resolution.
7. **Require an explicit reassessment request.** Show exactly what would be
   reconsidered and what will remain unknown. There is no automatic rerun.
8. **Show both packages after approval.** Explain what changed, what did not,
   what evidence caused it, and what remains uncertain.

Internal criterion names such as `repetition_frequency` or
`data_readiness` should not be customer prompts. The customer sees ordinary
business questions, while authorised reviewers can inspect the mapped
criterion, policy row and evidence record.

### 10.2 Prioritisation

M2 should use the GRW categories without numeric completion thresholds:

- `DECISION_CRITICAL`: evidence that could block or materially change the
  current decision;
- `DECISION_STRENGTHENING`: evidence that may improve confidence or the
  business/adoption basis;
- `EXECUTION_STAGE`: information useful later for business case, pilot or
  delivery but not necessary for this decision; and
- `SUPPORTING_LOW_PRIORITY`: useful context with no immediate decision need.

Priority is a question-selection/routing feature. It is not an admissibility
decision and does not make an unresolved critical risk gap disappear.

## 11. Operational-data and privacy boundary

M2 may eventually accept data exports, but only within a defined data boundary.
This section is a design minimum, not enterprise infrastructure.

### 11.1 Data/export acceptance

Before accepting an operational file or query result, M2 needs:

- an explicit intended metric and relevant criterion/gate use;
- approved population, organisation/process/step scope, date range and timezone;
- a declared data owner/collector and authority to provide it;
- dataset/export ID and immutable content hash;
- source system, export/query method and version where known;
- fields, units, identifiers, denominator and join rules;
- declared inclusion/exclusion, sampling, deduplication and missing-data treatment;
- a minimisation record showing only required fields are retained;
- sensitivity classification and a prohibition on secrets/credentials; and
- retention/withdrawal status.

An upload begins only as `DATASET_SUPPLIED`. It becomes `MEASURED` only after a
reviewed measurement record pins the calculation/formula/query version,
result, rounding, limitations and reproducibility conditions.

### 11.2 Data minimisation and sensitive content

M2 should request aggregated or de-identified data whenever it can answer the
question. Direct identifiers, credentials, special-category information,
customer content and unrelated operational fields are out of scope unless a
future approved policy and access boundary specifically permits them.

The product must explain what is needed and what is not needed. Raw data must
not be sent to extraction providers, LLMs, analytics systems or external
services merely because it was uploaded to GRW.

### 11.3 Reproducibility, retention and withdrawal

A measurement record must let an authorised reviewer reproduce the result from
the same source or explain why an immutable snapshot cannot be rerun. Deleting
or withdrawing raw data must not silently rewrite an approved reassessment:

- retain the immutable decision record, its hashes, provenance and withdrawal
  event as required by the future retention policy;
- mark affected measurements/reassessments as withdrawn, unavailable or stale;
- do not claim a result remains reproducible when its source has been removed;
- preserve the baseline package and any successor package as historical
  decision records unless a separately approved deletion policy requires a
  lawful exception.

Encryption, tenancy, authentication, retention execution, key management,
fine-grained access control and audit export are enterprise-productisation
work, explicitly outside M2 implementation planning.

## 12. Human approvals and local-product limitation

| Decision | Minimum required approval | Extra condition |
|---|---|---|
| Evidence class/scope acceptance | Qualified evidence reviewer | Must record provenance, integrity, scope, conflict and use-specific permission. |
| Ordinary ordinal criterion resolution | Domain reviewer using the approved instrument | Must preserve raw evidence and mapping rationale. |
| Business-value gate use | Business owner plus reviewer | Transparent inputs/assumptions; never a claim of proven ROI. |
| Data-readiness gate use | Data owner plus reviewer | Document/control support or validated profile as the policy requires. |
| Risk/autonomy/accountability resolution | Domain/risk reviewer and accountable risk owner; legal/compliance where applicable | High-consequence use needs corroboration. An estimate cannot clear safeguards. |
| Reassessment request | Explicit reassessment approver | Reviews all material resolutions, conflicts and pinned policy/instrument versions. |

The local M2 product may capture labels and declarations but cannot yet verify
identity, role authority, independence or separation of duties. It must display
that fact where it matters. A single-user proof-of-concept must not present a
self-review/self-approval as independently governed. High-consequence
automation or accountability conclusions should be blocked or clearly marked
as not eligible until the required external approvals and future role controls
are in place.

## 13. Failure and honest outcomes

M2 must make all of the following first-class terminal outcomes:

| Outcome | Required result |
|---|---|
| Evidence rejected | Preserve it, the reason and its relation to the gap; do not create a resolution. |
| Evidence accepted but criterion remains unknown | Show why it is insufficient for the requested use and the lightest credible next evidence route. |
| Criterion resolved, recommendation unchanged | Generate comparison showing the resolved input and the independent gate/recommendation reason that remains. |
| Recommendation becomes more favourable | Describe a policy-governed decision change only; do not claim adoption success or realised value. |
| Recommendation becomes less favourable | Preserve it as a valuable safety result; do not hide conflicting or adverse evidence. |
| New evidence introduces uncertainty | Include the new uncertainty/conflict in the successor review and comparison; the result may become more cautious. |
| Material conflict prevents reassessment | Keep the baseline active, mark the request blocked, and retain all evidence/review records. |
| Baseline/request becomes stale | Do not reroute it to a newer package. Require an explicit new request pinned to the desired baseline. |

## 14. Recommended M2 minimal milestone

### 14.1 Recommendation: one document-supported data-readiness path

The safest first M2 implementation should prove **one
`DOCUMENT_SUPPORTED` resolution of `data_readiness`**, not measured-data
ingestion.

The candidate M2 path is:

```text
package with a selected UNKNOWN data-readiness gap
        ↓
customer provides one bounded supporting document
        ↓
reviewer verifies document identity, exact passage, source/scope/period
        ↓
data owner and reviewer use one approved data-readiness instrument
        ↓
explicit reassessment approval
        ↓
successor review/assessment/package/comparison
```

This deliberately requires a synthetic, package-ready fixture where all
earlier technical-fit requirements—including direct `ai_capability_fit` and
capability mapping—are already satisfied by admissible baseline evidence.
That allows the milestone to show whether the data-readiness gate evaluates
differently without manufacturing the earlier prerequisite.

### 14.2 Why document-supported before measured

`DOCUMENT_SUPPORTED` is the safer first decision-affecting path because:

- the current engine already has reviewed document evidence, locators and
  projection tests, so M2 extends a familiar evidentiary form rather than
  pretending an upload is measurement;
- a single bounded document can exercise source identity, semantic review,
  scope, criterion mapping, policy permission, human approval, successor
  lineage and comparison without accepting customer operational data; and
- `MEASURED` requires the unimplemented dataset, privacy, calculation,
  reproducibility, retention and withdrawal boundary described above. It would
  combine too many high-risk unknowns into the first decision-affecting change.

M2-minimum still must not treat document support as enough merely because it is
a document. The supporting passage needs a data-readiness-specific instrument,
data-owner approval, criterion mapping and gate-use approval.

### 14.3 M2-minimum acceptance properties

The first implementation should prove all of these using fresh synthetic
workspaces only:

- baseline approved review, assessment and package remain byte-identical and
  active after the successor is created;
- one immutable supporting-document submission, review, resolution and
  reassessment approval are fully hash-pinned;
- a successor run can alter only the approved `data_readiness` assertion;
- every untouched successor review assertion is provably equal to its baseline;
- Phase 5 and 6 run only after explicit reassessment approval;
- the successor uses the pinned decision policy and approved instrument;
- the comparison reports criterion/gate/recommendation/priority/ROI deltas;
- unchanged, more favourable and less favourable outcomes remain possible;
- no frozen PORT workspace, manifest or production baseline is opened for
  M2 mutation; and
- no data upload, CSV analysis, measurement, automatic approval or AEL action
  is included.

## 15. Explicit boundaries

M2 does not implement or claim:

- implementation management, pilots, deployment, rollout or change management;
- measured business outcomes, realised savings, ROI proof or causal benefit;
- portfolio learning, calibration, model training or a feedback loop;
- AEL, business-case workflow or execution governance;
- automatic evidence acceptance, criterion mapping, gate approval or
  reassessment approval;
- retroactive mutation of a baseline Decision Package, review or assessment;
- rewriting or opening frozen PORT/evaluation workspaces for M2 mutation;
- a generic data lake, CSV analytics product, API, multi-user architecture,
  authentication, tenancy or enterprise infrastructure; or
- a design goal of producing more `AUGMENT`/`AUTOMATE` recommendations.

The current decision policy, taxonomy, prompts and Phase 1–7 product semantics
remain unchanged until separately approved implementation work.

## 16. Relationship to the future AEL

The intended boundary is:

```text
Engine
  ↓
Decision Package
  ↓
GRW M1 / M2
  ↓
better-supported Decision Package
  ↓
explicit human decision to proceed
  ↓
future Adoption Execution Layer
```

GRW asks: “Do we now have enough admissible, reviewed evidence to make a
stronger adoption decision?” It stops at an evidence-grounded Decision Package.

The future AEL asks: “Now that the organisation has chosen to proceed, how do
we govern, pilot, implement and measure it?” It owns initiatives, business
cases, pilots, deployment, operating controls and measured outcomes. AEL must
not be inferred from an M2 recommendation change.

Before handoff to AEL, the organisation should have an explicit human decision
to proceed, a current package with known limitations, identified accountable
owner/sponsor, unresolved decision-critical risks accepted or bounded, and the
scope/guardrails required by the selected action. The precise AEL entry criteria
remain future product design.

## 17. Open decisions requiring approval before M2 implementation

### Architecture and persistence

1. Approve a dedicated `ReassessmentRun`/successor lineage rather than the
   current reset-to-review path.
2. Choose the physical persistence design: dedicated tables/repository versus a
   separately scoped revision namespace; define migration, retention and
   deletion semantics.
3. Define the successor review/projection contract and how it interoperates
   with current `ApprovedProcessReview`, `EvidenceReference` and Phase 5
   validation without falsifying existing provenance meanings.
4. Specify active-pointer semantics for a baseline plus one or more successor
   packages, including customer navigation and comparison selection.
5. Define idempotency, stale-request, withdrawal and retry behaviour for every
   reassessment lifecycle transition.

### Methodology and policy

6. Approve the actual admissibility-policy version, per-criterion/gate matrix,
   role requirements, and canonical fingerprinting method.
7. Approve the first `data_readiness` criterion instrument with 0–5 anchors,
   boundary cases, scope rules and prohibited mappings.
8. Decide whether structured attestation is allowed in the first M2 release;
   the recommendation is **no** until a role/authority contract is approved.
9. Define when a document may be treated as semantically sufficient for a
   data-readiness claim and whether corroboration is mandatory.
10. Decide the treatment of a policy-version change between baseline and
    successor: block it in M2-minimum, or allow it only as an explicitly
    separated evidence-and-policy comparison.
11. Define conflict materiality, escalation criteria and who can approve a
    narrower-scope reassessment.

### Data, privacy and product

12. Approve the document intake boundary for M2-minimum: permitted formats,
    scanning/storage controls, size limits, source identity and retention.
13. Before any measured-data milestone, approve dataset fields, sensitive-data
    handling, hashing, reproducibility, calculation review, retention,
    withdrawal and deletion policy.
14. Decide the minimum acceptable local-product disclosure and whether M2 must
    prohibit high-consequence risk/accountability resolutions until real
    identity/role controls exist.
15. Approve customer-facing question catalogue, priority-routing logic and the
    product wording for rejected, uncertain and less-favourable outcomes.
16. Approve the comparison schema/copy so it cannot frame recommendation
    movement as prediction accuracy, implementation success or ROI proof.

No M2 implementation should start until these decisions are resolved for the
chosen narrow milestone.
