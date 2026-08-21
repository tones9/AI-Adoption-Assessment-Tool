# Next product milestone P2 — Guided review and approval journey

Status: **DESIGN PROPOSAL — implementation requires approval**  
Version: v0.1  
Date: 2026-08-21  
Direction: **Productisation P2 — guided review and approval**

## Product-development context

This is a discovered productisation need, not a missing part of the original
Engine architecture. The original Engine produced an evidence-bounded Decision
Package. Portfolio validation then exposed important information gaps, which
led to GRW. GRW M1 established a safe non-decision evidence lifecycle and GRW
M2 established one controlled, evidence-backed reassessment path. Product
audit then showed that those continuation paths were fragmented and difficult
to resume; DCW P1 made the Decision Package the coherent continuation point.

Reviewing the complete current local product after DCW P1 exposes the next
problem: a customer still has to traverse a dense, technical Phase 4 editing
surface before any reliable Decision Package exists. P2 addresses that review
and approval experience only. It does not retrospectively make GRW, DCW, or
future execution capabilities part of the original Engine.

## 1. Problem discovered

The Engine correctly refuses to turn candidate extraction into a decision
without human review. That safety boundary is essential. The current Streamlit
page nevertheless combines all of the following in one dense activity editor:
document-supported facts, inferred facts, unknowns, collections, dependencies,
criteria, capability signals, structural conflicts, ordering, optional detail,
and final approval.

A reviewer can use the existing progress panel and grouped confirmation of
document-supported facts, but must still understand Phase 4 concepts and
navigate an eight-page technical sidebar to reach a useful decision. For a
real company, the main drop-off risk is not that the product has no post-package
route; it is that the accountable person may not finish the evidence-preserving
validation required to reach the first package.

P2 therefore solves a **product UX** problem: make the existing human-review
and approval boundary comprehensible, resumable, and manageable without
weakening it.

It does not solve a **methodology/evidence** problem. A better interface must
not make unverified extraction true, make a human estimate document-supported,
or force unknown values to be resolved.

## 2. Why this is the next milestone

P2 improves the mandatory bottleneck in every real journey before assessment,
Decision Package, DCW, M1, or M2 can help. It has higher immediate value than:

- broader GRW, which would require a new admissibility decision and more
  evidence-policy validation;
- report/export work, which improves a package that many users will not reach
  if review is burdensome;
- more workspace management, for which DCW P1 already supplies safe M2
  discovery and resumption; and
- AEL, which is premature while the product remains a local, single-user
  decision-support MVP with no delivery, role, or outcome-management contract.

The existing Phase 4 review service, approval boundary, review-progress
projection, persistence, and active-workspace integrity checks are sufficient
for a narrow presentation/orchestration milestone. No new evidence model,
policy, score, or database table is justified.

## 3. Customer journey before P2

```text
Create local assessment
        ↓
Supply one text-native PDF/text document or pasted text
        ↓
Explicitly run extraction
        ↓
Open Process Review
        ↓
Find the required fields among a full technical activity editor
        ↓
Individually confirm/correct/reject/retain, resolve structure and order
        ↓
Infer from progress whether approval is now possible
        ↓
Explicitly approve
        ↓
Assessment → Decision Package → DCW → optional GRW M1/M2
```

Pain points in the current journey are:

- initial navigation is stage-oriented rather than a guided task journey;
- the mandatory review work is mixed with non-blocking detail and internal
  terminology;
- corrected values, document citations, and human-supplied context need careful
  interpretation by the reviewer;
- approval readiness is shown, but the person approving does not first receive
  one concise, accountable summary of what will be approved, what changed, and
  what remains explicitly unknown; and
- a return visit persists the review session, but the page does not reliably
  reopen at a simple "next required action" without relying on the visitor to
  rediscover the work.

## 4. Customer journey after P2

```text
Candidate extraction completed
        ↓
Validate this process (guided review)
        ├── What the document directly says — confirm in groups or inspect
        ├── What needs your decision now — one required item at a time
        ├── What remains unknown — retain transparently when legitimate
        └── What is recommended to check — inferred/non-blocking items
        ↓
Approval readiness summary
        ↓
Existing explicit Phase 4 approval
        ↓
Assessment → Decision Package → DCW → optional GRW M1/M2
```

On return, the guided screen reloads the persisted active review and selects a
deterministic next required action. It can therefore show the person where to
continue, while the persisted review—not Streamlit session state—remains the
source of truth.

## 5. P2 scope

The smallest useful P2 is a replacement/reorganisation of the current Phase 4
**Process Review** presentation into a guided **Validate process** journey.

It will:

1. Lead with the candidate-process warning, a plain-language explanation of
   the review boundary, and a persisted approval-readiness summary.
2. Present the existing approval-required work as a short work queue: process
   identity, each retained activity, order, and any actual Phase 4 structural
   blocker.
3. Keep existing grouped confirmation for directly document-supported facts,
   with source snippets and locators available before confirmation.
4. Present inferred values, optional descriptive detail, and legitimate
   unknowns in separate, accurately labelled sections. They remain accessible
   but must not be presented as approval blockers unless the actual Phase 4
   approval preflight says they are.
5. Provide a final read-only approval summary derived from existing review
   events and `approval_errors`: confirmed/corrected/rejected items, unresolved
   required items, retained unknowns, human-supplied entries, changes to step
   order, and structural-conflict state.
6. Use the existing explicit approval confirmation and existing approval
   service only when the real preflight is ready.
7. Make recovery clear: a saved review can be reopened; a source replacement
   makes downstream work non-current under the existing workflow; and a save
   failure does not claim that an action succeeded.

P2 does not change what is required for approval. It changes only how the
existing state and permitted actions are presented.

## 6. UX behaviour

The customer-facing wording should use ordinary language while retaining
truthful evidence labels:

- **Candidate process — needs validation**: extraction is a proposal, not a
  decision or an approved process.
- **Confirm what the document says**: directly cited statements can be reviewed
  together after the reviewer can inspect the citations.
- **Decide the next required item**: accept, correct with a rationale, reject
  with a rationale, or retain a legitimate unknown through the existing Phase 4
  action. The interface must state the evidence origin of a correction.
- **Keep unknown when you do not know**: no customer is asked to invent a
  number or fill an optional descriptive field simply to advance.
- **Recommended checks**: model-inferred material remains visible and clearly
  separate from required approval work.
- **Ready to approve**: before the existing checkbox/button, show exactly what
  approval means: an acceptable human-reviewed representation of the
  current-state process, not a deployment decision or proof of a business
  outcome.

The page may retain a compact activity list and let the user select another
activity, but the default focus must be the first persisted approval blocker.
All detailed fields must remain available through progressive disclosure; P2
must not hide a reviewed assertion merely because it is non-blocking.

The approved state becomes a clear, read-only hand-off: current-state process
approved, unknowns retained as appropriate, then an existing link to Assessment
Results. It must not encourage `reset_to_review` as an ordinary navigation
action.

## 7. Existing capabilities reused unchanged

P2 reuses, without altering:

- Phase 2 ingestion and Phase 3 candidate extraction, including the current
  one-document text-native input scope and evidence locators;
- `ProcessReviewService` for every Phase 4 mutation;
- `AssessmentWorkspaceService.start_review`, `save_review`, and `approve` as
  the Engine write boundaries;
- `approval_errors` and `build_review_progress` as the side-effect-free view of
  the real approval boundary;
- existing artifact revisions, active-workspace chain validation, and
  idempotent operation handling;
- Phase 5 deterministic assessment and Phase 6 Decision Package generation;
- DCW P1's read-only baseline/continuation view and persisted M2 discovery;
- GRW M1's non-decision lifecycle and GRW M2's separate reassessment lineage,
  evidence review, resolution, approval, successor, and comparison services.

No P2 component may call an assessment, package-generation, GRW, or M2 write
operation as a side effect of review navigation or approval rendering.

## 8. Architecture

P2 belongs in Phase 7 presentation over the existing Phase 4 workflow. The
preferred architecture is a small, pure/read-only `ReviewJourneyView` (name
provisional) that projects the persisted active `ProcessReviewSession` into:

```text
candidate/process identity summary
approval readiness from the existing Phase 4 preflight
required queue in deterministic order
group-confirmable document-supported facts
recommended inferred items
legitimate unknowns retained
read-only approval hand-off summary
```

The Streamlit page renders this view and delegates any selected action to the
existing review/workspace services. The projection owns no approval rule and
does not calculate a new readiness score. It must call the same Phase 4
preflight used by approval rather than duplicate the rule in UI code.

The normal assessment active-pointer namespace, the M1 sidecar pointers, and
M2's separate reassessment namespace remain untouched. P2 neither reads nor
writes successor state as part of review.

## 9. Persistence requirements

Existing persistence is sufficient for the P2 slice. P2 needs no table,
migration, artefact type, schema version, operation type, or active pointer.

- The active `REVIEW_SESSION` remains the mutable, persisted Phase 4 working
  state under existing rules.
- The immutable `APPROVED_REVIEW` remains the approval record.
- Existing review events are the audit source for the approval hand-off
  summary.
- A selected queue item, expanded panel, or return location may use Streamlit
  session state only as transient presentation convenience. On reload it must
  be recomputed from the saved review/session preflight.

This deliberately keeps review progress recoverable without creating a second
review workflow or a competing source of truth.

## 10. Decision and evidence boundary

P2 explicitly guarantees that it does **not**:

- invent missing evidence or convert a customer statement into a fact;
- alter `UNKNOWN`, evidence origin, knowledge state, or review disposition
  except when a reviewer chooses an existing, explicitly permitted Phase 4
  action with its required rationale/evidence;
- convert a human-supplied correction into `DOCUMENT_SUPPORTED` without the
  existing restricted source-reference path;
- change gate semantics, criterion scoring, priority, recommendation, ROI, or
  decision-policy behaviour;
- assess, generate a Decision Package, or start/restart GRW/M2;
- bypass the existing human review or explicit approval boundary;
- weaken M1/M2 admissibility, successor-lineage, or comparison rules; or
- write to, repair, rerun, or otherwise mutate frozen evaluation artefacts.

The P2 UI must distinguish **what is directly documented**, **what was
inferred**, **what a reviewer supplied**, and **what remains unknown**. Better
copy and prioritisation must never silently make one class equivalent to
another.

## 11. Baseline and successor behaviour

P2 operates before the initial baseline Decision Package exists. It therefore
does not present a review edit as a revision of an existing formal Decision
Package.

Once a review is approved and the existing Phase 5/6 path creates a package,
that package is the baseline governed by DCW P1. P2 must not alter or obscure
it. Existing M2 successors remain separate reassessment-run artefacts, retained
and presented only through the existing M2/DCW contracts. A P2 page must never
promote a successor, replace a baseline, or interpret recommendation movement
as adoption success.

The existing `reset_to_review` operation is outside P2's guided journey because
it deliberately makes the ordinary active approval/assessment/package chain
non-current. If it remains exposed elsewhere, its present explicit warning and
historical retention semantics remain unchanged; P2 must not make it a casual
"edit" or recovery action.

## 12. Error and recovery behaviour

- **No assessment / no candidate**: direct the user to the existing prerequisite
  page with a plain-language explanation; do not fabricate a review session.
- **Reload or return later**: load the persisted active review and reconstruct
  the queue/readiness from it. Loss of browser state loses only panel selection,
  not review decisions.
- **Save/action failure**: show that the action was not saved, refresh from the
  persisted workspace, and offer retry. Customer copy should not expose raw
  exception-class names or internal trace details.
- **Approval preflight not ready**: enumerate only the actual outstanding
  requirements from the existing preflight and keep approval disabled.
- **Already approved**: render the existing approval as read-only and offer the
  existing next stage. Do not create a duplicate approval.
- **Source replaced or chain is non-current**: retain historical artefacts under
  current Engine rules and require review of the new active candidate; do not
  merge evidence from revisions.
- **Invalid/hash-failing workspace state**: retain the current no-partial-load
  failure behaviour. P2 must not attempt repair.

## 13. Frozen-workspace behaviour

Frozen portfolio/evaluation workspaces are never P2 editing targets. A P2
implementation must detect the established `evaluation/portfolio` protected
path boundary before composing or calling any Phase 4 write path. It may show a
safely loaded immutable record where existing read behaviour permits, but it
must suppress all Start review, Save review, Approval, and Reset/reopen
controls. A refused action must happen before database mutation.

This requires an explicit implementation decision: today the strong
service-level path guard is present for GRW M1/M2 and DCW's M2 composition, but
the ordinary Phase 2–7 workspace service does not uniformly apply it. For P2,
the narrow acceptable approach is a shared, fail-closed guard at the existing
Phase 4 write boundary (`start_review`, `save_review`, `approve`, and
`reset_to_review`) plus UI suppression. UI hiding alone is insufficient.

That guard must preserve ordinary non-evaluation workspaces and must not open,
migrate, or change a protected database merely to decide whether it is
protected. Extending the guard to all Phase 2–7 writes is a worthwhile separate
safety decision, not silently included in P2.

## 14. Deferred scope

P2 does not include:

- multi-document/process intake, OCR, Office/PDF expansion, or extraction-prompt
  changes;
- broader GRW questions, CSV/measured evidence, structured attestation, or new
  evidence/admissibility contracts;
- any new criterion, instrument, policy, gate, scoring, priority, ROI, or
  recommendation behaviour;
- revised Decision Package/report formats, PDF export, sharing, project
  portfolio management, or customer collaboration;
- reassessment beyond the frozen M2 M1 document-only `data_readiness` path;
- AEL initiatives, pilots, deployment, outcomes, or learning loops;
- APIs, authentication, tenancy, cloud hosting, encryption-at-rest, role
  separation, or enterprise security infrastructure; and
- changes to frozen PORT-001/002/003/004 or cross-case evaluation artefacts.

## 15. Acceptance criteria

P2 is complete only when a fresh, ordinary local workspace can demonstrate:

1. Candidate extraction opens one guided review journey that clearly states it
   is unconfirmed.
2. The next required review action and approval readiness are derived from the
   real Phase 4 preflight, with no UI-only alternate rule.
3. Directly document-supported facts can use the existing grouped confirmation
   only after their existing citations are visible.
4. The customer can clearly distinguish required work, recommended inferred
   checks, human-supplied content, and retained unknowns.
5. Every review mutation still passes through the existing review/workspace
   services; an attempted UI bypass or invalid state fails safely.
6. The final approval summary accurately reflects persisted review events,
   conflicts, order, corrections, rejections, and unknowns.
7. Approval remains an explicit existing human action and is unavailable until
   the existing approval boundary is ready.
8. Reloading or opening a fresh browser session restores the same persisted
   review and a deterministic next action without creating an artefact.
9. Baseline review/assessment/package artefacts and normal active pointers are
   unaffected by navigation, queue selection, and rendering.
10. M1/M2/DCW behaviour, Phase 5/6 deterministic behaviour, and all frozen
    portfolio hashes remain unchanged.
11. A protected evaluation/portfolio target refuses every P2 Phase 4 write
    before mutation and remains byte-identical; an ordinary local workspace
    remains writable.
12. Focused review/UI/boundary tests and the full regression suite pass.

## 16. Risks and decisions requiring approval

| Risk or concern | Mitigation / decision needed |
| --- | --- |
| A streamlined queue could conceal relevant non-blocking evidence. | Keep every assertion accessible, label rather than hide non-blocking content, and test the complete-detail path. |
| Plain language could erase important provenance distinctions. | Display origin/knowledge labels at decision points and reuse existing evidence components. |
| A reviewer may mistake progress for quality or confidence. | Call it approval readiness only; do not add a confidence score. |
| Local same-person review remains possible. | Keep the existing local-MVP limitation explicit; do not claim role separation. |
| Protected evaluation workspaces remain writable through ordinary Phase 2–7 service methods today. | Before implementation, approve the narrow Phase 4 service-level fail-closed guard described in section 13, or separately approve a broader Engine-wide guard. This is the only new architectural safety decision P2 needs. |
| The work grows into intake redesign or a new workflow engine. | Limit P2 to a Phase 4 presentation/projection layer with existing persistence and writes. |
| A redesigned page changes historical review semantics. | Derive readiness from `approval_errors`, reuse existing mutation services, and retain regression/portfolio boundary tests. |

## 17. Recommended future implementation sequence

After approval, implement only this order:

1. Freeze this governing design and agree the narrow Phase 4 protected-workspace
   write-guard decision.
2. Add a pure `ReviewJourneyView`/projection over the existing persisted review
   and existing approval preflight; add no persistence entity.
3. Reorganise the Process Review presentation around required queue, grouped
   document confirmation, retained unknowns, recommended inferred checks, and
   approval hand-off.
4. Route all review writes through the existing service methods; enforce the
   approved protected-workspace guard at that service boundary.
5. Add unit, integration, architecture, and Streamlit UI tests for queue
   accuracy, persistence/resumption, provenance labels, explicit approval,
   immutability, protected-workspace refusal, and M1/M2/DCW regressions.
6. Run the full suite and frozen portfolio hash verification, then perform an
   adversarial freeze audit before committing.

After P2 is evaluated with representative local users, the next decision should
be evidence-led: either improve the constrained first-document intake, improve
Decision Package/report shareability, or design one additional GRW evidence
path under its own approved policy. AEL remains out of scope until a secure,
role-aware product has an explicit adoption-execution contract.
