# AI Adoption Decision Engine

A local, explainable decision-support system that turns **one documented business
process** into a defensible AI-adoption decision.

It reads a process document, proposes a candidate reconstruction of that process,
requires a human to validate and explicitly approve it, assesses each activity
against a versioned deterministic policy, and produces a Decision Package with
the reasoning, the evidence and the missing information all recorded.

The product ends at the decision. It does not build, pilot, deploy or operate
anything.

The [Master Bible](AI_Adoption_Engine_MASTER_BIBLE_v1.0.docx) is the
highest-authority project document. The implementation must not broaden the
project scope or replace deterministic recommendation logic with unconstrained
LLM judgement.

## The problem

Organisations are asked to decide where AI belongs in their operations, usually
from process documentation that was never written to answer that question. The
common failure modes are a confident recommendation built on evidence nobody can
trace, and an analysis that quietly invents the facts it needs.

This engine takes the opposite position: a recommendation is only as good as the
evidence behind it, unknown information stays visibly unknown, and a decision a
reviewer cannot audit is not a decision.

## How it works

```text
business process documentation
  → candidate AI-assisted extraction
  → guided human review and validation
  → explicit approval
  → deterministic AI-adoption assessment
  → Decision Package / Decision Report
  → DONE
```

When the evidence does not support a recommendation for an activity, the
assessment records `INVESTIGATE_FURTHER` and names what is missing. That is a
complete result, not a failure, and the Decision Package is still produced. From
there the user may stop, or take an optional continuation path:

```text
INVESTIGATE_FURTHER
  → optional Decision Continuation Workspace
  → optional Gap Resolution Workspace
  → controlled reassessment where permitted
  → separate successor Decision Package + comparison
  → DONE
```

**The continuation paths are optional.** A user whose evidence is sufficient
finishes directly at the Decision Package and never sees them.

## What makes a decision defensible

**A trusted evidence chain.** Extraction proposes; Python resolves. The
extraction provider cannot create trusted offsets — snippets are matched in
application code against the ingested document:

```text
document_id → block_id → exact snippet resolved by Python
            → computed block/document offsets → candidate assertion
```

**Deterministic ingestion.** Identical source bytes processed by the same
parser produce the same document ID, block order, block IDs, source locators and
canonical offsets. Offsets are zero-based, half-open indexes in Unicode code
points against the canonical text, which normalises line endings and trailing
whitespace but performs no case, punctuation, spelling or semantic cleanup. PDFs
with no extractable text do not invoke OCR; encrypted, unreadable, empty and
page-partial inputs return explicit structured issues.

**Human review and explicit approval.** Nothing reaches the assessment engine
without a human approval artifact. Reviewers accept, correct, reject or
explicitly retain unknown assertions, reorder or remove steps, correct
dependencies and resolve structural conflicts. Every operation appends an
immutable audit event with before/after snapshots. Approval requires confirmed
process identity, an explicitly accepted step order, a confirmed activity for
every retained step, valid dependencies and no unresolved blocking conflicts.
Human-supplied values never receive fabricated document evidence.

**Unknown stays unknown.** A criterion with no supporting evidence is recorded
as `unknown` with a null value, not replaced by a confident invented number. The
policy applies evidence requirements only where a criterion is material to the
current gate, so an unknown non-material criterion stays visible without forcing
the outcome.

**`INVESTIGATE_FURTHER` is a legitimate outcome.** It is a statement about the
available evidence, not a judgement that the activity is unsuitable for AI, and
it is one of the four locked recommendation modes alongside `AUTOMATE`,
`AUGMENT` and `DO_NOT_RECOMMEND`.

**Determinism and lineage.** Equivalent semantic input produces equivalent
output. SHA-256 fingerprints are computed from canonical JSON for the validated
process content and the decision-policy content; run identifiers and timestamps
are excluded from those fingerprints. Each assessment references its exact
approval artifact, and each Decision Package references its exact assessment
artifact.

## When evidence is insufficient

Three optional surfaces sit after the Decision Package. None of them edits it.

**Decision Continuation Workspace (DCW).** Presents the current official
decision and the continuation options that are actually available for it, each
with what it requires and what it can produce. Option A is to stop.

**Gap Resolution Workspace — Milestone 1 (preliminary context).** One recorded
open question can be answered in plain language. The answer is retained exactly
as written, with how it was supplied and what a reviewer decided it may be used
for. M1 is **non-decision-affecting by construction**: it cannot change the
criteria, the checks, the scores, the recommendation, the priority, the ROI
statement or the Decision Package, and it never triggers a reassessment.

**Gap Resolution Workspace — Milestone 2 (controlled reassessment).** A narrow,
permitted path for supplying genuinely new documentary evidence. It requires, in
order: one reviewed plain-text supporting document, a reviewed evidence
decision, a reviewed resolution of the single permitted criterion — currently
data readiness only — and an explicit approval. Only then does it produce a
separate successor assessment and successor Decision Package. The route opens
only for an activity the assessment has already recorded as having that specific
open question; it does not widen the evidence types the engine accepts.

Three rules govern the result:

- **Baseline immutability.** The original Decision Package is never rewritten,
  edited or replaced. It remains the authoritative record for the evidence it
  was based on.
- **Successor separation.** The reassessment produces a *separate* Decision
  Package that sits alongside the original, with its own artifact identity and
  content fingerprint.
- **Deterministic, neutral comparison.** The baseline/successor comparison
  records formal differences. It does not describe recommendation movement as
  success, as an outcome, or as ROI proof, and a difference between the two is
  not evidence that adoption succeeded.

## The decision experience

Portfolio Version 1 makes every decision-facing surface decision-first. Each one
answers, before anything is expanded: **what was decided, why, what information
is missing, what the result means, and what you can do next.**

Identifiers, fingerprints, raw enumerations, gate rationale and provenance are
not removed — they move behind one consistent control, `Technical reasoning and
evidence`, so the full record stays available for inspection. The governing
design is frozen in
[`docs/portfolio-v1-decision-experience-design-v0.1.md`](docs/portfolio-v1-decision-experience-design-v0.1.md).

## What this product does not do

Out of scope, deliberately:

- implementing AI systems;
- running pilots;
- deploying models;
- managing execution;
- tracking realised outcomes.

The **Adoption Execution Layer** — governance, pilots, implementation,
deployment and measured outcomes after an organisation chooses to proceed —
remains future work and is not implemented here.

Commercialisation infrastructure is also outside Portfolio Version 1:
authentication, tenancy, integrations and hosted operations.

No output of this system constitutes a legal conclusion, a security approval, an
ethical acceptability judgement, or a deployment-readiness decision.

## Portfolio Version 1 status

Implemented and covered by the test suite:

| Capability | State |
|---|---|
| Document ingestion — text-native PDF, plain text, pasted text | Implemented |
| Candidate process extraction with resolved source evidence | Implemented |
| Guided review, validation and explicit approval | Implemented |
| Deterministic assessment against `decision_policy.v0.2` | Implemented |
| Decision Package and Decision Report with HTML export | Implemented |
| Decision Continuation Workspace | Implemented |
| GRW Milestone 1 — preliminary context | Implemented |
| GRW Milestone 2 — controlled reassessment | Implemented |
| Successor Decision Package and deterministic comparison | Implemented |
| Controlled reassessment report with HTML export | Implemented |
| Decision-first presentation across all decision surfaces | Implemented |
| Frozen evaluation workspace protection | Implemented |

The local Streamlit application registers **eight pages**
(see [`streamlit_app.py`](streamlit_app.py)):

| Page | Purpose |
|---|---|
| Assessments | Create, open and manage local assessments |
| Source & Extraction | Supply one document, inspect ingestion, start extraction |
| Validate process | Guided human review, correction and approval |
| Assessment Results | The decision for each activity, and why |
| Decision Package | The decision deliverable, its report and HTML export |
| Decision continuation | The optional continuation options for a decision |
| Gap resolution | GRW Milestone 1 preliminary context |
| Reassessment | GRW Milestone 2 controlled reassessment |

The application enforces the backend boundaries: extraction is explicit,
candidate output stays unconfirmed until approval, assessment requires the
immutable approval artifact, and decision-support content is rendered without
recreating assessment or planning rules.

Every capability listed above is implemented and exercised by the test suite.
The remaining Portfolio Version 1 work is demonstration material rather than
product capability — see the note on the offline demo below.

## Assessment method

Concise summary only. The authoritative policy is
[`config/decision_policy.v0.2.json`](config/decision_policy.v0.2.json).

### Criterion scale

Every criterion uses an ordinal `0–5` scale. Unknown is a null value with
`knowledge_state="unknown"`.

Higher is favourable for repetition, predictability, data readiness, AI
capability fit and business value. Higher is unfavourable for human-judgement
requirement, consequence/risk, residual risk with human oversight,
implementation complexity and conventional-solution fit.

Each known or inferred criterion carries a rationale and supporting evidence
IDs; inferred values carry a `0–1` confidence. Human-accountability requirements
use the same known/inferred/unknown semantics and never default silently to
`false`.

### Decision order

1. The activity itself must have a source evidence reference.
2. AI capability fit is evaluated first; a decisive failure can stop the
   analysis without demanding unrelated later-gate evidence.
3. Conventional-solution fit is conditionally material when deterministic or
   workflow-automation signals make a non-AI alternative credible, or when it
   would cause `DO_NOT_RECOMMEND`.
4. Data readiness is material when AI fit remains plausible; known readiness
   below `2`, or materially insufficient evidence, produces `INVESTIGATE_FURTHER`.
5. Business value is material at the value gate; a value below `2` produces
   `DO_NOT_RECOMMEND`.
6. Human judgement, consequence/risk, residual risk with oversight and
   accountability are material at the risk/autonomy gate.
7. Residual risk of at least `4`, even with human oversight, produces
   `DO_NOT_RECOMMEND`.
8. Required human accountability, human judgement of at least `3`,
   consequence/risk of at least `3`, or residual risk of at least `2` produces
   `AUGMENT`.
9. Predictability becomes material only when the remaining evidence permits an
   `AUTOMATE` decision.
10. `AUTOMATE` requires predictability and data readiness of at least `4`, human
    judgement no more than `1`, consequence/risk no more than `2`, residual risk
    no more than `1`, and no mandatory human accountability.

### Priority score

Only `AUTOMATE` and `AUGMENT` opportunities are eligible. When a non-gate
scoring input is unknown the priority is explicitly `incomplete`, no value is
imputed, and the missing criteria are listed.

| Criterion | Weight | Direction |
|---|---:|---|
| Business value | 25% | Favourable |
| AI capability fit | 20% | Favourable |
| Data readiness | 15% | Favourable |
| Predictability | 10% | Favourable |
| Repetition | 10% | Favourable |
| Consequence/risk | 10% | Inverted |
| Implementation complexity | 10% | Inverted |

Bands are High at `70+`, Medium at `50–69.99`, Low below `50`.

### Capability taxonomy

`DOCUMENT_INFORMATION_EXTRACTION`, `CLASSIFICATION`, `PREDICTION_FORECASTING`,
`ANOMALY_PATTERN_DETECTION`, `GENERATIVE_AI`, `KNOWLEDGE_RETRIEVAL`,
`RECOMMENDATION`, `DECISION_SUPPORT`, `COMPUTER_VISION`, `WORKFLOW_AUTOMATION`.

`WORKFLOW_AUTOMATION` is present because orchestration may be part of an
intervention, but the engine does not treat it as inherently AI. A high
conventional-solution fit causes the engine to prefer rules-based automation or
process redesign.

### Methodology warning

The active policy is:

> **decision_policy.v0.2 — PROVISIONAL — NOT YET ACADEMICALLY VALIDATED**

Its thresholds, weights and decision rules exist to make the architecture
implementable and testable. They are not presented as scientific findings. The
policy is externalised so later literature review, benchmark findings and expert
validation can replace it without redesigning the engine.

## Evaluation status

Phase 8 research evaluation has been carried out and its **portfolio validation
is complete and frozen**. It evaluated the unchanged production pipeline; it did
not modify or reimplement any application methodology, and production code never
imports `evaluation`. The earlier six-case confirmatory and reviewer
infrastructure is preserved separately under `evaluation/cases/` and
`evaluation/protocol/`.

The frozen portfolio validation covers three retrospective cases —
**PORT-001** (insurance claims-document processing), **PORT-002**
(telecommunications customer-call routing) and **PORT-004** (patent-examiner
prior-art search). A fourth case, PORT-003, is retained historically with status
`SUPERSEDED_CONTAMINATED_BEFORE` and excluded from every aggregate and
conclusion: its source audit found the prior workflow was knowable only from
AFTER-dated material.

Across the 20 assessed activities in the included cases, **all 20 resulted in
`INVESTIGATE_FURTHER`**, each stopping at the technical-fit gate because AI
capability fit remained unknown in the source documents.

**What that supports.** The engine reconstructed source-backed activities,
added no unsupported activity, preserved uncertainty rather than guessing, and
still produced a Decision Package when the evidence was insufficient. It is
evidence of cautious, deterministic handling of incomplete evidence.

**What that does not establish.** The frozen evaluation does **not** validate:

- predictive accuracy;
- recommendation accuracy;
- threshold, weight or scoring-band choices;
- proven ROI or quantified benefit;
- causal business impact;
- deployment readiness;
- cross-industry generalisation.

Three retrospective cases across two production fingerprint cohorts cannot
support statistical, causal or precision/recall claims, and the portfolio
contains no negative case. The full record, including its own limitations, is in
[`evaluation/portfolio/cross_case_summary.v0.2.md`](evaluation/portfolio/cross_case_summary.v0.2.md).

## Running it

Python 3.11 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

Launch the application from the repository root:

```bash
python -m streamlit run streamlit_app.py
```

The default local database is `var/ai_adoption_engine.db`; set
`AI_ADOPTION_ENGINE_DB_PATH` to use a different local path. `OPENAI_API_KEY` is
required only for an explicitly initiated live-provider extraction — the offline
demo never needs it. Install the optional provider adapter only when live
extraction is needed:

```bash
python -m pip install -e '.[dev,openai]'
```

### The offline demos, described honestly

Offline demo mode is permanently labelled
`OFFLINE DEMO — SCRIPTED SYNTHETIC EXTRACTION`. Scripted extraction is bound to
the exact bundled document it was written for; arbitrary documents can be
ingested in demo mode but cannot receive it, and live-provider mode never
silently falls back to the demo adapter.

Two bundled fixtures ship, chosen on the **Source & Extraction** page under
*Bundled synthetic demo*. Both are synthetic demonstration data — neither is a
customer process, research evidence, or a record of any measured outcome.

**A — Customer complaint handling (evidence gap).** The default.
[`data/demo/synthetic_complaint_process.txt`](data/demo/synthetic_complaint_process.txt)
is a process narrative that states no assessment criterion, so the scripted
extraction records **every criterion as `unknown`** and all seven activities
return "more information needed". This is what the engine does when a document
does not support a decision, and it is the behaviour the Phase 8 portfolio
observed on real documents.

**B — Field service request handling (documented facts).**
[`data/demo/synthetic_field_service_process.txt`](data/demo/synthetic_field_service_process.txt)
records, for each of its four activities, the operational facts an adoption
decision needs — volume, predictability, data availability, judgement, risk,
complexity and accountability — each in a sentence the extraction cites. Running
it produces four different outcomes from the unchanged policy:

| Activity | Outcome | Priority |
|---|---|---|
| Sort incoming maintenance requests | `AUTOMATE` | 75.0 (High) |
| Check the request against the service contract | `INVESTIGATE_FURTHER` | not scored |
| Draft the scheduling note for the field engineer | `AUGMENT` | 65.0 (Medium) |
| Approve or refuse a goodwill repair | `DO_NOT_RECOMMEND` | not scored |

Those outcomes are engine output, not fixture text: the source states facts, a
human reviewer accepts them, and the policy decides. The entitlement check keeps
its data-readiness question open, which makes it eligible for the controlled
reassessment route. To demonstrate that route, supply
[`data/demo/synthetic_field_service_contract_records.txt`](data/demo/synthetic_field_service_contract_records.txt)
as the supporting document on the Reassessment page. The baseline Decision
Package stays exactly as it is, and a separate successor is produced alongside
it.

Capability signals the source does not mention stay `unknown` in both fixtures.
They are recorded as immaterial to the recommendation rather than assumed away.

### Diagnostic CLI

The standalone engine can be run against a structured process input without the
application:

```bash
python -m ai_adoption_engine
python -m ai_adoption_engine --policy path/to/policy.json --process path/to/process.json
```

It emits the complete assessment as JSON, including the policy warning, criterion
and accountability provenance, gate materiality, score status and components,
recommendation reasoning and resolved evidence. The default input,
[`data/sample_processes/synthetic_customer_complaint_process.json`](data/sample_processes/synthetic_customer_complaint_process.json),
is hand-authored and synthetic; it is not a benchmark and was not tuned against
a real transformation case. It exercises all four recommendation modes.

### Tests

```bash
python -m pytest
```

The suite covers the decision engine, ingestion and locator contracts,
extraction and evidence resolution, the review and approval boundary, integrated
assessment, decision-package generation, persistence, the GRW M1 and M2
lifecycles, frozen-workspace protection, the Phase 8 evaluation harness, and the
Streamlit surfaces end to end.

## Data handling and deployment posture

This is **local, single-user software for a user-controlled machine**. SQLite is
not encrypted at rest. The application is not approved as a shared or public
deployment for confidential organisational material. Original upload bytes are
not retained; parsed document content and the required typed artifacts are
stored locally.

Frozen evaluation workspaces are protected: writes are refused before a
transaction is opened, the databases are never migrated in place, and their
bytes are left unchanged.

## Repository layout

```text
config/                     Versioned decision policy and extraction configuration
data/demo/                  Fixture-bound offline demonstration document
data/sample_processes/      Hand-authored structured engine input
docs/                       Design and implementation records
evaluation/                 Isolated Phase 8 research evaluation (never imported by production)
.streamlit/                 Restrained local application theme
src/ai_adoption_engine/
  models/                   Typed input and output contracts
  decision/                 Mapper, gates, scoring and engine
  ingestion/                PDF/text/raw-text document ingestion
  extraction/               Candidate extraction, evidence, merge and providers
  review/                   Human review operations and the explicit approval boundary
  application/              Approval-gated integrated assessment and decision continuation
  decision_support/         Deterministic portfolio, workflow, roadmap and report content
  grw/                      Gap Resolution Workspace: M1 preliminary context, M2 reassessment
  persistence/              Versioned transactional SQLite adapter and workspace protection
  presentation/             Streamlit pages, decision narrative, labels and HTML rendering
  workspace/                Guarded workflow and provider composition
  cli.py                    Diagnostic interface
streamlit_app.py            Shared Streamlit frame and eight-page navigation
tests/unit/                 Isolated rules and validation tests
tests/integration/          Lifecycle and end-to-end pipeline tests
tests/architecture/         Import-boundary and layering tests
tests/ui/                   Headless Streamlit application tests
```

## Further documentation

- [`docs/portfolio-v1-decision-experience-design-v0.1.md`](docs/portfolio-v1-decision-experience-design-v0.1.md)
  — the frozen governing design for the decision-first interface.
- [`docs/gap-resolution-workspace-design-v0.1.md`](docs/gap-resolution-workspace-design-v0.1.md)
  and [`docs/grw-m2-reassessment-design-v0.1.md`](docs/grw-m2-reassessment-design-v0.1.md)
  — the Gap Resolution Workspace and controlled reassessment designs.
- [`docs/grw-evidence-admissibility-policy-design-v0.1.md`](docs/grw-evidence-admissibility-policy-design-v0.1.md)
  — evidence admissibility rules for the reassessment path.
- [`docs/p2-guided-review-implementation-plan-v0.1.md`](docs/p2-guided-review-implementation-plan-v0.1.md)
  — the guided review and approval journey.
- [`evaluation/README.md`](evaluation/README.md) — Phase 8 scope, study boundary
  and safety controls.
- [`evaluation/portfolio/README.md`](evaluation/portfolio/README.md) — frozen
  portfolio composition and case-data boundaries.
- [`evaluation/portfolio/cross_case_summary.v0.2.md`](evaluation/portfolio/cross_case_summary.v0.2.md)
  — the cross-case findings and their limitations.
