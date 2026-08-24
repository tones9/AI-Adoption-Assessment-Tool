# Portfolio Version 1 — Decision Experience governing design

Status: **DESIGN FROZEN — implementation requires approval**  
Version: v0.1  
Date: 2026-08-24  
Baseline: `2cd6799` (parent `a88f6cf`), full local suite green.  
Direction: **Portfolio Version 1 closure governance**

This document is **not** Productisation P3, **not** a new Engine phase, **not** a
new Gap Resolution Workspace (GRW) milestone, and **not** new decision
methodology. It governs how the existing, authoritative decisions the Engine
already produces are presented to a non-technical business user, so that
Portfolio Version 1 can be closed as a defensible, comprehensible product.

It changes no production code, test, schema, migration, policy, prompt,
taxonomy, portfolio artefact or frozen evaluation artefact.

## 1. Terminology boundary

These names are distinct and are used precisely throughout this document.

- **Engine phases 1–8** — the original architecture: intake, ingestion,
  extraction, human review, assessment, decision support, presentation,
  retrospective validation portfolio. Frozen.
- **GRW M1** — the optional, deliberately non-decision-affecting evidence
  lifecycle. Frozen.
- **GRW M2** — the narrow, controlled reassessment lifecycle that can produce a
  *separate successor* Decision Package. Frozen.
- **DCW** — the Decision Continuation Workspace, which makes the Decision
  Package the coherent continuation point. Frozen.
- **Productisation P2** — the guided review and approval journey. Delivered and
  frozen; its identifiers and behaviour are regression-protected.
- **Portfolio Version 1 closure (this work)** — a presentation-only change to
  information hierarchy across the existing decision-facing surfaces.

Portfolio Version 1 closure adds no capability. Every statement it puts in
front of a user already exists inside an authoritative Engine output.

## 2. Problem

The Engine is evidence-bounded and correct, but the decision-facing surfaces
are ordered by the shape of the artefact rather than the shape of the decision:

```text
technical state -> gates and criteria -> identifiers and provenance
        -> user attempts to infer the decision
```

Concretely, at the current baseline: Assessment Results opens with a
pipeline-completion banner and a five-column count row; the Decision Package
opens with a generation-status message and an ambiguous continuation button;
the DCW opens with the phrase "active formal baseline". In each case the
reader must reconstruct the outcome. All four gate results are rendered at
equal weight, including the `NOT_EVALUATED` gates that explicitly did nothing.

This is an **information-hierarchy** problem. Renaming `data_readiness` to
"Data readiness" leaves the page in the same wrong order. The required target
is:

```text
BUSINESS DECISION
        -> SPECIFIC EVIDENCE-SUPPORTED REASON
        -> WHAT IT MEANS
        -> NEXT PERMITTED ACTION
        -> TECHNICAL REASONING AND EVIDENCE (hidden by default)
```

## 3. Governing principles

### 3.1 The 10-second rule

On each primary decision-facing surface, a non-technical business user must be
able to answer these five questions within roughly ten seconds, **without
expanding any technical section**:

1. Where am I?
2. What happened, or what was decided?
3. Why?
4. What does this mean?
5. What can I do next?

This rule is the acceptance criterion for the work, not an aspiration.

### 3.2 Two-layer model

**Layer 1 — Business decision view.** Visible by default. Contains the
business-facing outcome, the specific evidence-supported explanation, the
specific missing information where structured data supports it, limitations,
and the next permitted action.

**Layer 2 — Technical reasoning and evidence.** Hidden by default behind one
consistently labelled expandable section, `Technical reasoning and evidence`.
Contains authoritative internal decision states, gates, criteria, scores,
policy identifiers, evidence provenance, technical identifiers, source
references, verbatim engine rationale, and fingerprints.

Technical detail is **relocated, never removed**. Every value visible at the
baseline must remain reachable after the change.

### 3.3 Specificity rule

A Layer 1 statement must be as specific as the existing structured evidence
permits, and no more specific.

If the structured evidence records only `data_readiness = UNKNOWN`:

- Allowed: "The available evidence does not establish whether the required data
  is ready for AI use."
- Not allowed, unless separately supported by structured evidence: "The source
  is missing data quality, accuracy and exception-handling information."

Never manufacture sub-gaps from a broad criterion name. Never parse engine
rationale strings to manufacture new business claims — engine rationale is
engine-owned prose and may change; it appears verbatim in Layer 2 only. Layer 1
derives from structured fields (section 5).

### 3.4 Wording safeguards

`UNKNOWN` means unknown, not bad. `INVESTIGATE_FURTHER` means the evidence is
insufficient, not that AI is unsuitable.

Do not describe a successor decision as an improvement, a success, an
optimisation, or evidence of deployment readiness. Do not claim predictive
accuracy, recommendation accuracy, proven Return on Investment (ROI), causal
impact, implementation success, or deployment readiness.

Stating a limitation is correct and required. "This assessment does not
establish Return on Investment (ROI)" is exactly the kind of sentence the
product should carry. The term ROI is **not** prohibited; unsupported positive
claims are.

### 3.5 Action design rule

Every actionable control must communicate its consequence. Before clicking, the
user must be able to tell whether the action navigates, records information,
requests a reassessment, approves something, generates a package, or leaves the
current formal decision unchanged.

Ambiguous labels such as "Continue decision" are not acceptable. Controls whose
only effect is to display reassurance text are not acceptable; if nothing
happens, the page should say so as text rather than offer a button.

## 4. Frozen Engine boundaries

The Decision Experience must not change: criteria; gates; scoring;
recommendation logic; decision states; policy semantics; evidence semantics;
provenance; human-review authority; approval authority; UNKNOWN behaviour; GRW
M1 semantics; GRW M2 admissibility and reassessment semantics; DCW lineage;
baseline immutability; successor separation; Decision Package meaning; database
schema; migrations.

Presentation consumes existing authoritative outputs only.

## 5. Permitted derivation sources for Layer 1

This section is the anti-invention control. A Layer 1 sentence is admissible
only if it restates one or more of the following existing structured fields.

| Business statement | Structured source |
| --- | --- |
| The activity's outcome | `StepAssessment.recommendation_mode` / `OpportunityPortfolioItem.recommendation_mode` |
| Which check determined the outcome | the first `GateResult` whose `status` is `FAILED` or `PASSED_WITH_CONSTRAINTS` |
| Which checks were never reached | `GateResult.status is NOT_EVALUATED` |
| Which facts were material to that check | `GateResult.material_criteria` |
| Which of those facts are absent | `CriterionAssessment.knowledge_state is UNKNOWN` |
| Whether a gap blocks the decision, the priority, or planning | `material_to_recommendation` / `material_to_priority` / `material_to_planning` |
| Which facts are assumed rather than confirmed | `KnowledgeState.INFERRED`, `InformationGapKind.INFERRED_REQUIRES_CONFIRMATION` |
| Why a priority score is absent | `PriorityStatus.INCOMPLETE` with `priority_missing_criteria` |
| Whether gaps are process-wide or activity-specific | the existing grouping in `report_view` |
| Whether the package has material gaps | `PackageCompleteness` |
| Whether any AI-adoption roadmap applies | `RoadmapStatus` |
| The next permitted step for an activity | `OpportunityRoadmap.stages[0].objective`, else `.rationale` |
| Whether a continuation route exists | `DecisionContinuationView.m1_context` / `.m2_context` being present |
| That the baseline is untouched by a successor | `DecisionContinuationApprovedChange.baseline_remains_active` |
| Limitations | `roi_statement`, `FutureStateStatus`, `MethodologyDisclosure.disclosure_statements`, the governance non-claim flags |

Two constraints follow from the data model and must be respected:

1. **Assessment Results has no `InformationGap` objects.** They are produced in
   Phase 6. On Assessment Results, gaps must derive from
   `CriterionAssessment.knowledge_state`, the criterion materiality flags and
   `priority_missing_criteria`. Only the Decision Package and report may use
   `InformationGap`.
2. **Assessment Results has no roadmap.** "What happens next" on that surface
   derives from the recommendation state and the fact that a Decision Package
   has not yet been generated — not from roadmap stages.

### 5.1 Explicitly not derivable

- The distinction between "inferred with confidence below the policy threshold"
  and "inferred and accepted". Reproducing it requires reading decision policy
  thresholds, which section 8 forbids. Layer 1 says the fact is recorded as an
  assumption rather than a confirmed fact; the engine's own rationale, which
  already names the threshold, stays in Layer 2.
- Any judgement about quality, adequacy, cost, benefit or likelihood.
- Any claim that supplying missing information will change the outcome.
- Any generalisation of one activity's gap across the process unless the
  existing grouping shows it genuinely spans every activity.

## 6. Target information hierarchy per surface

### 6.1 Assessment Results (primary)

```text
Assessment complete · <process name>

DECISION TODAY            overall business conclusion, one statement
WHAT WE FOUND             decided versus unresolved activities
WHAT INFORMATION IS       only when relevant; structured, evidence-supported;
  STILL NEEDED            distinguishes recommendation-impacting gaps
WHAT HAPPENS NEXT         next permitted product action
ACTIVITY-BY-ACTIVITY      per activity: outcome, specific reason,
  RESULTS                 missing information, next permitted action
  > Technical reasoning and evidence
```

The user must not have to reconstruct the outcome from metric counts, and
per-activity business content must not sit behind a selection control while
technical content is the only expanded structure.

### 6.2 Decision Package (primary)

```text
DECISION SUMMARY
WHY THIS DECISION WAS REACHED
WHAT THIS MEANS
WHAT HAPPENS NEXT
RISKS AND LIMITATIONS
Supporting report and detail
  > Technical reasoning and evidence
```

The Decision Package is the core deliverable, not a package-generation console.
Package identifiers, policy fingerprints, `PlanningOrigin` values, step
identifiers and comparable traceability must not dominate the initial view. The
page must answer: "What decision package did I receive, and what am I supposed
to understand from it?"

The limitation statements that currently sit in four separate places
(`roi_statement`, future-state status, the governance non-claim notice, and the
methodology disclosures) are consolidated into one RISKS AND LIMITATIONS block.
Their text and authority are unchanged.

### 6.3 Decision Continuation Workspace (primary)

```text
YOUR CURRENT OFFICIAL DECISION
WHAT THIS PAGE IS FOR
DO YOU NEED TO DO ANYTHING?      explicit yes or no
YOUR OPTIONS
  A. Continue with the current decision
     Nothing changes; this remains your official decision.
  B. Add preliminary context (GRW M1)
     Recorded and reviewed; cannot change the formal decision.
  C. Controlled reassessment (GRW M2)
     Requires reviewed supporting evidence, a reviewed resolution and explicit
     approval; may produce a separate successor decision.
PREVIOUS REASSESSMENTS            only when they exist
  > Technical baseline and traceability
```

Baseline, lineage, package identifier, hashes and run identifiers are retained
in technical traceability. The baseline and successor concepts are **not**
removed — they are explained in business language first. The page must not open
with "active formal baseline" as an unexplained term.

### 6.4 Decision Report (orientation rules)

The external report is decision-first. Presentation may reorder existing
content; it must not change the authoritative `DecisionReportContent` contract,
which validates that all thirteen sections are present in enum order. The
projection reorders for reading; the source is untouched and no section is
dropped.

The business-facing opening establishes: what was assessed, what was decided,
why, what information is missing, limitations, and the next permitted action.
Existing evidence and provenance remain later in the report. `PlanningOrigin`
values must not appear as visible badges on business prose.

### 6.5 GRW M1 (orientation rules)

The page must state what question is being asked, why it is being asked, and
that the answer cannot change the formal decision. The six formal "unchanged"
assertions remain available as detail but must not dominate the default view;
one business sentence carries the meaning above them.

Any sentence asserting that current information is sufficient must be
consistent with the package's actual `PackageCompleteness`.

### 6.6 GRW M2 / Reassessment (orientation rules)

Operational detail may remain — this is a controlled evidence process. The user
must still be able to see what the page is for, what the full controlled path
requires, where they currently are in it, what this step asks of them, and what
can happen only after explicit approval.

Internal enumerations, run identifiers, raw stage strings and character offsets
must not dominate the default view. **This design changes no M2 lifecycle
semantics, no admissibility rule and no input contract.**

## 7. Presentation architecture

1. **`src/ai_adoption_engine/presentation/decision_narrative.py`** — a pure,
   Streamlit-free, read-only projection, modelled on the existing
   `review_journey.py` pattern: frozen dataclasses built from authoritative
   outputs, no service, persistence or policy imports. Working names
   `ProcessNarrative` and `ActivityNarrative`; repository conventions may
   suggest better names. Being Streamlit-free is what makes the specificity and
   wording safeguards testable in isolation.
2. **A reusable decision summary/header component** rendering the
   where / what / why / meaning / next block identically on Assessment Results,
   Decision Package and DCW.
3. **A reusable expandable technical-details component** owning the single
   canonical label `Technical reasoning and evidence`.
4. **`src/ai_adoption_engine/presentation/labels.py`** — vocabulary
   infrastructure only. It maps internal tokens to business words. It must not
   become a hidden methodology or interpretation layer, and gate labels must not
   become a parallel decision engine.

`report_view.py` remains the report projection and consumes the narrative
module for its decision-first opening, so the in-app surfaces and the exported
report cannot disagree.

## 8. Architecture boundary

Presentation must not duplicate or reinterpret Engine decisions. It must not
import `decision.gates`, `decision.scoring` or `decision.policy` for the purpose
of reproducing decision behaviour. The existing boundary test already forbids
the first two; implementation should extend it to `decision.policy`.

Where a desirable explanation would require crossing this boundary, the correct
outcome is to drop the explanation, not to cross the boundary. Section 5.1
records the one known instance.

If implementation discovers a requirement that appears to need a change inside
a frozen module, the correct action is to **stop and request review**, not to
implement it.

## 9. Known `labels.py` corrections (documented only)

`labels.py` is untracked at this baseline and is **not modified by this
document**. The following corrections are recorded for the implementation that
first consumes it.

1. `not_evaluated` must not be rendered "Could not be evaluated". That invents a
   limitation: the Engine sets `NOT_EVALUATED` with the rationale that an
   earlier gate already determined the outcome. The business meaning must
   reflect that an earlier check already decided the result.
2. Package `COMPLETE` must not automatically be rendered "Decision ready" if
   that implies more than "no material information gaps".
3. Labels are vocabulary only. Gate status labels must not accumulate meaning
   that belongs to the assessment methodology.

## 10. Testing contract to freeze

Implementation must deliver:

- **Pure decision-narrative unit tests** — one per gate exit path, covering
  deciding-gate selection, missing-fact derivation, the three materiality
  statements, inferred-requires-confirmation phrasing, and next-step derivation
  including the empty-stages fallback.
- **Evidence-specific wording tests** — the derived sentence for a given
  structured input is exactly the sentence section 5 permits.
- **No-invention tests** — a broad `UNKNOWN` criterion must not produce
  enumerated sub-gaps; engine rationale must not be parsed into Layer 1.
- **Unsupported-positive-claim safeguards** — Layer 1 output must not contain
  claims of improvement, proven ROI, deployment readiness, proven suitability,
  or that a reassessment improved a decision. This is a test for unsupported
  positive claims, **not** a blanket prohibition on the token "ROI"; a
  limitation sentence containing ROI must pass.
- **Technical-layer completeness** — every technical value visible at the
  baseline remains reachable after the change.
- **UI hierarchy and order assertions** — the business outcome precedes any
  technical token on each primary surface; technical content is present but
  within an expandable section.
- **Consequence-specific action labels** — every actionable control names its
  consequence.
- **Regression, unmodified and green**: deterministic assessment; P2
  equivalence, including the `OutstandingReviewItem.item_id` contract; GRW M1
  and M2 lifecycles; DCW lineage; frozen-workspace protection; Phase 8
  portfolio and evaluation outputs.

## 11. Authorised implementation scope

May change:

- `src/ai_adoption_engine/presentation/**`
- focused presentation, UI and unit tests
- `docs/`

Must not change, unless a separately reviewed blocker is found and approved:

- `decision/**`
- the assessment engine and its services
- decision-support methodology
- authoritative models defining evidence or assessment semantics
- `grw/**` policy, models and services
- application decision and reassessment semantics
- `persistence/**`
- `workspace/**`
- schemas and migrations
- frozen evaluation artefacts and Phase 8 evaluation outputs

## 12. Explicit non-scope

This design does not authorise, and Portfolio Version 1 closure does not
include: the Adoption Execution Layer; implementation, pilots, deployment,
execution tracking or realised-outcome management; new criteria, gates, scores
or decision states; a broader GRW; new evidence types or admissibility rules;
changes to baseline immutability or successor separation; authentication,
tenancy, organisation administration, enterprise roles, encryption
infrastructure, APIs, integrations, hosted operations or monitoring platforms.

Commercialisation remains a separate track.

## 13. Completion criteria

1. Assessment Results, Decision Package and DCW each satisfy the 10-second rule
   without expanding a technical section.
2. No raw internal enumeration, internal identifier, policy identifier or
   fingerprint appears above the fold on those three surfaces.
3. Every technical value visible at the baseline remains reachable under the
   single label `Technical reasoning and evidence`.
4. Every actionable control names its consequence; no control exists whose only
   effect is reassurance text.
5. For `INVESTIGATE_FURTHER`, the surface names the specific missing facts that
   structured evidence supports, and no more.
6. The no-invention and unsupported-positive-claim tests pass across the three
   primary surfaces and the exported report.
7. All listed regression suites pass unmodified.
8. No file outside `src/ai_adoption_engine/presentation/**`, tests and `docs/`
   appears in any implementation commit.

## 14. Self-review record

Checked before freezing:

- No methodology change: this document defines presentation order and
  permitted derivation only. Section 5 constrains Layer 1 to restating existing
  structured fields; section 8 forbids reproducing decision behaviour.
- Terminology: Engine phases, GRW M1, GRW M2, DCW, Productisation P2 and
  Portfolio Version 1 closure are distinguished in section 1 and used
  consistently.
- No claim exceeds available evaluation evidence: the document asserts no
  accuracy, ROI, causal or deployment-readiness result, and section 3.4 forbids
  introducing one.
- Implementation scope is presentation-only (section 11).
- User-owned material is untouched.
- `labels.py` remains unmodified and untracked; section 9 records its
  corrections without applying them.
