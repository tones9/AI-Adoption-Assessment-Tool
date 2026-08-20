# GRW M1 implementation plan

Status: **IMPLEMENTATION PLAN ONLY — NOT APPROVED, NOT IMPLEMENTED**  
Version: v0.1  
Date: 2026-08-20  
Depends on: the GRW workspace, evidence-contract and evidence-admissibility
design documents.  
Scope: the smallest non-decision evidence lifecycle. This plan changes no code,
database, policy, schema, prompt, taxonomy, migration, frozen evaluation
artefact or portfolio summary.

> **M1 status note.** The evidence-admissibility policy design is the later,
> controlling design authority for M1. It intentionally narrows earlier GRW
> design language that anticipates a successor reassessment: M1 records and
> reviews preliminary context only, with no decision-affecting reassessment.

## 1. M1 outcome and boundary

M1 proves that a customer can voluntarily strengthen the explanation around an
existing Decision Package without weakening evidence discipline.

It must:

- capture one optional DECISION_STRENGTHENING question;
- accept a natural-language estimate or range;
- retain the exact answer and an explicit provenance label;
- submit it for human review;
- persist the review decision as PRELIMINARY_UNDERSTANDING or RECORDED_ONLY;
- link it to the original Phase 6 InformationGap; and
- visibly prove that the baseline criterion, gates, recommendation and Decision
  Package did not change.

M1 is not a reassessment. It must not create a successor review, assessment,
Decision Package, priority score, ROI result, or recommendation. Its comparison
is a non-change evidence-strengthening view, not a Phase 5/6 product rerun.

## 2. Architecture findings that constrain M1

The current repository already has a suitable local persistence pattern:

- Phase 7 uses one SQLite database with generic assessment_artifacts,
  active_artifacts and assessment_operations tables.
- Artifact payloads are serialized and hash-validated by artifact type.
- Existing approved-review, integrated-assessment and Decision-Package payloads
  are append-only; only the in-progress Phase 4 review snapshot is replaceable.
- The active Decision Package has an exact parent link to the active integrated
  assessment, and WorkspaceSnapshot validates that chain.
- The current workflow stage can remain PACKAGE_READY while a sidecar artefact
  is added. Its assessment-record updated timestamp/row version may advance,
  but no baseline artefact or active baseline pointer may change.
- The generic SQLite schema stores artifact_type as text. Adding new typed
  artefacts needs application serialization and chain validation, but does not
  require a SQL migration.

The M1 design should use this existing mechanism. A new GRW table, new
repository, or full workspace domain would be more scope than necessary.

## 3. Exact customer workflow

### 3.1 Entry and initial reassurance

From a completed Decision Package, the customer sees a small optional Gap
Resolution page in the existing Streamlit navigation. The opening message is:

> Your current information is enough for an initial assessment.
>
> We identified additional information that could strengthen this decision. You
> may answer this question now or continue with the current recommendation.

The page also displays the baseline package ID, baseline recommendation and a
plain statement: “Nothing you enter here changes the current assessment.”

Two actions are visible:

- Continue with current recommendation — no write and no required action.
- Strengthen one point — opens the single M1 question.

No list of all package gaps is shown. There is no bulk questionnaire, upload
control, CSV control, progress percentage or requirement to complete anything.

### 3.2 Answer and submission

The customer sees one bordered native Streamlit form containing:

- a short activity label;
- why the answer could help;
- one question;
- help text saying that an estimate or range is acceptable;
- a text area for the answer;
- an explicit “I do not know” path; and
- one Submit answer button.

For an ordinary answer, the form says that it will be recorded as an estimate
unless supporting evidence is separately supplied in a future release. The
customer can edit the unsubmitted draft. On submission, the exact response is
immutable. The UI cannot offer Edit or Delete; a future attempt is a new
evidence item and is outside M1.

### 3.3 Review

The submitted item appears in a simple Review evidence section. The reviewer
sees:

- the original InformationGap and customer-facing question;
- the exact customer answer;
- an optional non-authoritative parsed candidate;
- provenance: OPERATOR_PROVIDED_ESTIMATE;
- a warning that it is not measured or document-supported; and
- three actions: Accept as preliminary understanding, Accept as recorded only,
  or Reject.

The local M1 product has no authentication or role separation. The reviewer
must type a reviewer label and rationale. If the customer and reviewer are the
same person, the UI displays that this is self-review rather than implying
independent validation.

### 3.4 Result

After review, the page displays:

- Accepted as preliminary understanding, recorded only, or rejected;
- the linked original InformationGap;
- the evidence class and the exact answer;
- a concise explanation of the policy effect; and
- a non-change panel:

~~~text
Formal assessment effect
Criterion: unchanged
Assessment gates: unchanged
Recommendation: unchanged
Decision Package: unchanged
~~~

For accepted preliminary understanding, the page may say: “This estimate gives
useful context about workload. It is not evidence for a formal criterion or
gate. Verified operational information would be needed before considering a
decision-affecting use.”

## 4. First M1 example

PORT-004 may be used as a read-only reference only. It must never be opened by
the M1 product or modified by an M1 test.

The frozen PORT-004 packaged workspace contains this suitable reference:

| Item | Read-only value |
|---|---|
| Baseline package artefact | artifact-7d8a9331af1449fea8c5ea905ace1a3b, revision 1, SHA-256 4c717926f4fd21bd1cecfbd6516553d63be3470e383de2a1a28388a136938862 |
| Step | candidate-step-8761540c3fb724d5 — “identifying the field of search” |
| Internal gap | candidate-step-8761540c3fb724d5:criterion:repetition |
| Gap field | repetition |
| Frozen state | unknown; the resulting recommendation is INVESTIGATE_FURTHER |

This reference shows why repetition is the appropriate M1 pattern: it may make
workload context more intelligible, but it is not the early gate-material
ai_capability_fit input that stops the frozen assessment. No new fact about
USPTO activity is asserted below.

The live M1 implementation and tests should use a fresh synthetic offline
workspace, not this frozen workspace. The illustrative interaction is:

| M1 element | Value |
|---|---|
| Customer-facing question | “About how often is this search activity performed in a typical month? A rough range is okay.” |
| Illustrative answer | “Usually around 20–35 searches per month, depending on the examiner’s docket.” |
| Stored evidence class | OPERATOR_PROVIDED_ESTIMATE |
| Parsed candidate, if recognised | lower 20, upper 35, unit searches, period month, qualifiers usually and around, status CANDIDATE_NEEDS_REVIEW |
| Human action | Accept as PRELIMINARY_UNDERSTANDING, with a rationale that the answer is unverified workload context. |
| Formal effect | No criterion assertion is created. repetition remains null/unknown; all gate results and INVESTIGATE_FURTHER remain exactly as in the baseline. |

The example is a pattern, not an instruction to collect information from, or
about, the frozen PORT-004 case.

## 5. Minimal domain model

Create a small GRW package separate from the Phase 1–6 domain models. M1 must
not add fields to InformationGap, CriterionInput, EvidenceReference,
ReviewedAssertion, IntegratedAssessmentSuccess or DecisionPackageSuccess.

| Concept | Persistence | Minimum purpose |
|---|---|---|
| GrwAnswerDraft | Streamlit session state only | Mutable, unsubmitted text and the selected pinned baseline/gap identity. It is discarded on session loss and never an assessment input. |
| GrwBaselineReference | Embedded in submitted artefact | assessment ID; exact Decision-Package artifact ID, revision, payload hash and package ID; exact integrated-assessment artifact ID, revision and payload hash. |
| GrwGapReference | Embedded in submitted artefact | Snapshot of the selected original InformationGap, portfolio step/activity label and the baseline package identity that contains it. |
| GrwQuestion | Embedded in submitted artefact | Fixed M1 question ID/version, customer wording, help text and category DECISION_STRENGTHENING. It is generated deterministically from the eligible repetition gap, not by an LLM. |
| GrwParsedEstimateCandidate | Optional embedded submission field | Parser version, parse status, recognised lower/upper bounds, unit, period, qualifiers and ambiguity notes. It is a candidate only, never a fact or score. |
| GrwEvidenceSubmission | New immutable artefact | Submitted answer, evidence class OPERATOR_PROVIDED_ESTIMATE or explicit UNKNOWN outcome, baseline/gap/question references, optional parse candidate and submission time. |
| GrwEvidenceReview | New immutable artefact | Exact parent submission reference/hash, reviewer label, rationale, accept/reject outcome and admissibility effect PRELIMINARY_UNDERSTANDING or RECORDED_ONLY. It includes an explicit assessment_effect NONE. |

Minimum enums are:

- GrwEvidenceClass: OPERATOR_PROVIDED_ESTIMATE and UNKNOWN.
- GrwSubmissionStatus: SUBMITTED.
- GrwReviewDecision: ACCEPT_PRELIMINARY, ACCEPT_RECORDED_ONLY, REJECT.
- GrwAdmissibilityEffect: PRELIMINARY_UNDERSTANDING, RECORDED_ONLY, NONE.
- GrwParseStatus: CANDIDATE_NEEDS_REVIEW, AMBIGUOUS, NOT_PARSED.

Do not add the full future evidence-class catalogue, ResolutionAssertion,
EvidenceAdmissibilityPolicy, ReassessmentRequest, successor review, or
reassessment comparison in M1. The M1 review record is deliberately not a
criterion assertion.

### 5.1 Exact-answer and parsing rule

The submission must retain the original answer as the source of truth:

~~~text
answer_text:
  "Usually around 18,000–22,000 tickets per month."

parsed_candidate:
  parse_status: CANDIDATE_NEEDS_REVIEW
  lower_bound: 18000
  upper_bound: 22000
  unit: tickets
  period: month
  qualifiers: [usually, around]
  parser_version: grw-m1-range-parser-v0.1
  criterion_value: absent
  midpoint: absent
~~~

The parser is deterministic and deliberately narrow. It may recognise a simple
number/range plus an explicitly written unit and period. It must retain all
qualifiers, produce AMBIGUOUS or NOT_PARSED when it cannot safely recognise the
input, and never infer a midpoint, confidence, criterion band, evidence ID for
the baseline process, or recommendation.

The answer remains valid when parsing fails. A reviewer can accept it as
context, record only, or reject it. No parser result is ever passed to Phase 4,
Phase 5, Phase 6, gates, scoring or ROI.

## 6. Eligibility and priority rule

M1 supports exactly one deterministic question type:

1. Start with the active successful Decision Package.
2. Inspect its portfolio items and missing-information records.
3. Select an UNKNOWN_INPUT gap whose field is repetition.
4. Bind it to its own package item/step.
5. Classify it as DECISION_STRENGTHENING for this M1 question catalogue.

If no such gap is present, the page displays “No optional M1 question is
available for this package” and performs no write.

This is intentionally narrower than a general prioritisation engine. Phase 6
does not itself store customer-facing priority categories, and a case that ends
at INVESTIGATE_FURTHER can have material_to_priority false because priority
scoring never becomes eligible. M1 must not reinterpret that flag as a complete
priority policy. It uses the non-gate repetition gap only because it is a safe,
pre-registered DECISION_STRENGTHENING pattern.

## 7. Persistence plan

Use the existing SQLite assessment_artifacts mechanism. No new table,
repository, database migration or change to Phase 1–6 payload schemas is
necessary.

Add two artefact types:

| Artefact type | Parent | Schema version | Mutability |
|---|---|---|---|
| GRW_EVIDENCE_SUBMISSION | Exact active DECISION_PACKAGE_RESULT artefact | grw-m1-v0.1 | Immutable |
| GRW_EVIDENCE_REVIEW | Exact GRW_EVIDENCE_SUBMISSION artefact | grw-m1-v0.1 | Immutable |

The generic table already stores typed JSON payload, SHA-256, parent artifact
and revision. The repository should add parent-type validation and active-chain
validation for these two types. It must retain PACKAGE_READY and must not
deactivate or replace the active approved review, integrated assessment or
Decision Package.

A submission should embed both baseline package and baseline assessment hashes,
rather than relying on an active pointer at display time. The service must
reject a submission if the pinned package is no longer the active package. This
prevents answers being attached to a superseded baseline.

Unsubmitted drafts remain only in page-prefixed Streamlit session state. This is
the smallest honest working-state mechanism. They are not durable and are not
auditable. After submit, all auditable state is an immutable artefact.

M1 may use the existing idempotent operation mechanism with two new manual
operation kinds, GRW_SUBMIT and GRW_REVIEW. Their keys should bind the baseline
package artifact ID, gap ID and submitted/reviewed content hash. This prevents
double-click or rerun duplication without making the answer mutable.

## 8. Application and service operations

Add a small GRW M1 service, exposed through AssessmentWorkspaceService. It must
use repository validation rather than UI conditions as the security boundary.

| Operation | Required validation | Result |
|---|---|---|
| open_m1_context(assessment_id) | Active successful Decision Package and its parent assessment; one eligible repetition gap. | Read-only context with pinned baseline reference and one M1 question, or no-question state. |
| create_answer_draft | Valid active context and non-empty customer text or explicit unknown choice. | Session-only draft; no repository write. |
| submit_estimate(assessment_id, context, answer_text) | Exact active package identity; selected gap belongs to the package; answer length/content validation; no existing M1 submission for the same package/gap. | Immutable GRW_EVIDENCE_SUBMISSION with OPERATOR_PROVIDED_ESTIMATE, or explicit UNKNOWN outcome. |
| review_submission(assessment_id, submission_id, decision, reviewer_label, rationale) | Submission ownership, integrity, correct parent baseline, valid one-time transition and non-empty review metadata. | Immutable GRW_EVIDENCE_REVIEW with assessment_effect NONE. |
| load_m1_status(assessment_id) | Valid workspace and GRW chain. | Read-only lifecycle status and non-change comparison fields for rendering. |

There is no assess, generate_package, reset_to_review, criterion mapping,
approval-for-reassessment, or policy-loading operation in M1. The service must
not import AssessmentEngine, IntegratedAssessmentService, DecisionSupportPackageService
or Phase 4 review mutation operations.

## 9. Smallest Streamlit addition

Add one new Gap resolution page to the existing st.navigation list. Do not
refactor the current application into a different page structure in M1.

Use native Streamlit elements only:

- title and explanatory text;
- one bordered container for the optional question;
- st.form for the answer and submit action, avoiding repeated writes on every
  keystroke;
- stable page-prefixed session-state keys for the draft;
- an explicit unknown button or checkbox path;
- a second bordered Review evidence container only after submission; and
- a read-only result container showing the non-change proof.

Use sentence-case labels and an appropriate Material icon. Do not add custom
HTML, CSS, AI-generated question text, hidden technical gap lists, files
uploads, data editors or tabs that eagerly evaluate unrelated work.

The page must load the current package first, then render a fast contextual
message. All database writes occur only from submit/review form actions. The
existing app already uses function-based page renderers; M1 should follow that
local pattern rather than refactor unrelated pages.

## 10. Required non-change proof

M1 acceptance is not merely “the UI says unchanged.” The service and tests must
prove all four conditions after submission and review:

| Baseline item | Required proof |
|---|---|
| Baseline criterion | The selected baseline criterion has identical value, knowledge state, rationale, evidence IDs and confidence before and after M1. For the M1 gap it remains null/unknown. |
| Baseline assessment | The active INTEGRATED_ASSESSMENT_RESULT has the same artifact ID, revision, parent, payload SHA-256 and canonical payload JSON. Its gate results and recommendation are identical. |
| Baseline Decision Package | The active DECISION_PACKAGE_RESULT has the same artifact ID, revision, parent, payload SHA-256 and canonical payload JSON. |
| Recommendation and gates | The selected portfolio item recommendation mode and every gate result are deep-equal before/after. No AssessmentEngine call or package-generation call occurs. |

Adding GRW active artefacts may increment the enclosing AssessmentRecord row
version and updated timestamp; that is expected local-workspace metadata. Its
workflow stage stays PACKAGE_READY. It is not a changed formal assessment.

The review payload should contain a compact non-change snapshot: baseline
artefact references/hashes, selected criterion state, selected recommendation
and gate-result digest. The UI renders this stored proof and may additionally
read the current baseline for display. It must fail closed if either baseline
hash differs.

## 11. Tests

### 11.1 Unit tests

- Domain validation: immutable submitted/reviewed payloads; required exact
  baseline/gap references; permitted M1 evidence classes; review decision to
  admissibility-effect mapping; no criterion-value field; answer-length and
  empty-answer failures.
- Parser: preserve raw text; recognise the canonical range only as
  CANDIDATE_NEEDS_REVIEW; preserve qualifiers; never create midpoint, ordinal
  score or confidence; return AMBIGUOUS/NOT_PARSED without rejecting valid text.
- Service eligibility: select only an UNKNOWN repetition gap from the active
  package; return no-question state for any other package.
- Invalid transitions: review nonexistent/cross-assessment submission; review
  twice; submit against stale package; select a gap not present in the pinned
  package; use unsupported evidence class; attempt to associate a submission
  with a frozen/evaluation package path.

### 11.2 Integration tests

Use a fresh temporary offline workspace that has generated a real package through
the existing pipeline.

- Submit “Usually around 18,000–22,000 tickets per month.”
- Reopen the SQLite database and validate submission/review payload hashes,
  schema versions, exact parent IDs and nested baseline hashes.
- Review as PRELIMINARY_UNDERSTANDING and separately as RECORDED_ONLY.
- Assert that review persists the exact original answer and provenance.
- Take pre-M1 snapshots of the selected criterion, integrated assessment,
  Decision Package, gate results and recommendation. Assert deep equality and
  matching hashes after each lifecycle action.
- Use counting assessment/package services to prove that submission/review make
  zero calls to assess or generate_package.
- Assert only GRW submission/review revisions increase; approved review,
  integrated assessment and Decision Package revision counts do not increase.
- Assert invalid and duplicate actions roll back transactionally.

### 11.3 UI and architecture tests

- A Streamlit app test verifies the Gap resolution page is in navigation, shows
  the initial reassurance, shows at most one M1 question, preserves the text
  field across ordinary reruns, and exposes no upload/CSV control.
- A review UI test verifies that the answer is displayed verbatim, provenance is
  OPERATOR_PROVIDED_ESTIMATE, and a reviewer action yields the stored
  non-change panel.
- A boundary test statically and behaviourally proves the M1 service does not
  call or import Phase 4 mutation, Phase 5 assessment, Phase 6 generation,
  AssessmentEngine or policy mutation paths.
- A frozen-isolation test records hashes for the PORT-001, PORT-002, PORT-003
  and PORT-004 frozen manifests before and after an M1 run against a temporary
  database and asserts exact equality. PORT-003 remains historical and is not
  an M1 input.

## 12. Security and privacy safeguards

M1 is a local single-user workspace, not enterprise productisation. The minimum
safeguards are:

- accept typed text only; no documents, files, CSVs or data exports;
- do not send answers to an extraction provider, LLM, analytics service or
  external endpoint;
- do not log raw answer text in exceptions, operation error codes or UI
  diagnostics;
- enforce a server-side maximum text length and validate all submission fields;
- rely on the repository's local SQLite file permissions, content hash and
  integrity validation;
- render user text through normal escaped Streamlit text elements, never custom
  unsafe HTML;
- display a concise notice not to enter secrets, credentials or unnecessary
  personal data; and
- use parameterized existing SQLite operations only.

Enterprise authentication, authorisation, tenancy, encryption/key management,
fine-grained retention, deletion workflow, audit export, data classification,
DLP, legal hold and cross-user reviewer separation are explicitly deferred.

## 13. File-level implementation plan

### Files to create

| File | Why |
|---|---|
| src/ai_adoption_engine/grw/__init__.py | Marks the narrow GRW package boundary. |
| src/ai_adoption_engine/grw/models.py | Holds only M1 draft/context, submission, review, provenance, parse-candidate and non-change-proof contracts. |
| src/ai_adoption_engine/grw/service.py | Implements eligibility, baseline pinning, submission, review, invalid-transition and non-change-proof rules without importing assessment execution. |
| src/ai_adoption_engine/presentation/pages/gap_resolution.py | Renders the one-question optional form, review controls and read-only non-change result. |
| tests/unit/test_grw_models.py | Validates domain states, provenance and exact-answer preservation. |
| tests/unit/test_grw_service.py | Validates selection, transitions, stale baseline rejection and no assessment-input effects. |
| tests/integration/test_grw_m1_lifecycle.py | Proves the complete fresh-workspace lifecycle and immutable baseline artefacts. |
| tests/ui/test_grw_m1.py | Tests the single Streamlit question, review action and non-change display. |
| tests/architecture/test_grw_m1_boundaries.py | Guards no Phase 4–6 mutation and frozen portfolio isolation. |

### Files to modify

| File | Why |
|---|---|
| src/ai_adoption_engine/workspace/models.py | Add two GRW artefact types, immutable classification and the two manual operation kinds. Do not add a workflow stage. |
| src/ai_adoption_engine/persistence/serialization.py | Register GRW submission/review adapters and the grw-m1-v0.1 schema version. |
| src/ai_adoption_engine/persistence/sqlite.py | Add exact parent-type and active-chain validation for the two sidecar artefacts; preserve PACKAGE_READY and baseline active artefacts. No migration is needed. |
| src/ai_adoption_engine/workspace/service.py | Expose guarded GRW M1 operations through the existing application/workspace service. |
| streamlit_app.py | Add the one Gap resolution navigation entry. |
| tests/ui/test_streamlit_app.py | Update navigation coverage for the added page. |
| tests/unit/test_phase7_persistence.py | Extend existing revision/parent integrity coverage for the two new generic artefact types if shared helper coverage is preferable. |

### Files deliberately not modified

- config/decision_policy.v0.2.json and all policy code;
- Phase 1 decision engine, gates and scoring;
- Phase 4 review models/service/approval;
- Phase 5 assessment models/service;
- Phase 6 Decision-Package models/service;
- persistence/migrations.py;
- any PORT artefact, manifest, hash file or portfolio summary;
- existing GRW design documents;
- AEL materials and all production APIs.

## 14. Explicitly deferred work

M1 must not implement:

- decision-affecting reassessment or successor assessments;
- new gate-admissibility rules or policy versions;
- criterion instruments or 0–5 mappings;
- structured attestation;
- document evidence attachment through GRW;
- measured-data ingestion, CSV upload or CSV analysis;
- data-quality profiling;
- ROI, business-case or savings calculation;
- multi-gap prioritisation or an all-gap workspace;
- AEL, initiative management, pilots, deployment, outcomes or learning loops;
- API endpoints;
- multi-user workflow, enterprise authentication, tenancy or authorisation;
- enterprise privacy/security controls beyond the local safeguards above.

## 15. M1 acceptance checklist

M1 is complete only when all of the following are true.

- [ ] A package-ready local workspace presents the reassurance message and one
  optional DECISION_STRENGTHENING repetition question.
- [ ] The customer can continue without answering and retain the current
  recommendation.
- [ ] A range estimate and an explicit unknown can be submitted without an
  upload.
- [ ] The original answer is retained exactly, including range language and
  qualifiers.
- [ ] Any parsed candidate is marked non-authoritative and contains no
  midpoint, criterion score, confidence or recommendation.
- [ ] The stored submission records OPERATOR_PROVIDED_ESTIMATE or UNKNOWN and
  exact baseline package/assessment plus original gap references.
- [ ] A reviewer can accept as PRELIMINARY_UNDERSTANDING or RECORDED_ONLY, or
  reject, with a recorded label and rationale.
- [ ] The review states assessment_effect NONE and the UI makes that limitation
  clear.
- [ ] Baseline criterion, integrated assessment, Decision Package, gate results
  and recommendation are byte/deep-equal before and after M1.
- [ ] No assessment or package-generation service call occurs.
- [ ] The baseline approved-review, assessment and package revisions remain
  unchanged; only immutable GRW artefacts are added.
- [ ] Invalid, stale, duplicate and cross-assessment actions fail safely.
- [ ] Frozen PORT-001, PORT-002, PORT-003 and PORT-004 artefacts remain
  hash-identical.
- [ ] No policy, gate, taxonomy, Phase 4–6 contract, migration, API, AEL or
  enterprise feature is introduced.

## 16. Implementation risks to guard against

| Risk | Required guard |
|---|---|
| Estimate accidentally changes an assessment input | M1 models contain no criterion value or assertion target; architecture tests prohibit Phase 4–6 mutation/imports. |
| New evidence looks document-backed or measured | Fixed M1 provenance is OPERATOR_PROVIDED_ESTIMATE; UI and review record state its limitations. |
| Parsed range creates false precision | Retain raw text/qualifiers; no midpoint or score fields; parser test and review warning. |
| Active package is silently replaced or detached | Pin exact package and assessment artefact IDs/hashes; validate parent links and reject stale baseline at submit/review. |
| GRW reopens or invalidates the normal workflow | Keep PACKAGE_READY, never deactivate existing active artefacts and never call reset_to_review. |
| Double click creates multiple submissions/reviews | Use operation idempotency keys and one allowed submission/review transition per package-gap in M1. |
| UI exposes a large technical backlog | Eligibility selects at most one pre-registered repetition gap. |
| Raw operational text leaks | No external provider calls or unsafe rendering; server-side validation; minimal local privacy notice. |
| Frozen evaluation becomes an input or is modified | Tests run only against fresh temp databases and verify frozen-manifest hashes before/after. |

No implementation should begin until this plan receives explicit approval.
