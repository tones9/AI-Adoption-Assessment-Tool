# P2 guided review and approval journey — implementation plan

Status: **PLAN ONLY — implementation requires approval**  
Version: v0.1  
Date: 2026-08-21  
Governing design: `docs/next-product-milestone-p2-design-v0.1.md`

## 1. Purpose, history, and fixed boundary

P2 is a productisation improvement discovered after the original Engine and
the subsequent validation/product work:

```text
Original Engine Decision Package
        ↓ portfolio validation exposed evidence gaps
GRW M1 non-decision evidence lifecycle
        ↓
GRW M2 controlled evidence-backed reassessment
        ↓ fragmented continuation/resumption discovered
DCW P1
        ↓ mandatory Phase 4 review remains the main customer-friction point
P2 guided review and approval journey
```

P2 improves how a customer works through the existing Phase 4 review and
approval boundary. It is not a new decision method, evidence policy, review
domain, reassessment path, or AEL capability.

The implementation boundary is:

```text
Existing candidate extraction
        ↓
Read-only guided projection of the persisted active review
        ↓
Existing Phase 4 review actions, selected explicitly by a human
        ↓
Existing approval preflight and explicit approval
        ↓
Existing Phase 5 assessment and Phase 6 Decision Package
```

P2 must not change extraction semantics, evidence/provenance semantics,
criterion definitions, `UNKNOWN` handling, approval requirements, scoring,
gates, decision policy, recommendation logic, Decision Package semantics, GRW
M1/M2 contracts, DCW contracts, or AEL scope.

## 2. Preimplementation boundary audit

### 2.1 Actual current Phase 4 journey

| Current transition | Authoritative state/action | Persisted result | Approval relevance |
| --- | --- | --- | --- |
| Candidate extraction → start review | `AssessmentWorkspaceService.start_review()` calls `ProcessReviewService.start_review()` | Active `REVIEW_SESSION`, parented to the active candidate extraction | Required prerequisite |
| Review action | Existing `ProcessReviewService` action mutates an in-memory working copy; `AssessmentWorkspaceService.save_review()` persists it | Same active review artefact is updated; `ReviewEvent`s preserve its action audit | Depends on field/action |
| Document-supported group confirmation | Existing UI calls `accept_assertion()` once per selected candidate assertion | Individual accepted events, preserving each assertion's existing citation | Only process name and retained activities can clear approval blockers |
| Correct/resolve/reject/retain | Existing review service validates the permitted provenance and records an event | Current review state plus immutable event | A retained process name/activity must be accepted or corrected; other unknowns normally do not block |
| Dependency/conflict/order action | Existing review service corrects/rejects dependency, resolves conflict, reorders, or accepts order | Current review state plus event | Invalid retained dependency, open blocking conflict, and unaccepted order block |
| Explicit approval | `AssessmentWorkspaceService.approve()` calls `approve_review()` | Immutable `APPROVED_REVIEW`, parented to active `REVIEW_SESSION`; workspace stage `APPROVED` | Final required human act |
| Assessment eligibility | Existing Results page invokes assessment only after `APPROVED_REVIEW` exists | Existing Phase 5 artefact only | Outside P2 |

### 2.2 What actually blocks approval

The single authoritative implementation is `review.approval._approval_errors()`
via `approve_review()`. With an explicit approval statement supplied, it
requires:

1. the process name to be retained and accepted or corrected;
2. at least one retained step;
3. explicit acceptance of the retained-step order;
4. every retained step activity to be retained and accepted or corrected;
5. every retained dependency to target another retained step; and
6. every blocking structural conflict to be resolved.

`approve_review()` also performs the existing Phase 1 projection; any resulting
projection error is an approval blocker. The P2 queue must show it using the
existing `invalid-phase1-projection` error, not invent a repair rule.

The following are not approval requirements unless one of the preceding real
rules makes them material:

- optional process description/objective;
- optional collections such as actors, systems, inputs, outputs, exceptions,
  and operational characteristics;
- criteria, accountability assertions, and capability signals;
- model-inferred values; and
- legitimate unknown values.

An `UNKNOWN` process name or retained-step activity cannot be retained as a way
to complete approval: it will remain an actual approval error. Other unknowns
can be deliberately retained with the existing review action and must remain
visibly unknown.

### 2.3 Existing state P2 may project

P2 may read only the existing active `ProcessReviewSession`, its
`original_candidate`, review assertions/collections/dependencies/conflicts,
immutable `ReviewEvent`s, and the side-effect-free projections already in
`presentation.review_progress`:

- `approval_errors(session)`;
- `build_review_progress(session)`;
- `iter_process_assertions(session)`;
- `iter_step_assertions(session, step_id)`;
- `document_supported_unreviewed(targets)`;
- `inferred_unreviewed(session)`; and
- `unknown_unreviewed_by_step(session)`.

`APPROVED_REVIEW` is already the immutable record after approval and the
normal workspace active-chain validation already governs assessment/package
eligibility. No P2 artefact, pointer, table, or operation record is needed.

### 2.4 State that must never become authoritative

Streamlit session state may remember only a selected work item, selected step,
or expanded section. It must never establish:

- whether review is ready for approval;
- the active review identity or candidate identity;
- an assertion's value, provenance, knowledge state, or disposition;
- a dependency target or conflict resolution;
- whether the review is approved; or
- eligibility for assessment, package generation, GRW, DCW, or M2.

Every render reloads the active workspace. A stale selected item is discarded
when it no longer exists; the default focus is recomputed from the persisted
authoritative queue.

## 3. Guided review read model

### 3.1 New pure projection

Create a presentation-only `ReviewJourneyView` in
`src/ai_adoption_engine/presentation/review_journey.py`. It is a frozen
dataclass/read model plus a builder such as `build_review_journey(session)`.
It accepts a persisted `ProcessReviewSession`, calls the existing
`approval_errors()`/`build_review_progress()` functions, and returns no mutable
domain model or callable mutation.

The view must contain only presentation facts already derived from the session:

```text
ReviewJourneyView
  candidate summary and extraction warning
  ReviewProgress + exact ApprovalError/OutstandingReviewItem sequence
  required work items in deterministic preflight order
  grouped document-supported unreviewed targets
  explicit unknown items by step
  inferred/unreviewed recommended items
  invalid retained dependencies
  open blocking conflicts
  event-derived approval summary
  default focus item ID
```

`ReviewJourneyView` is not a second review state and cannot store an action,
choose an approval result, resolve an assertion, or call an Engine/GRW/M2
service. Its definition must make this apparent in imports and tests.

### 3.2 Deterministic required-work queue

Use the already ordered `ReviewProgress.outstanding` tuple as the queue source.
P2 may attach rendering metadata by `ApprovalError.code` / `field_path`, but
must not remove, reorder, add, or mark an item complete independently.

The default-focus rule is:

1. retain a currently selected work item only if its `item_id` remains in the
   new persisted outstanding tuple;
2. otherwise select the first outstanding item; and
3. if none remain, show the ready-for-approval summary.

This makes browser/session loss harmless while avoiding a new persisted
bookmark.

### 3.3 Guided sections

| Customer section | Existing state feeding it | Customer action | Existing mutation boundary | Completion / approval effect |
| --- | --- | --- | --- | --- |
| **Review summary** | Candidate identity, extraction issues, `ReviewProgress` | Open the next required item or another activity | None | Read-only; no effect |
| **Needs your decision** | `ReviewProgress.outstanding`, resolved field references | Use existing accept/correct/reject/resolve/retain, step removal/order, dependency, or conflict controls appropriate to the true field | `ProcessReviewService` then `AssessmentWorkspaceService.save_review()` | Complete only when the real next `approval_errors()` result no longer contains it |
| **What the document says** | Existing document-supported unreviewed assertion targets and their existing resolved locators/snippets | Use existing scoped confirmation or inspect and use the ordinary review action | Same existing review/save path | Acknowledges each selected assertion independently; only required fields can change readiness |
| **Unknown or not provided** | Existing UNKNOWN assertions and dispositions, grouped by activity | Retain unknown or use an existing, explicit review action when legitimate evidence/information exists | Same existing review/save path | Informational unless a real approval error cites it; never auto-resolved |
| **Dependencies and structural issues** | Invalid retained dependencies and open blocking conflicts from existing session/preflight | Existing dependency correction/rejection or conflict resolution, with required rationale | Same existing review/save path | Blocking only when the real preflight returns the corresponding error |
| **Recommended checks** | `inferred_unreviewed()` and non-blocking fields | Existing review actions, optionally | Same existing review/save path | Never labelled required unless the real preflight returns a blocker |
| **Review more detail** | All remaining process/step assertion editors and collections | Existing actions only | Same existing review/save path | Must remain accessible; it cannot be silently suppressed |
| **Ready for approval** | Existing session, events, conflicts, `approval_errors()` | Existing explicit approval checkbox/button and optional rationale | `AssessmentWorkspaceService.approve()` | Available only when the authoritative preflight is ready |

The existing detailed editor helpers may be retained and called from the
reorganised page rather than reimplementing assertion logic. P2 should favour
moving existing render helpers behind guided sections over creating a second
set of forms.

## 4. Approval experience

The final P2 section is a read-only **Approval summary** immediately before the
existing explicit approval form. It must show, in plain language:

1. the original candidate process name and candidate activity list;
2. the current reviewed process name and retained ordered activity list;
3. material review events, grouped as corrections, rejections/removals,
   added human-supplied entries, dependency/order changes, and conflict
   resolutions;
4. directly documented versus human-supplied versus inferred versus unknown
   status, without equating them;
5. retained unknown values, including the statement that they may remain
   unknown when they are not approval requirements;
6. all actual current approval blockers returned by `approval_errors()`; and
7. the exact Phase 4 approval statement: approval accepts the current-state
   process representation, not an AI deployment, ROI, complete evidence set,
   legal/security sign-off, or recommendation.

The summary is audit-oriented presentation. It must not edit the review,
convert an event into evidence, or calculate a quality/confidence score.

The existing checkbox labelled `APPROVE CURRENT-STATE PROCESS`, optional
rationale, and `AssessmentWorkspaceService.approve()` remain the only approval
mechanism. P2 must not create a "quick approve", automatic approval after the
last queue item, or an approval derived from a progress percentage.

After an immutable `APPROVED_REVIEW` exists, render the approved process as
read-only and provide a registered navigation action to the existing Assessment
Results page. Do not put `reset_to_review` in the normal P2 progression.

## 5. Frozen evaluation/portfolio protection

### 5.1 Narrow guard contract

P2 adds a fail-closed guard for exactly these existing Phase 4 write entry
points in `AssessmentWorkspaceService`:

- `start_review`;
- `save_review`;
- `approve`; and
- `reset_to_review`.

The guard runs as the first statement of each method, before `load_workspace`,
`begin_operation`, a repository transaction, or any mutation. It receives only
the configured repository database path and applies the established rule:

```text
path resolves under a directory containing both `evaluation` and `portfolio`
        → refuse
otherwise
        → allow ordinary local behaviour
```

The exception must be explicit and customer-safe, for example
`Phase4FrozenWorkspaceError("Phase 4 review writes are refused for frozen evaluation portfolio workspaces")`.
The UI may suppress controls after the same pure path check, but UI suppression
is not the safety boundary.

### 5.2 Smallest consistent implementation

Create a small generic path helper in
`src/ai_adoption_engine/persistence/workspace_protection.py`:

- `is_frozen_evaluation_portfolio_path(path) -> bool`;
- a neutral `FrozenEvaluationWorkspaceError`; and
- `assert_phase4_write_target_allowed(path)`.

`workspace.service` uses the Phase 4 helper. `persistence.reassessment` may
reuse the predicate internally while preserving its current
`M2FrozenWorkspaceError` public behaviour; this is a non-functional
consolidation only. GRW M1's existing error contract remains unchanged.

This is deliberately not a whole-Engine guard. Phase 2/3/5/6 operations and
repository construction remain outside P2. The P2 guarantee is precise:
attempting any of the four Phase 4 write methods on a protected path is refused
without an operation, artefact, pointer, stage, or database-byte change.

Existing general application hydration uses the legacy SQLite repository,
which performs an idempotent schema check on construction. P2 must not claim
that it creates a new repository-wide read-only access mode. A strict
"never open a protected SQLite database" requirement would require a broader
read-only persistence design and is explicitly deferred. The Phase 4 action
guard itself needs no database access to determine refusal.

### 5.3 UI behaviour for protected paths

The Source and Review pages use the same pure predicate to hide/disable
Phase 4 lifecycle controls and display a concise immutable-evaluation notice.
The Review page must check this before attempting to start, save, approve, or
reset. It may show only a safely hydrated read-only view where the existing app
can load one. The existing DCW protected-baseline behaviour remains unchanged.

## 6. Persistence, resumption, and recovery

No new persistence model is needed.

- `REVIEW_SESSION` remains the single active mutable working record. Its
  existing parent remains the active candidate extraction. Its event list is
  the action audit.
- `APPROVED_REVIEW` remains the immutable approval artefact, parented to that
  active review session.
- Current review edits retain existing behaviour: the same active review
  artefact/revision is replaced under `replace_current_review=True`; P2 must
  neither create another mutable review nor rewrite its original candidate.
- Reload, Streamlit restart, or reopening the assessment hydrates the existing
  workspace and current review session. The queue and default focus are rebuilt
  from the review/preflight; only an optional selected item is lost.
- An invalid/stale selected item is discarded rather than applied. The user sees
  the persisted current queue. `save_review` continues to refuse a session that
  is not the active review ID.
- A failed validation/action produces no success state; P2 refreshes the
  workspace and presents recovery guidance. It does not retry a mutation
  automatically.
- An approved review renders read-only. Source replacement and the already
  existing explicit reset semantics remain the only ways to make an ordinary
  active chain non-current; P2 does not add an alternate reopening path.

## 7. Error and recovery copy

P2 changes presentation wording, not the underlying rule.

| Condition | Customer-facing guidance | Underlying rule preserved |
| --- | --- | --- |
| Review not started | “Start validation after candidate extraction is complete.” | `start_review` still requires active candidate extraction |
| No candidate / extraction failed | “Return to Source & Extraction and complete a usable candidate process first.” | No review session is fabricated |
| Stale/non-current session | “This saved review is no longer the active candidate review. Refresh and continue with the current process version.” | `save_review` continues to require active review ID |
| Invalid correction | “This change was not saved. Provide the required value, rationale, and—when you cite the document—an existing source reference.” | Existing review-service validation still decides admissibility |
| Missing/invalid document citation | “A document-backed correction needs a citation from this reviewed source document.” | Existing source-document ownership check remains authoritative |
| Open dependency | “Choose another retained activity as the dependency target, or remove this dependency.” | Existing retained-dependency preflight rule |
| Open structural conflict | “Resolve the identified structure issue before approval.” | Existing conflict state and `resolve_conflict()` |
| Approval blocked | “Complete the listed process-validation items before approval.” | Exact `approval_errors()` list, not UI logic |
| Already approved | “This current-state process is already approved. Continue to assessment.” | No duplicate `APPROVED_REVIEW` |
| Reset is required | Keep the existing explicit warning that it makes active approval/assessment/package non-current; do not present it as recovery for ordinary navigation. | Existing reset semantics unchanged |
| Protected evaluation workspace | “Review changes are unavailable because this is a frozen evaluation record.” | Service-level fail-closed refusal before mutation |

Raw exception-class names and trace details must not be shown as normal
customer-facing errors. Tests may still assert the typed service exception.

## 8. Customer terminology

| Current/internal term | P2 customer label | Meaning retained |
| --- | --- | --- |
| Candidate / unconfirmed process extraction | **Candidate process — needs validation** | It is not approved or factual merely because it was extracted |
| Process Review | **Validate process** | Phase 4 human review remains the same workflow |
| Approval preflight | **Approval readiness** | Exact `approval_errors()` remains the authority |
| Document-supported | **Directly documented** | Existing resolved source evidence remains required |
| Model-inferred | **Suggested by the extraction — review recommended** | It is not directly documented |
| Human-supplied | **Added by the reviewer — no document evidence claimed** | It does not silently acquire document provenance |
| Knowledge state `UNKNOWN` | **Unknown / not provided** | It remains explicitly unknown, not zero or false |
| Retain unknown | **Keep as unknown** | No inference or fact is created |
| Structural conflict | **Process structure issue** | Existing blocking conflict remains blocking |
| Dependency correction | **Set the dependent activity** | Existing target validity rule remains unchanged |
| Approved review | **Approved current-state process** | It does not recommend AI, deployment, ROI, or a successor |

Technical source locators, field paths, IDs, and detailed provenance remain
available in an expandable **Technical traceability** section. They must not be
removed or converted into customer claims.

## 9. Exact implementation plan

### 9.1 Files to create

| File | Purpose |
| --- | --- |
| `src/ai_adoption_engine/presentation/review_journey.py` | Pure immutable/read-only guided-review projection and event-derived approval-summary view; no service mutation imports. |
| `src/ai_adoption_engine/persistence/workspace_protection.py` | Pure protected-path predicate and Phase 4 fail-closed exception/helper; performs no database access. |
| `tests/unit/test_review_journey.py` | Projection ordering, categorisation, summary, default focus, no-mutation, and real-preflight alignment tests. |
| `tests/integration/test_p2_guided_review_equivalence.py` | Old direct Phase 4 path versus P2 guided path semantic/downstream equivalence using a fresh deterministic workspace. |
| `tests/integration/test_p2_phase4_frozen_workspace.py` | Direct adversarial refusal tests for all four Phase 4 write methods plus fresh-workspace control. |
| `tests/architecture/test_p2_guided_review_boundaries.py` | Proves no new decision authority, persistence entity, assessment/package/GRW/M2 write, or session-derived approval rule. |
| `tests/ui/test_p2_guided_review.py` | Guided page language, queue, provenance/unknown sections, resumption, approval summary, protection notice, and navigation. |

### 9.2 Files to modify

| File | Change and reason |
| --- | --- |
| `src/ai_adoption_engine/presentation/pages/review.py` | Reorganise existing helpers around `ReviewJourneyView`; retain all existing service calls/forms, add approval summary and recovery wording, and remove raw customer exception-class presentation. |
| `src/ai_adoption_engine/presentation/pages/source.py` | Present the existing start-review handoff as **Validate process** and suppress the start action on a protected path; service guard remains authoritative. |
| `src/ai_adoption_engine/presentation/context.py` | Add pure Phase 4 write-availability helper and registered navigation to Assessment Results; clear P2 page-local selection state on assessment change. |
| `src/ai_adoption_engine/workspace/service.py` | Call the Phase 4 path guard as the first statement of `start_review`, `save_review`, `approve`, and `reset_to_review`; do not alter any downstream logic. |
| `src/ai_adoption_engine/persistence/reassessment.py` | Optionally reuse the new pure protected-path predicate while retaining `M2FrozenWorkspaceError` and all M2 behaviour exactly. Omit this change if it cannot be made as a semantics-preserving refactor. |
| `streamlit_app.py` | Rename the sidebar title to **Validate process** while retaining the `review` route and normal navigation order. |
| `tests/ui/test_streamlit_app.py` | Update only expectations affected by customer-facing naming/navigation; retain existing end-to-end Phase 1–7 coverage. |
| `tests/unit/test_phase7_review_progress.py` | Add/retain assertions that P2 relies on exact Phase 4 requirements rather than a percentage/readiness approximation. |
| `tests/architecture/test_phase4_boundaries.py` | Extend boundary assertions for P2 projection/import direction and unchanged Phase 4 decision separation. |

### 9.3 Files explicitly not to modify

- `docs/gap-resolution-workspace-design-v0.1.md` and frozen GRW M1/M2
  governing documents;
- GRW M1/M2 services, models, policy/instrument configuration, and their
  contracts, except the optional neutral protected-path helper consolidation
  described above;
- Phase 1–3 extraction, prompts, schemas, taxonomy, and ingestion behaviour;
- Phase 5 assessment/decision engine and Phase 6 package-generation services;
- decision policy, gates, scoring, criterion definitions, and evidence models;
- DCW application/service contracts and M2 successor lineage/persistence;
- migrations, artifact schema registrations, workspace artifact types, and
  operation kinds;
- all `evaluation/portfolio` / PORT artefacts and manifests;
- `AI_Adoption_Engine_MASTER_BIBLE_v1.0.docx`, `....`, `.agents/`, `.claude/`,
  `AGENTS.md`, and `docs/observations/9a-0c/scratch/`.

## 10. Implementation order

1. Add the pure protected-path helper and direct Phase 4 service guards, with
   adversarial tests before touching presentation code.
2. Add the pure `ReviewJourneyView` projection and unit-test it against the
   real `approval_errors()` / `build_review_progress()` output.
3. Reorganise `review.py` to render the guided sections while preserving the
   existing assertion/dependency/conflict action helpers and service calls.
4. Update Source, navigation, protected-path UI suppression, and approved
   review hand-off to Assessment Results.
5. Add UI/resumption/recovery coverage and the direct-versus-guided equivalence
   integration test.
6. Run Phase 4–7, GRW M1/M2, DCW, frozen portfolio, and full-suite regressions;
   then conduct an adversarial pre-freeze audit before any commit.

## 11. Test and equivalence strategy

### 11.1 Unit tests

- `ReviewJourneyView` produces its required queue from the actual
  `approval_errors()` result and exactly preserves error order/field paths.
- No non-blocking unknown, inferred assertion, or optional descriptive field is
  promoted into a blocker by the projection.
- Unknown process name/retained activity remains visible as a real blocker.
- Document-supported, inferred, human-supplied, rejected, and unknown states
  retain their exact provenance labels.
- Dependency and conflict items appear only according to the active session
  and real preflight.
- Approval summary event counts/listings are deterministic, traceable to the
  stored events, and do not mutate the supplied session.
- Default focus survives a valid selection and otherwise chooses the first
  current outstanding item.

### 11.2 Service/protection integration tests

- For each guarded method (`start_review`, `save_review`, `approve`,
  `reset_to_review`), provide a protected-path repository double whose methods
  fail if called; assert the typed refusal occurs first and a sentinel database
  file hash is unchanged.
- Copy a known frozen package/review workspace to a temporary path under
  `evaluation/portfolio`, attempt each guarded action, and assert no artefact,
  active pointer, stage, operation, or bytes change.
- A fresh ordinary workspace completes start → save → approve normally.
- Existing source replacement/reset behaviour remains unchanged outside the
  protected path.

### 11.3 Old-path versus guided-path equivalence

Use two fresh synthetic workspaces created from the same scripted demo
candidate, deterministic repository IDs/clocks, and the same explicit human
decisions:

1. **Old path:** invoke the current authoritative review service actions and
   workspace save/approve methods directly.
2. **Guided path:** invoke the same existing action helpers through the P2
   guided UI/harness, with no P2 mutation service.

Compare canonical approved-review semantics: original candidate identity,
retained process/step content and order, assertion values, knowledge states,
origins, evidence IDs/locators, dispositions, conflicts, and review-event
action/rationale sequence. Use fixed approval time and deterministic IDs, or
normalise only generated IDs/timestamps, never semantic fields.

Run the unchanged Phase 5 and Phase 6 services on both approved reviews and
compare canonical deterministic assessment and Decision Package semantics:
recommendations, gate results, criteria/provenance, priority/ROI status,
package portfolio/future-state/roadmap/governance/missing-information content,
and policy fingerprints. No P2 special case is permitted.

### 11.4 UI tests

- Candidate warning and plain-language summary appear before actions.
- The first real blocker opens by default; valid user step selection is a
  convenience only.
- Group confirmation shows existing source locators/snippets and preserves one
  event per assertion.
- Unknown, inferred, human-supplied, and document-supported content are
  distinguishable; no automatic correction or unknown resolution occurs.
- Invalid correction/missing citation produces recovery copy and no saved
  change.
- Dependency/conflict queue states are visible; approval remains disabled until
  the actual final resolution.
- Approval summary accurately presents changes/unknowns and does not claim AI
  recommendation, ROI, deployment, or complete evidence.
- Closing/restarting the AppTest session restores persisted review state and
  deterministic next required action.
- Protected targets display the refusal notice and expose no Phase 4 write
  controls. Ordinary targets still expose permitted controls.
- Approved review renders read-only and can navigate to Assessment Results.

### 11.5 Boundary/regression tests

- Static architecture test: the new projection/page imports no decision engine,
  assessment/package service, GRW M1/M2 lifecycle service, direct SQLite
  mutation, migration, or policy/scoring modules.
- Static/runtime test: page actions use only existing review/workspace write
  boundaries; session state cannot determine readiness/approval.
- Existing Phase 4 approval and review-service tests remain green unchanged in
  meaning.
- Existing Phase 5–7, GRW M1, GRW M2, DCW, persistence, navigation, and
  portfolio-boundary tests remain green.
- Re-run all PORT-001/002/003/004 and cross-case hash-manifest verification;
  every frozen file remains byte-identical.

## 12. Non-change proofs

The implementation is acceptable only if tests demonstrate:

- opening, selecting, expanding, or refreshing P2 changes no review assertion,
  event, artefact, active pointer, workspace stage, assessment, package, M1,
  M2, or DCW state;
- a review mutation changes state only through a pre-existing authorised
  `ProcessReviewService` action and `AssessmentWorkspaceService.save_review()`;
- approved review semantics, Phase 5 assessment semantics, and Phase 6 package
  semantics are equivalent for the same human decisions through old and guided
  paths;
- no new Phase 4 data model, migration, entity, active pointer, or operation
  exists;
- a protected write is refused before repository access/mutation from the four
  service methods, with byte/hash non-change; and
- normal non-protected local review remains functional.

## 13. Preimplementation safety verdict

**Verdict: no unresolved implementation blocker.**

The current repository can support P2 as a presentation/projection milestone
without changing Phase 4–6 methodology or persistence. The following are
non-negotiable implementation constraints, not new product decisions:

1. `approval_errors()`/`approve_review()` is the sole readiness and approval
   authority; P2 never derives readiness from counts, statuses, or session
   state.
2. The guided page may reorganise existing controls but cannot create a generic
   action dispatcher that accepts arbitrary field paths/values without the
   existing review-service validation.
3. The existing document-evidence selector proves source-document ownership,
   not semantic relevance. P2 must not claim a stronger validation than the
   current service supplies.
4. P2 must not present `retain_unknown` as approval-completing for required
   process identity/activity fields.
5. The Phase 4 protected-path guard must be direct and service-level, covering
   all four named methods. UI hiding alone fails the boundary.
6. The narrow guard does not create a whole-application read-only SQLite mode;
   that broader persistence change remains deferred and must not be smuggled
   into P2.

## 14. Acceptance checklist

- [ ] No new review persistence, migration, artefact, active pointer, evidence
      type, criterion, policy, score, gate, or recommendation logic.
- [ ] Guided queue exactly matches real Phase 4 preflight and always reloads
      persisted state.
- [ ] Every existing detailed review assertion remains accessible.
- [ ] Provenance and `UNKNOWN` distinctions remain explicit and unaltered.
- [ ] Existing review service and workspace service remain all review/approval
      write boundaries.
- [ ] Explicit approval remains the existing final human action.
- [ ] Approved view is read-only with existing results hand-off; no casual reset.
- [ ] Four Phase 4 writes fail closed for protected paths before mutation.
- [ ] Protected-path and ordinary-workspace controls have targeted test proof.
- [ ] Old-path/guided-path approved-review, assessment, and package semantics
      are equivalent for identical human decisions.
- [ ] GRW M1/M2 and DCW regression suites pass unchanged in meaning.
- [ ] Frozen portfolio/cross-case hashes remain valid and byte-identical.
- [ ] Full test suite, compile check, and diff check pass before freeze.

No implementation, migration, policy/schema change, evaluation change, GRW
expansion, AEL work, staging, or commit is authorised by this plan.
