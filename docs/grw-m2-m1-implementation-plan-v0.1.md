# GRW M2 M1 implementation plan

Status: **IMPLEMENTATION PLAN ONLY — APPROVAL REQUIRED BEFORE CODING**  
Version: v0.1  
Date: 2026-08-20  
Governing contract: [GRW M2 pre-implementation decisions v0.1](grw-m2-preimplementation-decisions-v0.1.md), limited to its approved M2 M1 boundary.  
Depends on: frozen GRW M1 governing designs/implementation and [GRW M2 reassessment design v0.1](grw-m2-reassessment-design-v0.1.md).  
Scope: one document-supported `data_readiness` reassessment path. This plan
changes no code, migration, policy, prompt, taxonomy, portfolio or frozen
evaluation artefact.

## 1. Exact M2 M1 boundary

M2 M1 is one controlled decision-affecting path only:

```text
one package-ready baseline
        ↓
one UNKNOWN data_readiness criterion
        ↓
one new plain-text supporting document
        ↓
reviewed document evidence
        ↓
human-reviewed data-readiness resolution under one versioned instrument
        ↓
explicit reassessment approval
        ↓
separate immutable successor review
        ↓
new Phase 5 assessment
        ↓
new Phase 6 Decision Package
        ↓
deterministic baseline-versus-successor comparison
```

The baseline approved review, integrated assessment, Decision Package, active
pointers, assessment row and M1 artefacts remain byte-identical and active. M2
M1 must never call `reset_to_review`, `ingest_upload`, `extract`,
`start_review`, `save_review`, `approve`, `assess`, or `generate_package` on
the baseline `AssessmentWorkspaceService`.

M2 M1 supports neither general evidence collection nor a general reassessment
engine. It supports no PDF/Office document, CSV/data export, measured/derived
evidence, structured attestation, free-text-to-score mapping, risk/autonomy/
accountability resolution, decision-policy change, successor promotion, AEL or
deployment workflow.

## 2. Proposed implementation architecture

### 2.1 Deliberate separation of the two chains

```text
baseline AssessmentWorkspace (untouched; stays PACKAGE_READY)
  APPROVED_REVIEW → INTEGRATED_ASSESSMENT_RESULT → DECISION_PACKAGE_RESULT
         ↑                     ↑                           ↑
         └──────────────── immutable M2BaselineReference ──┘
                                      │
                                      ▼
M2 ReassessmentRun (separate tables and active-pointer namespace)
  RUN_MANIFEST
    → SUPPORTING_DOCUMENT_SUBMISSION
      → DOCUMENT_EVIDENCE_REVIEW
        → DATA_READINESS_RESOLUTION
          → REASSESSMENT_REQUEST
            → REASSESSMENT_APPROVAL
              → SUCCESSOR_APPROVED_REVIEW
                → SUCCESSOR_INTEGRATED_ASSESSMENT
                  → SUCCESSOR_DECISION_PACKAGE
                    → BASELINE_SUCCESSOR_COMPARISON
```

The M2 chain is append-only. Its active pointer exists only within a
`reassessment_run_id`; it is never inserted into `active_artifacts` for the
baseline assessment. A baseline package is selected through exact ID, revision
and SHA-256 references, not by whichever historical artefact has a recent
timestamp.

### 2.2 New service boundaries

| Component | Responsibility | Explicitly does not do |
|---|---|---|
| `M2ReassessmentService` | Validates M2 lifecycle transitions, baseline references, permissions, conflicts, staleness and non-change conditions. | Mutate any baseline workspace artefact or call reset/re-ingestion. |
| `SQLiteReassessmentRepository` | Owns only M2 run/documents/artefacts/pointers/operations in the same database. | Update `assessments`, `assessment_artifacts`, `active_artifacts` or `assessment_operations`. |
| `SuccessorReviewProjector` | Creates one successor process/input from a hash-pinned baseline plus one approved patch. | Reuse Phase 4 mutation, invent a score, or alter any non-target field. |
| `IntegratedAssessmentService.assess_successor` | Validates an M2 successor input then uses the existing deterministic Phase 5 engine path. | Accept unapproved M2 evidence or relax Phase 5 checks. |
| Existing `DecisionSupportPackageService.generate` | Generates a normal Phase 6 package from the validated successor `IntegratedAssessmentSuccess`. | Know or alter baseline state. |
| `M2ComparisonService` | Compares two immutable packages and their pinned inputs deterministically. | Score success, rerun assessment, or promote a successor. |

The `M2ReassessmentService` must be composed independently from
`AssessmentWorkspaceService`, using the latter only as a read-only source of
the baseline repository and artefacts.

## 3. Exact domain models and artefact contracts

All models below use `ConfigDict(extra="forbid", frozen=True)`. Customer
working drafts stay only in Streamlit session state and are never formal inputs.

### 3.1 Shared immutable references

| Model | Required fields |
|---|---|
| `M2ArtifactReference` | `artifact_id`, `artifact_revision`, `payload_sha256`. |
| `M2BaselineReference` | baseline `assessment_id`, execution mode, source document ID, approved-review/integrated-assessment/package references, package ID, validated-process fingerprint and decision-policy ID/version/status/fingerprint. |
| `M2StepGapReference` | package ID, step ID, activity, original `InformationGap` snapshot, baseline `data_readiness` criterion snapshot and the baseline technical-fit gate snapshot. |
| `VersionedPolicyReference` | ID, version, canonical SHA-256 fingerprint. Used independently for M2 admissibility policy and data-readiness instrument. |
| `M2ActorDeclaration` | display label, declared role, acknowledgement that authority/independence is not verified locally, timestamp. |

`M2BaselineReference` is valid only when all three baseline artefacts still
form the normal active chain and their package/integrated/approval payloads
match the stored references. It also requires a successful package and an
`UNKNOWN` `data_readiness` criterion for the selected step.

### 3.2 M2 document and evidence contracts

| Contract | Required fields and invariants |
|---|---|
| `M2SupportingDocument` | `document_id = "doc-" + content_sha256`, `content_sha256`, `content_type = text/plain`, original filename/label, byte length, received timestamp, declared source/authority, stored-byte reference. The raw bytes live in the M2 document table, not in JSON artefacts. |
| `M2DocumentLocator` | UTF-8 character start/end offsets, inclusive line start/end and exact excerpt. Validation must prove the excerpt equals the stored text slice; it cannot be a reviewer paraphrase. |
| `M2DocumentSubmission` | baseline/run/step/gap references, document reference, customer declaration, submission timestamp and provenance class fixed to `DOCUMENT_SUPPORTED_CANDIDATE`. Submission is immutable. |
| `M2EvidenceReview` | parent submission ID/hash, reviewer declaration/rationale, document identity, source/authority, scope/period, semantic-support finding, limitations, conflict finding, and permission result: `REJECTED`, `INSUFFICIENT_FOR_THIS_USE`, or `CRITERION_RESOLUTION_AND_GATE_ADMISSIBLE`. |

M2 M1 never represents the document as Phase 2 extraction evidence. It is a
new, separately identified supporting document. Its source locator is
reproducible within that document only.

### 3.3 Resolution, request and approval contracts

| Contract | Required fields and invariants |
|---|---|
| `M2DataReadinessResolution` | parent evidence-review ID/hash; target exactly `CriterionName.DATA_READINESS`; baseline state/value snapshot; proposed value in `0..4` or explicit retained `UNKNOWN`; knowledge state; full mapping rationale; all document locators; data-owner declaration; reviewer declaration; policy and instrument references; permitted gate exactly `TECHNICAL_FIT`. |
| `M2ReassessmentRequest` | baseline reference; selected gap; evidence review and resolution references/hashes; conflict record; data-owner and criterion-review declarations; M2 policy/instrument references; pinned baseline decision-policy fingerprint; canonical request hash; request time. It must reject no-op, rejected, insufficient, unresolved-material-conflict or non-admissible resolutions. |
| `M2ReassessmentApproval` | parent request ID/hash; approver declaration/rationale/time; acknowledgement of the exact change, retained uncertainty, conflict status and no verified role separation; assessment effect limited to authorising the successor. |

M2 M1 permits only one document, one evidence review and one resolution per run.
A new answer/evidence item creates a different run; nothing is edited or
overwritten.

### 3.4 Successor decision contracts

| Contract | Required fields and invariants |
|---|---|
| `M2SuccessorApprovedReview` | baseline approved-review reference/hash, approval reference/hash, exact changed field path, `M2DataReadinessResolution`, successor review/approval IDs, successor `BusinessProcess`, successor trace map and canonical successor-process fingerprint. Every field other than selected `data_readiness` must deep-equal the baseline projection. |
| `M2SuccessorAssessment` | parent successor review reference; inner `IntegratedAssessmentSuccess`; M2 lineage including run/request/approval/evidence/resolution/policy/instrument references. The inner result must use the same decision-policy fingerprint as baseline. |
| `M2SuccessorDecisionPackage` | parent successor assessment reference; inner `DecisionPackageSuccess`; package ID/hash; same M2 lineage. |
| `M2BaselineSuccessorComparison` | exact baseline package/integrated/approval references; successor review/assessment/package references; all data-readiness, gate, recommendation, priority, ROI statement, package completeness and gap deltas; neutral comparison categories. |

The standard Phase 5 and Phase 6 payloads remain their existing types inside
the M2 wrapper artefacts. The wrappers hold M2-specific lineage rather than
changing the historical Phase 4–6 artefact schema in place.

### 3.5 M2 run state and artefact types

`M2RunStage` is distinct from `WorkflowStage`:

```text
OPEN
→ DOCUMENT_SUBMITTED
→ EVIDENCE_REVIEWED
→ RESOLUTION_PROPOSED
→ REQUESTED
→ APPROVED
→ SUCCESSOR_REVIEW_READY
→ ASSESSED
→ PACKAGE_READY
→ COMPARED
```

Terminal non-success paths are `EVIDENCE_REJECTED`, `INSUFFICIENT`,
`BLOCKED_CONFLICT`, `STALE`, `WITHDRAWN`, `FAILED`. A terminal state preserves
all preceding immutable rows.

`M2ArtifactType` contains exactly:

```text
RUN_MANIFEST
DOCUMENT_SUBMISSION
EVIDENCE_REVIEW
DATA_READINESS_RESOLUTION
REASSESSMENT_REQUEST
REASSESSMENT_APPROVAL
SUCCESSOR_APPROVED_REVIEW
SUCCESSOR_INTEGRATED_ASSESSMENT
SUCCESSOR_DECISION_PACKAGE
BASELINE_SUCCESSOR_COMPARISON
```

Each type has an exact allowed parent, apart from `RUN_MANIFEST`, which is the
run root. Replacement is never allowed.

## 4. Separate active-pointer semantics and persistence

### 4.1 Dedicated M2 SQLite structures

The implementation adds a new migration in the existing local SQLite database
for these tables only:

| Table | Purpose |
|---|---|
| `reassessment_runs` | Run ID, baseline assessment/package identity and hashes, run stage, created/updated times, row version. No mutation of the baseline assessment row. |
| `reassessment_documents` | Immutable `text/plain` bytes, content hash, identity/metadata and run ID. |
| `reassessment_artifacts` | Immutable typed JSON payload, SHA-256, run ID, type, revision, parent ID, schema version and timestamps. |
| `active_reassessment_artifacts` | One active M2 artefact per type per run. It is disjoint from `active_artifacts`. |
| `reassessment_operations` | M2-specific idempotency key, status, produced artefact ID and sanitised error code. |

Foreign keys must validate baseline assessment/artifact IDs as existing rows but
must not cascade from M2 to baseline data. M2 document/artifact deletion is
prohibited in M2 M1. SQLite parameterised queries, canonical JSON serialization
and SHA-256 validation follow the existing persistence pattern.

### 4.2 Separate repository

Create `SQLiteReassessmentRepository` rather than adding M2 methods to
`AssessmentRepository`. It has:

- `create_run(baseline_reference)`;
- immutable `save_artifact_and_advance(run_id, ...)`;
- `load_run(run_id)` with full M2 parent-chain validation;
- `load_document(document_id)` and `save_document_and_submission(...)` in one
  transaction;
- `begin_operation`, `complete_operation`, `fail_operation`; and
- read-only baseline verification helpers.

It has no method to update normal `assessment_artifacts`, normal
`active_artifacts`, or `assessments`.

### 4.3 Frozen evaluation write protection

Create a reusable, pure path predicate such as
`assert_m2_write_target_allowed(database_path)`. It resolves the configured
database path and refuses when the path has both `evaluation` and `portfolio`
as path components.

It must run:

1. before `SQLiteReassessmentRepository` opens a connection or executes its
   migration/DDL;
2. at the first line of every M2 service mutation—run creation, document
   submission, evidence review, resolution, request, approval, successor
   review, assessment, package generation and comparison; and
3. in the composition factory before it constructs a write-capable M2 service.

This is defence in depth. UI absence is never a guard. Reads may inspect a
normal baseline, but a protected target is refused without opening or changing
the protected database. The M1 guard is not reused implicitly; M2 has its own
all-write-path coverage.

## 5. Supporting-document intake and source locators

### 5.1 Narrow intake contract

M2 M1 accepts one UTF-8 `text/plain` file only. The client sends bytes and a
display filename. The service must:

1. enforce a bounded maximum byte size set as a named M2 M1 constant;
2. reject a non-text media type, invalid UTF-8, empty/whitespace-only text and
   any second document for the run;
3. compute SHA-256 over the original bytes before decoding;
4. derive `document_id = doc-<sha256>`;
5. store exactly those bytes locally in `reassessment_documents`; and
6. display a notice not to include secrets, credentials or unnecessary
   personal data.

The plan deliberately does not reuse ordinary process ingestion. There is no
PDF extraction, LLM/external-provider call, document summarisation, CSV import
or data profiling.

### 5.2 Locator creation

The evidence reviewer selects an exact excerpt from the stored decoded text.
The service derives, rather than trusts, its character offsets and line range.
`M2DocumentLocator` validation re-slices the stored text to prove that the
submitted excerpt is byte/character-consistent with the content hash.

The locator format is:

```text
document_id: doc-<sha256>
source_locator: lines <start>-<end>; chars <start>-<end>
exact_excerpt: exact decoded source slice
```

The reviewer records a scope/period statement separately. An excerpt with no
clear relationship to the baseline activity is insufficient; it cannot be
generalised automatically.

## 6. Approved M2 M1 policy fragment and instrument

### 6.1 Admissibility policy configuration

Create one immutable canonical JSON configuration:

```text
policy_id: grw_m2_m1_data_readiness_admissibility
version: 0.1.0
allowed_evidence_class: DOCUMENT_SUPPORTED
allowed_criterion: data_readiness
allowed_gate: technical_fit
required: document hash, exact locator, same-step scope, stated period or
          explicit period limitation, semantic review, declared data owner,
          criterion reviewer, reassessment approver, no unresolved material conflict
permitted_effects: CRITERION_RESOLUTION, GATE_ADMISSIBLE_WITH_APPROVAL
prohibited: estimates, free text, M1 sidecars, attestation, dataset, measured,
            derived, direct criterion mutation, policy change
```

The service canonicalizes the loaded JSON and stores its SHA-256 in every
evidence review, resolution, request, approval, successor review and comparison.
It is an M2 admissibility policy, not a modification of `decision_policy.v0.2`.

### 6.2 Data-readiness instrument configuration

Create one canonical JSON instrument:

```text
instrument_id: grw_m2_m1_data_readiness_document_instrument
version: 0.1.0
criterion: data_readiness
allowed_values: [0, 1, 2, 3, 4]
value_5: prohibited; a measured profile is required in a future milestone
```

The approved anchors are:

| Value | Document-supported meaning for M2 M1 |
|---|---|
| 0 | The document establishes that required data is absent or inaccessible for the target activity. |
| 1 | The document identifies only a claim or isolated example; required fields, scope or access/control are not established. |
| 2 | The document identifies some relevant fields and a usable limited source, with material coverage, access/control or quality limitations retained. |
| 3 | The document identifies relevant fields, target-step scope and an available source, while retaining stated coverage/quality/control limitations. |
| 4 | The document identifies relevant fields, target-step scope, available access/ownership/control and material limitations sufficient for the stated assessment use; it does not prove measured quality or deployment readiness. |

The reviewer must select one anchor and explain why the exact excerpt meets it.
The instrument must offer `RETAIN_UNKNOWN`; it does not turn a range into a
score and does not by itself pass technical fit. The deterministic gate retains
the existing policy thresholds unchanged.

## 7. M2 workflow operations

### 7.1 Open a reassessment context and run

`open_m2_m1_context(assessment_id)` is read-only. It validates the active
baseline chain and selects exactly one `UNKNOWN` `data_readiness` gap from a
successful active Decision Package. It additionally verifies the target step’s
baseline technical prerequisites, described in §13.

`create_m2_run(context)` is the first write. It validates the full baseline
hash chain, creates the immutable run manifest, and retains baseline artefact
references. It never changes the baseline assessment’s stage or row version.

### 7.2 Submit and review one document

`submit_supporting_document(run_id, content_bytes, filename, source_label)`:

- applies frozen-workspace guard first;
- verifies run is `OPEN` and current baseline references still match;
- applies the intake contract in §5;
- persists raw bytes and document-submission artefact atomically; and
- advances only the M2 run stage to `DOCUMENT_SUBMITTED`.

`review_document_evidence(run_id, submission_id, reviewer, locator, scope,
period, source_authority, semantic_rationale, limitations, conflict_status,
permission)`:

- requires the exact active submission parent/hash;
- validates locator against stored bytes/text;
- permits only document evidence and the approved M2 policy fragment;
- rejects an unsupported permission result;
- records conflict status and never overwrites baseline evidence; and
- yields `EVIDENCE_REVIEWED`, `EVIDENCE_REJECTED`, `INSUFFICIENT` or
  `BLOCKED_CONFLICT` within the M2 run only.

### 7.3 Criterion-resolution review

`propose_data_readiness_resolution(...)` requires the active accepted evidence
review and all required document-policy fields. It requires:

- target field exactly `data_readiness` and the pinned baseline step/gap;
- review decision with `CRITERION_RESOLUTION` and
  `GATE_ADMISSIBLE_WITH_APPROVAL` permission;
- one M2 instrument value 0–4 or explicit `RETAIN_UNKNOWN`;
- a declared data owner and criterion reviewer, both with rationale;
- mapping rationale tied to exact document locator(s); and
- no unresolved material conflict.

It cannot mutate a `ReviewedAssertion`, criterion, `BusinessProcess` or active
Phase 4 artefact. It creates only an immutable M2 resolution proposal.

### 7.4 Request and explicit approval

`request_reassessment(run_id, resolution_id)` creates a canonical snapshot of
every artefact/hash/configuration needed for the successor. It fails if the
resolution retained unknown, is non-admissible, is not data readiness, has a
material conflict, or the baseline/policy/instrument is stale.

`approve_reassessment(run_id, request_id, approver, rationale)` is the only
operation that permits a successor. It repeats all request validation and
requires an explicit acknowledgement that:

- the baseline remains unchanged;
- the successor changes one specified data-readiness input only;
- local labels do not verify independence or authority; and
- a changed recommendation is not an adoption-success or ROI claim.

No M1 artefact, estimate, free-text answer or UI action automatically creates
an M2 request or approval.

## 8. Constructing the successor approved process

### 8.1 Do not mutate or forge Phase 4

M2 must not call `ProcessReviewService.correct_assertion` with the supplemental
document: current Phase 4 correctly rejects evidence outside the original
candidate document. It also must not create a fake Phase 3 extraction result
for the document or pretend the document was a baseline source.

### 8.2 Successor projection algorithm

`SuccessorReviewProjector.build(approved_request)` performs only these steps:

1. Load the hash-pinned baseline `ApprovedProcessReview` read-only.
2. Load the baseline `BusinessProcess` projection and deep copy it in memory.
3. Locate exactly the pinned process step and its `data_readiness` input.
4. Assert every non-target process field deep-equals the baseline before
   patching.
5. Construct an `EvidenceReference` for the M2 document with its own document
   ID/locator/excerpt and explicit provenance text:
   `M2 reviewed supporting document; document ID <id>; policy <fingerprint>`.
6. Replace only that copied step’s `data_readiness` input with the approved
   M2 value/state/rationale and the new M2 evidence ID.
7. Append the new evidence reference to the copied process evidence list;
   preserve all baseline evidence references and IDs unchanged.
8. Build successor trace data that points to the baseline review field plus the
   M2 resolution/evidence review, never a Phase 3 field path for the new
   document.
9. Revalidate `BusinessProcess`, compare untouched fields recursively, and
   calculate the successor process fingerprint.

The successor review model records the baseline source document and extraction
lineage as historical process provenance, and the M2 document as supplemental
evidence. The two source roles are visible and not interchangeable.

## 9. Safe Phase 5 invocation

### 9.1 Required refactor, not bypass

`IntegratedAssessmentService.assess` currently accepts only
`ApprovedProcessReview` and internally validates its Phase 4 projection. M2
must not instantiate `AssessmentEngine` directly or hand-edit an
`IntegratedAssessmentSuccess`.

Refactor the service into two validated input adapters feeding one shared
private assessment path:

```text
assess(ApprovedProcessReview)
  → validate existing Phase 4 approval/projection
  → ValidatedAssessmentInput
  → _assess_validated_input(...)

assess_successor(M2SuccessorApprovedReview)
  → validate M2 lineage, one-field patch, policy/instrument/evidence pins
  → ValidatedAssessmentInput
  → _assess_validated_input(...)
```

`_assess_validated_input` owns the existing policy load/fingerprint, deterministic
`AssessmentEngine` call, process/step output validation and traceability
validation. Existing `assess(ApprovedProcessReview)` behaviour and tests must
remain byte-for-byte/behaviourally unchanged.

### 9.2 Successor Phase 5 output

The successor adapter builds standard `AssessmentLineage` using the original
baseline source document and extraction run, but uses a new successor review
ID and approval-event ID. Supplemental M2 evidence appears in the standard
process evidence/traceability with its own document ID and explicit M2
provenance. M2-only request/resolution/policy/instrument links are retained in
the wrapping `M2SuccessorAssessment`, not silently dropped.

Before execution, the adapter verifies the loaded decision-policy fingerprint
equals the pinned baseline fingerprint. Mismatch yields M2 run `STALE` with no
Phase 5 artefact. Assessment failure is stored as a terminal M2 failure record;
it never changes the baseline.

## 10. Safe Phase 6 invocation

`DecisionSupportPackageService.generate` already accepts a validated
`IntegratedAssessmentSuccess` and performs its own integrity/traceability
validation. M2 M1 calls it unchanged with the successor inner result only
after successful Phase 5 persistence.

The service must not be taught about M2 policy or alter package-generation
rules. `M2SuccessorDecisionPackage` wraps the successful standard package with
M2 lineage and is persisted under the M2 run. A Phase 6 failure becomes an M2
terminal failure; no partial successor package is active.

## 11. Baseline-versus-successor comparison

`M2ComparisonService.compare(baseline, successor)` is pure and deterministic.
It accepts only pinned successful baseline/successor references and produces an
immutable `M2BaselineSuccessorComparison`.

Required fields:

- baseline and successor review/assessment/package IDs, revisions and hashes;
- run/request/approval IDs and M2 policy/instrument fingerprints;
- selected original gap and whether it was addressed, retained, rejected or
  blocked;
- old/new `data_readiness` value, knowledge state, rationale, evidence IDs and
  explicit M2 document provenance;
- an assertion that every other criterion/accountability/capability signal is
  unchanged, with a digest of their canonical payloads;
- ordered old/new gate results including statuses, material criteria, rationale
  and evidence IDs;
- old/new recommendation, priority status/score, ROI statement and package
  completeness/gap summary; and
- neutral categories: `NO_FORMAL_CHANGE`, `CRITERION_CHANGE`, `GATE_CHANGE`,
  `RECOMMENDATION_CHANGE`, `UNCERTAINTY_INCREASED`.

The UI wording is: “The recommendation changed after approved additional
evidence under the pinned policy.” It never calls this a successful adoption,
proven ROI, validated prediction or deployment outcome.

## 12. Conflict handling

M2 M1 stores a conflict record at document-evidence review. Allowed statuses
are `CONSISTENT`, `PARTIALLY_OVERLAPPING`, `CONTRADICTORY`, `DIFFERENT_SCOPE`,
`STALE_OR_SUPERSEDED` and `UNRESOLVED`.

A conflict is material in M2 M1 if it changes whether the supporting document
establishes the selected activity’s data availability/control claim, or if the
target step, population, system or period cannot be related to the baseline.

- A material `UNRESOLVED` conflict blocks resolution/request/approval.
- `DIFFERENT_SCOPE` and `PARTIALLY_OVERLAPPING` require an explicit narrower
  scope in the resolution and successor comparison, otherwise block.
- `CONTRADICTORY` requires documented reconciliation by evidence reviewer and
  declared data owner; without it, block.
- `STALE_OR_SUPERSEDED` does not automatically choose the newer source; the
  reviewer must state why it applies to the target period/scope.

No conflict state changes or deletes baseline evidence. M2 M1 does not support
multiple new documents, so reconciliation cannot combine them into a new
aggregate claim.

## 13. Stale-request detection and idempotency

### 13.1 Staleness checks

At run creation, request creation, approval, successor review, assessment,
package generation and comparison, validate:

- baseline active artefact IDs/revisions/hashes and their normal parent chain;
- baseline package ID, selected gap/step and selected criterion snapshot;
- document content hash and unchanged document status;
- evidence-review/resolution/request/approval parent IDs and hashes;
- M2 admissibility-policy and instrument fingerprints;
- baseline decision-policy fingerprint equals the currently loaded policy; and
- expected M2 run stage and no existing active successor for the operation.

Any mismatch writes one immutable M2 terminal `STALE`/`STALE_POLICY` event when
the M2 database is writable, and generates no successor review, assessment,
package or comparison. It never switches to newer records.

### 13.2 Idempotency keys

Every M2 mutation uses a SHA-256 idempotency key over canonical immutable input:

| Operation | Key material |
|---|---|
| Create run | baseline package artefact ID/hash, step ID, gap ID. |
| Submit document | run ID, document SHA-256, filename/declared source. |
| Review evidence | submission ID/hash, locator, decision, reviewer declaration and rationale. |
| Propose resolution | evidence-review ID/hash, value/state, instrument/policy fingerprints, actor declarations and rationale. |
| Request reassessment | resolution ID/hash plus complete pinned baseline/evidence/policy/instrument snapshot. |
| Approve | request ID/hash, approver declaration and rationale. |
| Build successor review | approval ID/hash. |
| Assess successor | successor-review ID/hash plus decision-policy fingerprint. |
| Generate package | successor-assessment ID/hash. |
| Compare | baseline package ID/hash plus successor package ID/hash. |

An exact replay returns the existing artefact. A non-identical attempt at a
completed stage is rejected; it does not overwrite an immutable record.

## 14. Failure and rollback behaviour

Every mutation is transactional within the M2 repository. Where a document
row and artefact, or an artefact and run stage, are created together, both
commit or both roll back. Failed operations are recorded with sanitised error
codes only—never raw document text or customer-provided content.

| Failure | Required behaviour |
|---|---|
| Invalid document or locator | No document/artifact/run-stage mutation. |
| Evidence rejected/insufficient | Persist immutable review and terminal M2 status; baseline unchanged. |
| Invalid resolution or missing approval field | No resolution; prior evidence remains reviewable. |
| Material conflict | Persist conflict/review; block request. |
| Stale baseline/policy/request | Persist M2 stale event when safe; no successor artefact. |
| Successor projection invariant failure | Fail before Phase 5 call; no successor assessment/package. |
| Phase 5 failure | Persist failure wrapper, no Phase 6 call. |
| Phase 6 failure | Persist failure wrapper, no active successor package/comparison. |
| Comparison failure | Preserve successful successor package but mark comparison failure; never reconstruct or alter either package. |
| Frozen target | Refuse before database open/migration/transaction; file bytes unchanged. |

## 15. Exact synthetic integration fixture

M2 M1 tests must build a fresh SQLite workspace through the normal Phase 2–7
baseline path using a deterministic synthetic extraction fixture. No PORT
database, document or artefact is input.

### 15.1 Baseline source and approved state

The fixture has one source-backed activity, such as “Categorise incoming
service requests,” with ordinary original-document evidence for all baseline
facts below. It produces a package-ready baseline where:

| Input | Baseline state/value | Reason |
|---|---|---|
| Activity and step evidence | `KNOWN`, document-supported | Evidence-sufficiency gate passes. |
| `ai_capability_fit` | `KNOWN = 4`, document-supported | Meets technical-fit minimum 3. |
| `categorises_items` capability signal | `KNOWN = true`, document-supported | Maps deterministically to `CLASSIFICATION`. |
| `predictability` | `KNOWN = 3`, document-supported | Does not make conventional-solution fit conditional via workflow automation. |
| `conventional_solution_fit` | `KNOWN = 0`, document-supported | Cannot cause `DO_NOT_RECOMMEND`. |
| `data_readiness` | `UNKNOWN = null`, no evidence | Baseline stops at technical fit with `INVESTIGATE_FURTHER`. |
| `business_value` | `KNOWN = 4`, document-supported | Successor business-value gate can pass. |
| `human_judgement_requirement` | `KNOWN = 3`, document-supported | Successor becomes `AUGMENT`, not a claimed autonomous result. |
| `risk_consequence` | `KNOWN = 2`, document-supported | Risk gate remains evaluable. |
| `residual_risk_with_human_oversight` | `KNOWN = 1`, document-supported | Risk gate remains evaluable. |
| `human_accountability_required` | `KNOWN = true`, document-supported | No M2 change to accountability. |
| `repetition` | `KNOWN = 4`, document-supported | Priority can become complete when eligible. |
| `implementation_complexity` | `KNOWN = 2`, document-supported | Priority can become complete when eligible. |

The supporting M2 document describes the actual target data fields, available
source, access/ownership/control and limitations for the same activity and
period. The M2 reviewer maps it to `data_readiness = 3` using the approved
instrument. Under the unchanged policy, the expected synthetic comparison is:

```text
baseline: technical fit fails because data_readiness is UNKNOWN
successor: technical fit passes with data_readiness = 3
successor: business value passes; risk/autonomy yields AUGMENT
comparison: INVESTIGATE_FURTHER → AUGMENT
```

This expected fixture outcome proves the data-readiness path reaches the
intended gate. It is a test fixture, not a product target or claim that an
`AUGMENT` recommendation is success.

### 15.2 Fixture construction

- Create a new `text/plain` synthetic baseline process source under test
  fixtures.
- Create a deterministic fake extraction provider that returns a candidate with
  exact baseline evidence pointers into that source.
- Run the real ingestion, extraction, Phase 4 review/approval, Phase 5 and
  Phase 6 services to persist the baseline.
- Use a separate literal M2 supporting text document—not a replacement source
  and not part of candidate extraction.
- Submit/review/map/approve it through M2 only, then call successor Phase 5/6.

## 16. Required tests

### 16.1 Unit tests

- Every M2 model rejects extra fields, missing/invalid parent references,
  unsupported evidence classes, invalid stages and mutability attempts.
- Canonical policy/instrument fingerprint is stable; an altered configuration
  changes the fingerprint and makes an existing request stale.
- Instrument anchors allow only 0–4 and `RETAIN_UNKNOWN`; no parser/midpoint or
  automatic score exists.
- UTF-8 document validation, SHA-256 identity, line/character locator and
  exact-excerpt revalidation all fail closed.
- Evidence-review permission combinations reject estimates, M1 sidecars,
  dataset/measured/derived records, missing data-owner declarations and
  material unresolved conflicts.
- Successor projector changes exactly one `data_readiness` input, retains all
  baseline fields/evidence, and adds only the explicit M2 evidence reference.
- Comparison output is deterministic and neutral for unchanged, more
  favourable, less favourable and increased-uncertainty fixtures.
- State-transition, duplicate/replay and cross-run/cross-assessment rejection
  tests cover every M2 operation.

### 16.2 Repository and migration tests

- M2 tables migrate atomically on a fresh normal workspace and do not change
  existing Phase 2–7 table contents/rows.
- Run-local parent/active-pointer validation rejects wrong parent type, wrong
  run, duplicate resolution, second document or second successor package.
- Document-bytes plus document-submission and run-stage updates roll back
  together under a forced database failure.
- Baseline artefact IDs/revisions/payload JSON/SHA, normal active pointers,
  assessment stage and assessment row version are equal before and after every
  M2 write.
- A copy of each frozen PORT-001/002/003/004 database placed under the
  protected path is refused by M2 composition/repository construction and all
  mutation methods before any connection/migration; its file SHA remains equal.

### 16.3 End-to-end integration tests

- Build the exact fresh synthetic baseline in §15 and assert the baseline is
  `INVESTIGATE_FURTHER` because data readiness is unknown.
- Execute the whole approved lifecycle and assert the successor is a separate
  run, changing only data readiness to 3 and producing the expected fixture
  `AUGMENT` result.
- Verify Phase 5 runs only after M2 reassessment approval; Phase 6 runs only
  after a successful successor assessment. Use counting fakes around service
  adapters to prove no direct engine/package bypass.
- Verify Phase 5 and Phase 6 normal service validations still reject malformed
  successor input/result.
- Assert policy mismatch, instrument mismatch, stale baseline hash, stale
  evidence review, altered document bytes, withdrawn document, rejected
  evidence, retained unknown, material conflict and invalid role declarations
  generate no successor formal artefact.
- Verify a package/comparison failure cannot alter the successful baseline or
  prior M2 records.
- Re-run frozen PORT manifests/hashes before and after all M2 synthetic tests.

### 16.4 UI and architectural-boundary tests

- The new page shows the existing baseline package/recommendation and says it
  remains unchanged until explicit reassessment approval.
- It shows at most the one plain-English data-readiness prompt and accepts only
  one `.txt` document; no raw gap table, CSV/data editor, PDF/Office upload or
  M1 answer conversion appears.
- It renders submitted document metadata, exact reviewed excerpt, evidence
  status, conflict/insufficiency reason, declared-role limitation and retained
  baseline status.
- It requires native Streamlit forms for document submission, evidence review,
  resolution and approval; drafts use page-prefixed session keys. No custom
  HTML/unsafe rendering is introduced for document text.
- A static/behavioural architecture test forbids calls from M2 service to
  `reset_to_review`, baseline ingest/extract/review mutation, direct
  `AssessmentEngine`, direct criterion DB update, or baseline active-pointer
  update.
- A boundary test proves all M2 write methods use the frozen-target guard and
  that the normal M1 service still has no decision-affecting path.

## 17. Baseline non-change proofs

M2 M1 acceptance requires proof beyond UI copy:

| Baseline item | Exact proof |
|---|---|
| Approved review | Artifact ID, revision, parent ID, canonical payload JSON and SHA-256 are unchanged and remain active. |
| Integrated assessment | Same identity, parent, JSON/SHA, gate results, recommendation, priority and ROI statement; remains active. |
| Decision Package | Same identity, parent, JSON/SHA, package ID and contents; remains active. |
| Baseline workspace | Same `WorkflowStage.PACKAGE_READY`, normal active-pointer map and `AssessmentRecord` row version. |
| M1 artefacts | If present, same submission/review identity, hash and active status. |
| Frozen evaluation | All manifests/hash listings pass; protected database byte hashes do not change during refused M2 operations. |

The physical SQLite file of a normal development workspace will change because
it receives new M2 tables/rows. That is not a changed baseline. The proof is
that no existing baseline row or active pointer changes and all baseline
artefacts retain identical canonical payloads and hashes.

## 18. File-level implementation plan

### 18.1 Create

| File | Why |
|---|---|
| `config/grw_m2_m1_admissibility_policy.v0.1.json` | Narrow approved M2 M1 document/data-readiness gate-use policy. |
| `config/grw_m2_data_readiness_instrument.v0.1.json` | Versioned 0–4 mapping anchors and explicit value-5 prohibition. |
| `src/ai_adoption_engine/grw/m2/__init__.py` | M2 package boundary separate from frozen M1. |
| `src/ai_adoption_engine/grw/m2/models.py` | Immutable run, evidence, resolution, approval, successor and comparison contracts. |
| `src/ai_adoption_engine/grw/m2/policy.py` | Canonical config loading/fingerprinting and narrow admissibility validation. |
| `src/ai_adoption_engine/grw/m2/instrument.py` | Canonical data-readiness instrument loading and anchor validation. |
| `src/ai_adoption_engine/grw/m2/projection.py` | One-field successor-review/process construction and equality proof. |
| `src/ai_adoption_engine/grw/m2/comparison.py` | Pure deterministic baseline/successor comparator. |
| `src/ai_adoption_engine/grw/m2/service.py` | Guarded M2 lifecycle orchestration. |
| `src/ai_adoption_engine/persistence/reassessment.py` | Dedicated SQLite M2 repository and path guard. |
| `src/ai_adoption_engine/persistence/reassessment_serialization.py` | Canonical M2 artefact serialization/hash validation. |
| `src/ai_adoption_engine/presentation/pages/reassessment.py` | Native Streamlit M2 M1 page only. |
| `tests/fakes/m2_reassessment.py` | Deterministic synthetic baseline/extraction fixture helper. |
| `tests/fixtures/m2_data_readiness_baseline.txt` | Source-backed baseline process fixture. |
| `tests/fixtures/m2_data_readiness_supporting_document.txt` | Separate supporting-document fixture. |
| `tests/unit/test_grw_m2_models.py` | Contract/immutability/state validation tests. |
| `tests/unit/test_grw_m2_policy_instrument.py` | Fingerprint, permission and 0–4 anchor tests. |
| `tests/unit/test_grw_m2_projection_comparison.py` | One-field projection and deterministic comparison tests. |
| `tests/unit/test_grw_m2_service.py` | Operation validation/idempotency/staleness tests. |
| `tests/unit/test_reassessment_persistence.py` | M2 tables, parent-chain, rollback and pointer tests. |
| `tests/integration/test_grw_m2_m1_lifecycle.py` | Full synthetic baseline → successor lifecycle/non-change proof. |
| `tests/architecture/test_grw_m2_boundaries.py` | No baseline mutations/direct engine/reset and frozen-target guard tests. |
| `tests/ui/test_grw_m2.py` | Reassessment page lifecycle and customer-copy tests. |

### 18.2 Modify

| File | Exact change |
|---|---|
| `src/ai_adoption_engine/persistence/sqlite.py` | Add one forward M2 table migration only; do not alter normal artefact/active-pointer behaviour. |
| `src/ai_adoption_engine/application/assessment.py` | Extract shared validated assessment execution and add `assess_successor(M2SuccessorApprovedReview)` with M2-specific validation before the unchanged deterministic engine path. |
| `src/ai_adoption_engine/presentation/context.py` | Add cached, separately constructed read/write M2 service by database path; do not change baseline hydration. |
| `streamlit_app.py` | Register one `Reassessment` page in existing navigation. |
| `tests/ui/test_streamlit_app.py` | Update page-navigation expectation only. |

### 18.3 Explicitly do not modify

- `src/ai_adoption_engine/review/service.py`;
- `src/ai_adoption_engine/review/approval.py`;
- `src/ai_adoption_engine/models/review.py`;
- `src/ai_adoption_engine/workspace/service.py`;
- `src/ai_adoption_engine/workspace/models.py`;
- `src/ai_adoption_engine/decision/gates.py`;
- `src/ai_adoption_engine/decision/engine.py`;
- `src/ai_adoption_engine/decision_support/service.py`;
- `config/decision_policy.v0.2.json`;
- frozen GRW M1 models/service/contracts;
- PORT-001/002/003/004 artefacts, manifests, databases or source captures; and
- AEL, API, authentication/tenancy, measured-data and enterprise infrastructure.

The Phase 6 service remains unmodified because it receives a standard validated
`IntegratedAssessmentSuccess`. The M2 wrapper artefact, not Phase 6, owns the
additional reassessment lineage.

## 19. Implementation order

1. Freeze this plan and confirm the two narrow JSON configurations/anchors.
2. Implement and test pure M2 models, canonical serialization, policy and
   instrument loading—no database or UI.
3. Implement pure document/locator validation, conflict rules, projection and
   comparison tests.
4. Implement the M2 migration/repository and all frozen-target guards; prove
   rollback and baseline isolation before lifecycle code.
5. Refactor Phase 5 into the shared validated execution path; run all existing
   Phase 5/6/Phase 7 regressions before adding M2 orchestration.
6. Implement `M2ReassessmentService` one operation at a time with invalid
   transition/idempotency/stale tests before each next operation.
7. Add the fresh synthetic end-to-end fixture and prove baseline non-change,
   correct technical-fit transition and package/comparison creation.
8. Add the one native Streamlit page and UI tests last.
9. Run targeted M2, Phase 4–7, portfolio boundary and full suites; re-verify
   all frozen portfolio manifests; inspect the complete diff before any freeze
   commit.

## 20. M2 M1 acceptance checklist

- [ ] Only a package-ready baseline with one eligible unknown
  `data_readiness` gap can open M2 M1.
- [ ] The baseline active chain, M1 artefacts and assessment row are unchanged
  after every normal M2 action.
- [ ] M2 has a distinct run root, storage tables, operation records and active
  pointers.
- [ ] Exactly one UTF-8 text document is hash-pinned, locally stored and
  manually located; no external extraction/data ingestion occurs.
- [ ] The only formal candidate evidence class is reviewed document support for
  `data_readiness`/technical fit under the frozen M2 M1 policy fragment.
- [ ] The only supported mapping is a human-reviewed 0–4 data-readiness value
  or retained unknown under the frozen instrument; no score is automatic.
- [ ] Material conflicts, stale references/policy, insufficient evidence,
  missing role declarations and invalid transitions fail closed.
- [ ] Explicit reassessment approval is the only route to successor creation.
- [ ] Successor projection proves that `data_readiness` is the only changed
  formal input and labels supporting evidence as M2 supplemental evidence.
- [ ] Phase 5 uses the shared validated service path and the unchanged decision
  policy; Phase 6 uses the existing generator unchanged.
- [ ] The comparison is immutable, deterministic and neutral about direction of
  recommendation change.
- [ ] Every M2 write path refuses frozen evaluation/portfolio targets before
  any database opening/migration/mutation and leaves copied protected DB bytes
  unchanged.
- [ ] Fresh synthetic tests prove the expected technical-fit transition without
  using a PORT fixture; frozen PORT-001/002/003/004 verification remains valid.
- [ ] No M2 M1 feature is presented as deployment, outcome, ROI proof,
  enterprise role verification or AEL.
