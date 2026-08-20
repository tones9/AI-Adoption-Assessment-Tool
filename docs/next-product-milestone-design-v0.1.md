# Next product milestone — Decision Continuation Workspace

Status: **DESIGN PROPOSAL — implementation requires approval**  
Version: v0.1  
Date: 2026-08-20  
Direction: **Productise the Engine and frozen GRW M1/M2 capabilities**  
Proposed milestone name: **Productisation P1 — Decision Continuation Workspace (DCW)**

## 1. Problem being solved

The product can create a useful Decision Package and can now support two bounded
post-package evidence paths:

- GRW M1: one optional, non-decision estimate/range question; and
- GRW M2 M1: one tightly controlled document-supported `data_readiness`
  reassessment.

They are currently separate technical pages. A customer has to understand which
page to visit, whether a path is available, and how to resume a reassessment.
In particular, the M2 selected run is held in Streamlit session state even though
the immutable run itself is persisted. This makes the controlled lifecycle hard
to discover and awkward to resume after a page refresh or a new browser session.

The problem is not a lack of another evidence type. It is the absence of one
clear customer-facing continuation from the formal Decision Package:

> What can we responsibly conclude now, what optional next action is available,
> and what is the status of that action?

## 2. Why this is the correct next milestone

The portfolio validation showed that the Engine preserves uncertainty and still
delivers a package from thin process documentation. GRW was then added to make
selected uncertainty actionable without inventing facts. M1 and M2 now prove the
two relevant evidence lifecycles, but only as deliberately narrow local-MVP
surfaces.

Broader GRW would require new admissibility decisions, instruments, source types
and stronger role/privacy controls. AEL would assume that an organisation has
chosen to proceed, despite the current policy being provisional and the product
having no multi-user, pilot, governance or outcome-management foundation. A
research/report-only pause would improve presentation but would leave the product
journey fragmented.

DCW is therefore the smallest implementation that materially improves customer
value while preserving every current methodological boundary. It is a
productisation milestone, not a new decision method and not a GRW expansion.

## 3. Customer workflow

```text
Package-ready Decision Package
        ↓
Decision Continuation Workspace
        ├── “Here is the current formal recommendation”
        ├── “You may continue with it now”
        └── optional, already-supported evidence paths
                ├── M1: improve preliminary understanding
                └── M2: request controlled formal reassessment
        ↓
Existing M1 or M2 page, with exact baseline/run context selected
        ↓
Return to DCW
        ↓
Show immutable status and, when present, the neutral M2 comparison
```

For a package-ready assessment, DCW shows:

1. The baseline package identity, policy identity, and the selected activity's
   existing recommendation. It explicitly remains the active formal decision.
2. A plain-language statement that additional evidence is optional; customers can
   continue with the current recommendation.
3. At most the existing, deterministic M1 question when it is eligible. It is
   labelled **Improve understanding only — does not change the recommendation**.
4. At most the existing, deterministic M2 `data_readiness` route when eligible.
   It is labelled **Controlled formal reassessment — reviewed supporting document
   and explicit approval required**.
5. The persisted status of M1 and each M2 run attached to this exact baseline
   package. A user can resume a selected M2 run; they cannot silently replace it.
6. For a completed M2 run, the baseline-versus-successor comparison in its
   existing neutral language, while keeping the baseline package visibly active.

DCW does not rank all raw gaps, promise that an answer will improve a
recommendation, or expose M2's review controls to a customer who is only
providing a document.

## 4. Scope

This milestone is limited to a local presentation and read-model layer over
existing contracts.

- Add one Decision Continuation Workspace page reachable from the Decision
  Package and navigation.
- Add a pure/read-only decision-continuation view model/service which composes:
  active Phase 6 package information, existing M1 status, M2 M1 eligibility, and
  persisted M2 run summaries.
- Add a read-only M2 repository query that lists runs for an exact baseline
  assessment and package reference, including run ID, stage, timestamps and
  manifest-derived activity/gap summary.
- Replace the M2 page's session-only run discovery with explicit persisted-run
  selection. Session state may remember a selected run, but must never be the
  source of truth.
- Pass only selected IDs/references between pages. Each destination reloads and
  validates its context from persistence.
- Surface M1/M2 status and existing neutral comparison output in DCW.
- Add integration and UI tests for discoverability, resume, exact-baseline
  filtering, and read-only rendering.

## 5. Explicit non-scope

DCW must not implement or change:

- any new GRW evidence class, question, criterion, instrument, policy row or
  admissibility rule;
- decision-affecting M1 behaviour;
- any M2 path beyond one document-supported `data_readiness` reassessment;
- automatic answer-to-score mapping, automatic evidence acceptance, automatic
  approval, or automatic reassessment;
- raw-gap ranking or a claim that these are the globally most important gaps;
- PDF/Office/CSV/data-export intake, measurement, structured attestation, ROI,
  business-value/risk/accountability/capability-fit resolution;
- successor promotion over the active baseline;
- AEL initiatives, pilots, deployment, outcome measurement or learning loops;
- APIs, authentication, tenancy, collaborative roles, cloud hosting or encrypted
  storage.

## 6. Relationship to the Engine, Decision Package, GRW and future AEL

The Engine remains the authoritative Phase 1–6 decision path. Its approved
review, assessment and Decision Package are unchanged.

DCW is a Phase 7 productisation surface. It renders a package-ready baseline and
offers only existing GRW transitions. M1 remains a non-decision sidecar. M2
remains a separate immutable reassessment lineage with a distinct active-pointer
namespace. DCW owns neither evidence nor decisions.

A future AEL starts only after an organisation chooses to act on a decision. It
would govern initiative delivery, pilots, deployment and outcomes. DCW must not
become an AEL backlog or imply that a reassessment authorises deployment.

## 7. Required architecture changes

### 7.1 Read model

Introduce a presentation/application-level `DecisionContinuationService` (name
subject to implementation review), composed from existing repositories/services.
It returns immutable/read-only view data such as:

```text
DecisionContinuationView
  baseline package / approved review / assessment references and hashes
  baseline recommendation summary
  optional M1 route + current M1 status
  optional M2 route + eligible step/gap summary
  M2RunSummary[] for this exact baseline package
  optional completed comparison summaries
```

The service must not import Phase 4 mutation operations, the assessment engine,
or package generation. It may call M1/M2 *read* methods only.

### 7.2 Persisted run discovery

Add a read-only `list_runs_for_baseline(...)` operation to
`SQLiteReassessmentRepository`. It must filter by all of:

- baseline assessment ID;
- baseline Decision Package artefact ID; and
- baseline Decision Package payload SHA-256.

The returned summary must be derived from the persisted run and manifest, not
from session state. It must never update a run, repair a chain, or migrate a
frozen evaluation workspace merely to display it.

No new table, schema migration, M2 artefact type, or active pointer is required.

### 7.3 Presentation routing

DCW may persist only page-local selection state such as
`selected_m2_reassessment_run_id`. Before rendering an action, the destination
must reload the run and check that it belongs to the selected assessment and its
exact active baseline package. An invalid, stale, or foreign run must be shown as
unavailable and never be acted on.

Existing M1/M2 services remain the only write boundaries. DCW calls no direct
SQL mutation and does not duplicate lifecycle guards.

## 8. Required data and evidence contracts

No new evidence contract is introduced.

DCW may display only identifiers, hashes, status, current activity, gap field,
route description, provenance/evidence state already recorded by M1/M2, and the
existing comparison's neutral categories. It must retain the following
distinctions in customer copy:

| Route | Evidence effect | Formal effect |
|---|---|---|
| M1 estimate/range | `PRELIMINARY_UNDERSTANDING`, `RECORDED_ONLY`, or rejected | None |
| M2 reviewed document | Candidate until human review; then only the recorded permission | A successor only after resolution and explicit approval |

The DCW view binds every route and status to the immutable baseline references
already held by `GrwBaselineReference` or `M2BaselineReference`. It must never
present a M2 successor as an update to the original package.

## 9. Human approval boundaries

DCW may let a customer choose to continue with the current recommendation,
answer the existing M1 question, or begin/resume an M2 run. It may not:

- accept an M2 document as `DOCUMENT_SUPPORTED`;
- select a conflict outcome;
- map an M2 score;
- approve a reassessment;
- run Phase 5/6 automatically; or
- interpret a changed recommendation as success.

The existing M1 review, M2 evidence review, criterion-resolution review, and
reassessment approval remain separate, explicit human actions on their existing
screens.

## 10. Immutability and audit requirements

- DCW is read-only except where it explicitly delegates a selected write to an
  existing M1/M2 service.
- Opening, refreshing, or selecting a route must not create an M2 run or M1
  submission, change a stage, or write an operation record.
- M2 run lists must preserve terminal as well as completed states; a stopped or
  stale run remains an audit record, not an invitation to overwrite it.
- Baseline package/review/assessment references and normal active pointers must
  remain byte-identical after every DCW action other than an existing, already
  permitted GRW sidecar/reassessment write.
- Frozen evaluation/portfolio workspace protection remains enforced. DCW must
  refuse M2 routes for a protected target before any write path; pure reads do
  not waive the existing guard.
- All displayed successor/comparison content must cite its selected run and
  baseline package identity.

## 11. UX changes

Use native Streamlit containers, forms and buttons; no custom HTML or CSS is
needed for this milestone. The page should lead with the current decision, not a
list of technical artefacts.

- Add a prominent **Continue with current recommendation** action with no write.
- Use two clearly distinct sections: **Improve understanding** (M1) and
  **Controlled formal reassessment** (M2).
- Use short, plain-language eligibility/status labels. Keep internal
  `InformationGap` IDs, hashes and M2 stage codes in an expandable technical
  traceability section.
- Show an empty state when neither route is available; do not fabricate a
  question merely to fill the page.
- Make completed/blocked/stale M2 runs resumable for inspection only, and only
  active non-terminal runs actionable.
- Keep existing standalone M1/M2 pages for the narrow lifecycle work, but enter
  them with an explicit selected baseline/run context and provide a return path
  to DCW.

## 12. Safety and methodology risks

| Risk | Required mitigation |
|---|---|
| A clear call-to-action makes optional evidence look mandatory. | Repeat that the baseline package is useful and remains active; offer continue-with-current-decision first. |
| M1 appears to be formal evidence. | Preserve its non-decision label and show its formal effect as none. |
| An M2 successor appears to replace the baseline. | Show both identities; call it a separate successor and keep baseline active. |
| Route ordering is mistaken for global gap priority. | Present only existing eligible routes, without a new ranking claim. |
| Session state selects a foreign/stale run. | Revalidate all run/baseline references server-side before display/action. |
| Convenience UI bypasses evidence review. | Delegate all writes to existing guarded M1/M2 services only. |
| Local prototype safety is mistaken for enterprise readiness. | Retain local single-user/unencrypted-storage disclosure and defer identity, roles and tenancy. |

## 13. Minimal implementation milestone

**P1 acceptance slice:** one package-ready local assessment can open DCW, see
its baseline decision, see only available M1/M2 routes, open or resume a
persisted eligible M2 run after a new session, and return to DCW to see its
status/comparison. It must work with the existing synthetic M2 fixture and
without a new policy, migration, or assessment/package run.

Minimal implementation components:

1. `DecisionContinuationView` read model and service.
2. Read-only M2 run listing/filtering with exact-baseline validation.
3. One Streamlit DCW page and explicit selected-run handoff.
4. Small changes to M2 page bootstrapping/resume UI and Decision Package entry
   point.
5. Unit, integration, architecture and AppTest coverage.

## 14. Acceptance criteria

- A package-ready baseline opens DCW without creating or mutating any artifact.
- DCW displays the exact baseline package ID and existing recommendation.
- M1 appears only when existing M1 eligibility is true and retains its
  non-decision wording/status.
- M2 appears only when existing M2 M1 eligibility is true; it displays only the
  selected `data_readiness` route.
- An M2 run can be listed/resumed after a fresh Streamlit session from persisted
  state, only when its exact baseline references match.
- Foreign, stale, incomplete, or corrupted run references are refused or shown
  non-actionable without mutation.
- Terminal runs and comparisons remain inspectable and cannot be overwritten.
- Existing M1/M2 lifecycle, approval, frozen-workspace and baseline
  non-change tests continue to pass.
- No production policy, taxonomy, Phase 4–6 decision behaviour, frozen PORT
  artefact, or evidence/admissibility rule changes.

## 15. What should come after it

After P1 is tested with representative local users, make a deliberate choice
based on observed friction and methodology needs:

1. Conduct structured user research/demo evaluation on the end-to-end customer
   journey and revise product copy/workflow only where evidence supports it.
2. If a real decision need remains blocked by supported evidence, design one
   additional GRW evidence path with its own approved admissibility contract and
   versioned instrument. Do not generalise from M2's data-readiness path.
3. Only consider AEL once customers can make and select stronger decisions in a
   secure, role-aware product and there is an explicit initiative/governance
   contract.

## 16. Decisions requiring approval before implementation

1. Approve **Productisation P1 — Decision Continuation Workspace** as the next
   direction rather than broader GRW, AEL, or a research-only pause.
2. Approve the new read-only M2 `list_runs_for_baseline` repository query and
   its exact baseline-filter contract.
3. Approve adding DCW as a new navigation page rather than embedding it solely
   within the existing Decision Package page.
4. Approve persistent run selection as a local UX convenience, with the
   persisted run/manifest always authoritative.
5. Confirm that P1 must retain the current local single-user disclosure and is
   not authorization, tenancy, or enterprise-readiness work.

No implementation, policy change, production schema migration, evaluation
change, GRW expansion, or AEL work is authorised by this document.
