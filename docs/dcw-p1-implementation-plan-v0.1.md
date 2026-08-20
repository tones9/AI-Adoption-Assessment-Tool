# Decision Continuation Workspace (DCW) P1 — implementation plan

Status: **PLAN ONLY — implementation requires approval**  
Version: v0.1  
Date: 2026-08-20  
Governing proposal: `docs/next-product-milestone-design-v0.1.md`

## 1. Purpose and fixed boundary

P1 productises the already frozen Decision Package, GRW M1, and GRW M2 M1
capabilities into one package-centred, local Streamlit journey. It resolves a
discoverability and safe-resumption problem; it does not create another
assessment method, evidence type, workflow authority, or persistence domain.

The implementation is limited to this journey:

```text
active package-ready baseline
        ↓
read-only Decision Continuation Workspace
        ├── continue with existing baseline recommendation (no write)
        ├── open existing M1 page (optional, non-decision route)
        └── start or resume existing M2 M1 route
                ↓
          existing M1/M2 services perform every write and guard
                ↓
read-only DCW status / existing neutral M2 comparison
```

DCW is a Phase 7 presentation/read-model milestone. It must not change Phase
4 review, Phase 5 assessment, Phase 6 package generation, the decision policy,
the M1/M2 admissibility contracts, or the baseline workspace's active chain.

## 2. Audit constraints incorporated into P1

The repository audit found no unresolved design blocker. The following are
non-negotiable implementation constraints rather than new design decisions.

1. **Protected evaluation paths cannot use M2 read discovery.**
   `SQLiteReassessmentRepository` and the M2 composition root correctly call
   `assert_m2_write_target_allowed()` before opening or migrating SQLite. P1
   must not introduce a read-only constructor or direct SQLite query that
   bypasses that guard. For a path protected as an `evaluation/portfolio`
   workspace, DCW may show the ordinary loaded package as an immutable record,
   but it must show GRW continuation as unavailable and must not construct an
   M2 repository, load an M2 run, start a run, or invoke a migration.

2. **A SQL row match alone is not sufficient run identity.**
   Each listed M2 run must match the selected active baseline on all three
   stored roots—`assessment_id`, Decision Package artifact ID, and Decision
   Package payload SHA-256—and its hash-validated `RUN_MANIFEST` must carry the
   same `M2BaselineReference.decision_package`. A corrupt, incomplete, or
   inconsistent row/manifest is not a resumable run.

3. **A multi-activity package has no DCW-wide “best next gap.”**
   DCW may show the existing deterministic M1 question and existing deterministic
   M2 M1 eligible step only. It must identify that activity and gap precisely,
   not invent a portfolio ranking or imply that a presented route is globally
   highest priority.

4. **M2 persisted state is authoritative; Streamlit state is not.**
   Session state may store a selected `run_id` and return destination only. On
   every render and before any existing M2 action, the Reassessment page must
   reload the run and prove the exact active-baseline relationship. Refreshing
   or opening a new browser session therefore loses only convenience state.

5. **Existing repository construction performs schema initialisation.**
   `SQLiteReassessmentRepository` currently delegates to the ordinary SQLite
   repository constructor, which performs the project’s idempotent migration
   check. DCW must therefore build its M2 read collaborators only after the
   normal local workspace is already initialised, and P1’s no-write proof uses
   an already initialised workspace. P1 adds no migration and no alternate
   read-only constructor. A protected evaluation/portfolio path must fail the
   target check before either repository constructor is reached.

## 3. Exact customer workflow

### 3.1 Preconditions and entry

1. The user has opened a local assessment with an active
   `DECISION_PACKAGE_RESULT` in its normal workspace chain.
2. The user opens **Decision continuation** from the sidebar or the Decision
   Package page.
3. DCW loads the current workspace snapshot and packages it into a read-only
   view. It does not generate a package, create an M1 submission, create an M2
   run, change an active pointer, or write an operation record.

If no package is active, DCW shows a guarded state: *“Generate a Decision
Package before continuing.”* It offers no GRW route.

### 3.2 Baseline-first screen

DCW leads with:

> **Current formal decision**  
> This Decision Package is your active baseline. You can continue with its
> recommendation now. Optional evidence paths do not replace it automatically.

It shows the baseline package ID, package artifact ID/revision/SHA-256,
assessment ID, policy ID/version/fingerprint, package completeness, and the
existing portfolio recommendations by activity. The customer-facing default is
plain language; technical identities reside in an expanded traceability panel.

Selecting **Continue with current recommendation** is informational only. It
does not record acceptance, create an AEL initiative, or write anything.

### 3.3 Optional M1 route

Where the existing `open_m1_context()` reports an eligible question, DCW shows
one card labelled **Improve preliminary understanding — no formal decision
change**. It contains the existing activity, customer-facing question, and
current M1 status only. The card opens the existing **Gap resolution** page;
the existing M1 service remains responsible for submission, review, rejection,
and immutable M1 records.

When M1 is not eligible, DCW shows no substitute question and no raw gap list.

### 3.4 Optional M2 route and persisted resumption

Where the existing `open_m2_m1_context()` reports an eligible M2 M1 target,
DCW shows one card labelled **Controlled formal reassessment**. It identifies
the activity and `data_readiness` limitation, and says that a reviewed text
document, reviewed criterion resolution, and explicit approval are all still
required. It does not accept a document or perform any reviewer action itself.

For the current exact baseline, DCW lists persisted runs in a compact table:

| Customer-facing field | Source |
|---|---|
| Separate reassessment run ID | `reassessment_runs.run_id` |
| Activity and limited field | validated `RUN_MANIFEST` step/gap reference |
| Current stage | `reassessment_runs.stage` |
| Created / last updated | persisted run timestamps |
| Baseline package identity | validated baseline reference |
| Available result | existing successor package/comparison only where present |

The customer chooses **Start controlled reassessment** only on the existing
M2 page. DCW may navigate there with the active baseline selected; it must not
call `create_run()` itself. A selected listed run uses **Resume**. The
Reassessment page reloads and validates that run before rendering its existing
stage-specific controls.

Terminal (`EVIDENCE_REJECTED`, `INSUFFICIENT`, `BLOCKED_CONFLICT`, `STALE`,
`WITHDRAWN`, `FAILED`) and completed (`COMPARED`) runs are inspectable in DCW
only. They cannot be resumed into a write state or overwritten. Only a
non-terminal run may be handed to the existing Reassessment page, after that
page has proved the selected run has the exact active baseline and matching
current M2 context. A `PACKAGE_READY` run with no persisted comparison must
show the package result and clearly say that the comparison is not available;
it must not invent one.

### 3.5 Return and successor display

On return from either GRW page, DCW reloads persisted state. It shows M1’s
existing status with its non-decision copy. It shows M2 successor and comparison
content only from M2’s immutable artifacts, labels it **separate successor**,
and always repeats that the normal active baseline remains the current formal
Decision Package.

An M2 successor recommendation is descriptive only. DCW must never label a
recommendation movement as success, adoption approval, outcome, ROI, or
deployment readiness.

## 4. Navigation and page structure

Add one native Streamlit page:

```text
Assessments
Source & Extraction
Process Review
Assessment Results
Decision Package
Decision continuation          ← new P1 page
Gap resolution                 ← existing GRW M1 lifecycle page
Reassessment                   ← existing GRW M2 lifecycle page
```

- Add a **Continue decision** entry point on the package-ready Decision Package
  page. It only navigates to DCW.
- DCW links to existing standalone M1/M2 pages. Keeping those lifecycle pages
  avoids duplicating their forms, human review, and service guards.
- Use only these page-local session keys: `dcw_selected_m2_run_id` and
  `dcw_return_page`. They may be mirrored to the existing
  `grw_m2_run_id` immediately before navigating to the Reassessment page for
  backwards compatibility, but the M2 page must treat both as untrusted hints.
- `clear_workspace_state()` and `select_assessment()` must clear the DCW keys.
  Reassessment must clear an invalid/foreign selection rather than retaining
  it for a different assessment.
- Both existing GRW pages must provide a return link/action to DCW without
  changing an M1 record or M2 run. The M2 page receives only a non-terminal
  selected run whose manifest, roots, current active package and current M2
  context all match. Terminal/completed records remain inspectable from DCW.
  Native `st.switch_page` (or the installed equivalent) is sufficient; no
  custom routing framework is required.

## 5. Read model and service contract

### 5.1 In-memory view models

Create immutable, non-persisted dataclasses (or equivalent frozen models) in a
new application-level module. They are presentation DTOs, not artifact types:

```text
DecisionContinuationBaseline
  assessment_id
  package artifact reference (ID, revision, payload SHA-256)
  package ID, completeness, policy identity/fingerprint
  approved-review and assessment artifact references
  portfolio recommendation summaries (step ID, activity, mode, rationale)

M2RunSummary
  run_id, stage, created_at, updated_at
  exact baseline package artifact reference
  manifest-derived activity, step ID, gap ID, field name
  optional successor package reference
  optional comparison reference

DecisionContinuationView
  baseline
  optional existing M1 context/status
  optional existing M2 eligibility context
  exact-baseline M2 run summaries
  protected-workspace availability state and safe display message
```

`DecisionContinuationService` receives existing read-capable collaborators: the
ordinary `AssessmentWorkspaceService`, its M1 read methods, and (only for a
non-protected path) the existing M2 service/repository. It may call:

- workspace snapshot/read functions;
- `load_grw_m1_status()` / `open_m1_context()`;
- `open_m2_m1_context()`; and
- the new repository `list_runs_for_baseline()` query.

It must not call any method named `submit`, `review`, `propose`, `request`,
`approve`, `execute`, `assess`, `generate`, `create_run`, `begin_operation`,
or any direct SQLite mutation API. It must not import or instantiate Phase 5 or
Phase 6 services.

### 5.2 Active package selection

The selected baseline is always the current normal workspace active
`DECISION_PACKAGE_RESULT`, plus the active `APPROVED_REVIEW` and
`INTEGRATED_ASSESSMENT_RESULT` from the same validated workspace snapshot.
DCW uses the persisted artifact references—not a package ID alone—to bind its
view.

If the normal workspace snapshot has no complete package-ready chain, the read
model returns an unavailable state rather than a partial fabricated baseline.

### 5.3 Exact-baseline M2 discovery

Add this read-only repository operation:

```python
list_runs_for_baseline(
    assessment_id: str,
    package_artifact_id: str,
    package_payload_sha256: str,
) -> tuple[M2RunSummary, ...]
```

Its implementation must:

1. query `reassessment_runs` with an exact equality predicate over all three
   supplied root values, with deterministic ordering (`updated_at` descending,
   then `run_id` ascending);
2. call existing chain validation for every candidate;
3. load the immutable `RUN_MANIFEST` and verify that its baseline assessment,
   `decision_package` artifact ID/revision/SHA, and package ID equal the
   selected active baseline;
4. derive activity, step ID, gap ID and field only from the validated manifest;
5. derive successor/comparison availability only from active M2 artifacts in
   that same run; and
6. return no raw supporting-document bytes, document text, M1 answer, or
   unreviewed evidence content.

A mismatch, missing manifest, failed payload hash/schema validation, wrong
parent chain, or foreign artifact is a persistence-integrity error. The DCW
service must show a safe unavailable/corrupt-run message and offer no action
for that row. It must never repair, delete, or re-parent it. Runs from another
baseline remain absent from the active-baseline list; historic cross-baseline
search is explicit non-scope.

No table, migration, artifact schema, active-pointer table, or persisted DCW
entity is necessary. This is a read query over M2’s existing dedicated tables.

## 6. Baseline and successor presentation rules

1. The normal workspace baseline is always labelled **Active formal baseline**.
   Its artifact ID, package ID, and policy reference are visibly distinct from
   any M2 run.
2. A successor is always labelled **Separate M2 successor for run `<id>`**.
   It is never called a replacement, current package, promotion, deployment
   decision, or outcome.
3. DCW only displays a successor package if its M2 artifact is present in the
   exact listed run and its existing artifact hash validates.
4. DCW only displays a baseline–successor comparison if the exact listed run
   contains the existing immutable comparison artifact. It renders the existing
   neutral fields; it computes neither a new score nor a summary verdict.
5. Old runs tied to a different package artifact/SHA are not shown against a
   new active baseline. The page should state that only runs for this exact
   baseline are shown, rather than implying history was deleted.
6. A completed, stale, rejected, conflict-blocked, withdrawn, or failed run is
   an audit record. Inspection is allowed; new evidence or retry must follow
   existing M2 semantics, not a DCW shortcut.

## 7. M1 and M2 action boundaries

| DCW action or display | Allowed effect | Authoritative existing boundary |
|---|---|---|
| Open/refresh DCW | Pure read/render | workspace/M1/M2 read repositories |
| Continue with baseline | No write | none |
| Open M1 | Navigation only | existing `Gap resolution` page + M1 service |
| M1 answer/review | Existing M1 sidecar lifecycle only | existing M1 service |
| Open M2 start screen | Navigation and baseline hint only | existing `Reassessment` page |
| Create M2 run | Existing atomic run/manifest creation only | existing `M2ReassessmentService.create_run()` |
| Resume M2 run | Revalidate then render existing stage | existing M2 service/repository |
| Evidence review, resolution, approval, successor execution | Existing explicit M2 steps only | existing M2 service and Phase 5/6 adapter |
| Show comparison | Read immutable recorded comparison | existing M2 persistence/model |

DCW must contain no duplicate review forms, policy choice, conflict selection,
criterion mapping, or assessment/package action. In particular, a customer
cannot cause `DOCUMENT_SUPPORTED`, `data_readiness`, a gate, or a recommendation
to change by pressing a DCW control.

## 8. Empty, error, stale, and protected states

| State | Required DCW behaviour |
|---|---|
| No selected workspace | Direct the user to open an assessment; no package/GRW data. |
| Workspace integrity load failure | Reuse existing safe load-error state; no partial content or actions. |
| Package not ready | Explain package prerequisite; no M1/M2 route. |
| No M1 eligible question | Omit M1 card; do not expose raw gaps. |
| No M2 eligibility and no matching persisted M2 run | Explain no controlled M2 route is currently available; do not create one. |
| Existing exact-baseline run but current eligibility has become stale | Show the persisted run stage/read-only status; do not start or advance it. |
| Invalid/session-selected/foreign run | Clear selection, show unavailable, and do not call an action method. |
| Invalid manifest/chain/artifact | Show a sanitised integrity error and no row action; do not repair it. |
| M2 terminal state | Read-only inspection only, including a neutral reason. |
| M2 `PACKAGE_READY` without comparison | Show successor availability only; do not infer comparison. |
| Protected evaluation/portfolio path | Show baseline as immutable only if ordinary workspace loading already succeeds. Show M1/M2 continuation unavailable. Do not create an M2 repository/service, issue M2 discovery reads, open/migrate/write the M2 database, or set a run selection. |

For a protected target, the page uses the existing pure
`assert_m2_write_target_allowed(path)` check before attempting any M2
composition. `M2FrozenWorkspaceError` is an expected protected state, not an
error that invites a workaround. The implementation must not add a bypassing
read-only M2 repository constructor.

## 9. Persistence and composition changes

### 9.1 Persistence

Modify only `SQLiteReassessmentRepository` to add the exact-baseline read
listing method and its validated summary materialisation. Once the existing
repository has been constructed for an already initialised normal workspace,
the listing uses the existing `_read()` context and no `_transaction()` path.
It must not alter a row, update `updated_at`, update `row_version`, or add an
operation record while listing. P1 must not change the constructor’s existing
idempotent migration check or use it against a protected target.

No migration is permitted or required: the existing tables already contain the
three baseline roots, run stage/timestamps, artifact chain, and separate active
M2 pointer namespace.

### 9.2 Composition

Add a small `build_decision_continuation_service()` composition helper for
ordinary local workspaces, injecting existing workspace and M2 collaborators.
It must run the current target-protection check before building the M2
collaborators. The Streamlit context module exposes a cached helper only for
allowed targets; the DCW page detects a protected target before invoking it.

This keeps the current M2 constructor’s fail-closed boundary intact. It must
not modify `build_m2_reassessment_service()` to support a read mode.

### 9.3 Session state

Add `dcw_selected_m2_run_id` and `dcw_return_page` as non-authoritative
presentation keys. Add them to `clear_workspace_state()`. The M2 page reads a
DCW selection only as a candidate and proves it matches the active baseline
before using it. No session key is persisted to SQLite or used as a lineage
parent.

## 10. UX implementation details

Use the existing Streamlit patterns: native headings, `st.container`,
`st.expander`, `st.info`, status text, buttons/forms, and `st.switch_page` (or
the installed native equivalent). Do not add custom HTML/CSS, client-side
storage, JavaScript state, a new component library, or a new dashboard.

The new page layout is:

```text
Decision continuation
  Current formal decision [baseline summary]
    Continue with current recommendation
    Technical traceability (collapsed)
  Optional next actions
    Improve preliminary understanding (M1 status/card, when available)
    Controlled formal reassessment (M2 eligibility/card, when available)
  Separate reassessment records
    compact exact-baseline run list
    selected run status, successor identity and existing comparison
```

Use direct, non-promissory copy:

- “Optional information may help a future formal reassessment if it is reviewed
  and admissible under the approved policy.”
- “This baseline Decision Package remains active.”
- “A successor is separate from the baseline; a changed recommendation is not a
  measured outcome or deployment approval.”

Do not show raw `InformationGap` lists. Internal IDs/hashes are available only
in the traceability expander. Do not collect a customer answer/document on DCW;
the existing lifecycle pages own those forms.

## 11. Files to create

| File | Why it is needed |
|---|---|
| `src/ai_adoption_engine/application/decision_continuation.py` | Frozen in-memory DTOs and the read-only composition service; keeps DCW logic out of Streamlit and out of assessment/GRW write services. |
| `src/ai_adoption_engine/presentation/pages/decision_continuation.py` | New native Streamlit DCW page, copy, safe route hand-off, status and comparison rendering. |
| `tests/unit/test_decision_continuation.py` | Tests view construction, exact baseline values, summary redaction, and zero-write read model behaviour. |
| `tests/integration/test_dcw_p1.py` | Fresh SQLite package-ready fixtures exercising exact-baseline discovery, new-session resumption and baseline non-change. |
| `tests/architecture/test_dcw_p1_boundaries.py` | Static/runtime boundary tests showing DCW has no Phase 4–6 or M1/M2 mutation path. |
| `tests/ui/test_dcw_p1.py` | AppTest coverage for baseline-first UI, cards, navigation/resume, terminal/stale/error/protected states and copy. |

## 12. Files to modify

| File | Required narrow change |
|---|---|
| `src/ai_adoption_engine/persistence/reassessment.py` | Add the read-only `list_runs_for_baseline()` query and manifest-backed summary validation. No write semantics change. |
| `src/ai_adoption_engine/workspace/composition.py` | Compose the DCW read service for allowed local targets only; retain existing M2 target guard. |
| `src/ai_adoption_engine/presentation/context.py` | Add safe DCW service accessor/target availability helper and clear DCW convenience session keys with workspace changes. |
| `src/ai_adoption_engine/presentation/pages/decision_package.py` | Add navigation-only entry to DCW after a successful package exists. |
| `src/ai_adoption_engine/presentation/pages/gap_resolution.py` | Add return navigation to DCW only; preserve all existing M1 forms, copy and service calls. |
| `src/ai_adoption_engine/presentation/pages/reassessment.py` | Revalidate and consume only an eligible non-terminal DCW-selected persisted run; leave terminal/completed inspection in DCW and add return navigation. Preserve all existing M2 forms/service calls and state guards. |
| `streamlit_app.py` | Register the new Decision continuation page in native navigation. |
| `tests/unit/test_reassessment_persistence.py` | Add exact-baseline read query, manifest mismatch/corruption and no-write assertions. |
| `tests/ui/test_streamlit_app.py` | Update expected navigation and add the new page smoke test. |

Do not modify migration files, M1/M2 governing designs, M2 policy/instrument
files, Phase 4–6 services/models, decision taxonomy, evaluation/portfolio
artefacts, frozen PORT artefacts, or GRW M1/M2 implementation behaviour.

## 13. Tests required

All new persistence/integration/UI tests use fresh synthetic local workspaces.
No test may create a run or write into a frozen evaluation database.

### 13.1 Unit and persistence tests

- A package-ready snapshot produces an immutable view with the exact active
  package/review/assessment references and portfolio recommendation summaries.
- Rendering/building the view performs no write: baseline SQLite bytes/normal
  active pointers/assessment stage/operation counts are unchanged.
- `list_runs_for_baseline()` returns only runs matching all three exact roots.
  Same assessment/different package, same package ID/different artifact SHA,
  and foreign assessment runs are excluded.
- A run with a missing manifest, failed payload hash/schema validation, wrong
  manifest baseline, wrong parent chain, or foreign active M2 artifact is
  rejected/safely unavailable and is not returned as resumable.
- List ordering is deterministic and summaries contain no document bytes,
  raw document text, raw unreviewed evidence, or M1 answer text.
- List discovery does not write tables or create an M2 operation record.

### 13.2 Integration tests

- Use the existing honest synthetic package-ready M2 fixture. Start a normal
  M2 run through existing service behaviour, discard all Streamlit state, then
  build a fresh DCW read service: the run is discovered and may be selected.
- On M2 page resume, an exact matching non-terminal `run_id` with matching
  current M2 context reaches its existing stored stage. A forged, foreign,
  old-baseline, terminal, or stale `run_id` is cleared or retained for DCW
  inspection only and cannot call an M2 write method.
- A terminal, stale, blocked-conflict and compared run remains discoverable for
  inspection but has no action to overwrite or restart it.
- A completed run displays its existing comparison. A package-ready/no-
  comparison failure state displays no invented comparison.
- M1 status is read from its existing service and M1 remains non-decision;
  DCW does not create an M1 submission or review.
- Capture baseline approved-review, integrated-assessment and Decision Package
  artifact hashes; normal active pointers and workspace stage before and after
  DCW render/navigation/discovery are unchanged.

### 13.3 Boundary and protected-workspace tests

- Assert DCW/application code does not import or invoke assessment, package
  generation, review reset, M1/M2 mutation, policy, instrument, or direct
  SQL-write APIs.
- Point DCW at an `evaluation/portfolio` database path. It must not construct
  `SQLiteReassessmentRepository` or M2 service, migrate/open the M2 database,
  list M2 runs, write an M2 record, or set an active pointer. Hash/file bytes
  remain unchanged.
- Existing frozen PORT-001/002/003/004 hash verification passes unchanged.
- Existing GRW M1/M2 immutability, write-guard, lineage, idempotency, Phase
 5/6 anti-forgery, and comparison tests continue to pass unchanged.

### 13.4 UI tests

- New page appears in main navigation and Decision Package exposes its
  navigation-only continuation entry after package generation.
- DCW shows baseline-first, optional wording, exact existing recommendation,
  M1’s non-decision label, and the M2 separate-successor label.
- DCW hides raw gap lists and does not render an M1/M2 action where the existing
  context is unavailable.
- A fresh AppTest instance selects/resumes a persisted eligible non-terminal
  exact-baseline M2 run, while terminal/completed records are inspectable in
  DCW without a lifecycle action.
- Session-run mismatch, terminal/stale run, corrupted row error, package-not-
ready, and protected target show a safe, non-actionable state.
- UI contains no control that records evidence review, score/resolution,
reassessment approval, assessment, package generation, successor promotion, or
AEL action.

## 14. Non-change proofs

P1 completes only if tests establish all of the following after opening,
refreshing, selecting, or resuming through DCW:

```text
normal active APPROVED_REVIEW payload/hash       unchanged
normal active INTEGRATED_ASSESSMENT payload/hash unchanged
normal active DECISION_PACKAGE payload/hash      unchanged
normal workspace active-pointer map              unchanged
normal workspace stage                           unchanged
baseline policy/taxonomy/configuration           unchanged
M1/M2 evidence/admissibility semantics           unchanged
```

The only permitted state changes are those already initiated on existing M1/M2
pages and guarded by their existing services. Even then, DCW must retain the
baseline active and must not directly create, advance, approve, assess, package,
or promote a successor.

## 15. Implementation order

1. Add and test the repository’s exact-baseline read-only listing/validation.
2. Add immutable DCW view DTOs and read-only application service; prove no
   writes and protected-target refusal.
3. Add composition/context safety and session-key clearing.
4. Add the DCW page and Decision Package/navigation entry points.
5. Add M2 selected-run validation/resume and return navigation without changing
   any lifecycle form or service transition.
6. Add full integration, architecture and AppTest coverage.
7. Run relevant M1/M2/Phase 4–7 regressions, frozen portfolio verification,
   full suite, `compileall`, and `git diff --check` before seeking freeze.

## 16. Acceptance checklist

- [ ] A normal active package-ready workspace opens DCW with no write.
- [ ] DCW identifies the active formal baseline and its existing portfolio
      recommendations precisely.
- [ ] The customer can explicitly continue with the baseline without a write or
      an AEL implication.
- [ ] M1 appears only through its existing eligibility/status and retains its
      non-decision language.
- [ ] M2 appears only through its existing M2 M1 eligibility and identifies a
      specific `data_readiness` activity, not a globally ranked raw gap.
- [ ] Persisted M2 runs are discoverable after a fresh session only for the
      exact active baseline triple and validated manifest.
- [ ] An invalid, foreign, stale, old-baseline, terminal, or corrupt run cannot
      be advanced through DCW.
- [ ] Successor packages and comparisons are separate, hash-validated, neutral
      records; the normal baseline remains active.
- [ ] The implementation adds no new evidence/admissibility semantics,
      assessment/policy/gate/recommendation behaviour, persistence model, or
      migration.
- [ ] Protected evaluation/portfolio targets cannot use M1/M2 continuation or
      M2 discovery, and their bytes remain unchanged.
- [ ] All new tests and existing M1/M2, Phase 4–7 and frozen portfolio tests
      pass.

## 17. Explicit non-scope

P1 does not implement GRW M3 or broaden M2. It specifically excludes:

- new M1 questions, natural-language parsing, evidence classes, information-gap
  priority rules, evidence-admissibility rules, policy rows or instruments;
- CSV, data export, PDF/Office document, measured evidence, attestation, ROI,
  or additional criterion resolution;
- reset/review reopening, re-extraction, re-ingestion, baseline promotion,
  decision-policy/scoring/gate changes, or successor recomputation;
- new human-role, authentication, tenancy, enterprise retention/encryption,
  cloud, API, multi-user or notification architecture;
- AEL initiatives, business cases, pilots, implementation, deployment,
  governance execution, outcome measurement, or learning loops;
- historical portfolio/evaluation browsing or changes to frozen PORT/evaluation
  artefacts.

## 18. Decisions still requiring implementation approval

This plan assumes approval of the P1 DCW direction and makes no new methodology
decision. Before implementation, confirm the following product choices:

1. Add DCW as a separate sidebar page with a Decision Package entry point,
   rather than embedding it in the existing package page.
2. Add the exact-baseline, manifest-validated read query to the existing M2
   repository without a new persistent DCW model or migration.
3. Retain the strongest protected-workspace rule: evaluation/portfolio targets
   have no M1/M2 continuation or M2 discovery surface, even for read-only
   historical display.
4. Retain strict local single-user disclosure; P1 is product usability work,
   not enterprise authentication/authorisation work.

No production code, policy, schema, migration, frozen evaluation artefact, or
GRW M2 lifecycle change is authorised by this plan.
