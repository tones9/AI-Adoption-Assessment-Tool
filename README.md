# AI Business Process Opportunity Assessment Engine

This repository contains the Phase 1 deterministic backend foundation, Phase 2 document-ingestion layer, Phase 3 candidate process-extraction layer, Phase 4 human-review boundary, Phase 5 integrated assessment orchestration, and Phase 6 deterministic decision-package generation for an explainable decision-support system that identifies and prioritises potential AI adoption opportunities within **one documented business process at a time**.

The [Master Bible](AI_Adoption_Engine_MASTER_BIBLE_v1.0.docx) is the highest-authority project document. The implementation must not broaden the project scope or replace deterministic recommendation logic with unconstrained LLM judgement.

## Phase 1 status

Implemented in this phase:

- Typed current-state process and process-step models.
- Evidence, provenance, knowledge-state, and uncertainty models.
- The four locked recommendation modes.
- The approved canonical capability taxonomy and deterministic mapper.
- A replaceable, versioned decision policy.
- Ordered evidence, technical-fit, business-value, and risk/autonomy gates.
- Transparent priority scoring for qualifying opportunities.
- Evidence-backed reasoning output.
- One hand-authored synthetic process.
- A diagnostic JSON CLI.
- Unit and integration tests.

The `phase1-v0.3` contract preserves known, inferred, and unknown capability-signal states. Legacy explicit booleans remain accepted as known values. Descriptive process metadata and the step actor are optional when unavailable; structural identity, steps, activities, ordering, and assessment structures remain mandatory. The `decision_policy.v0.2` methodology is unchanged.

Not implemented in Phase 1:

- PDF or text ingestion, OCR, LLM integration, or LLM abstractions.
- Human-review or Streamlit UI.
- SQLite persistence or HTTP APIs.
- RAG, report generation, or future-state workflow generation.
- Enterprise integrations or benchmark experiments.

Phases 1–7 produce the working product MVP. Phase 8 is the mandatory MSc research evaluation phase.

## Phase 2 status

Phase 2 adds document ingestion only:

- Text-native PDF files through `pypdf`.
- Plain-text files with UTF-8/UTF-8-BOM first and `charset-normalizer` fallback.
- Pasted/raw text through a domain-level service.
- Deterministic document and block identifiers.
- Ordered text blocks, metadata, page/line locators, canonical document offsets, and structured warnings/errors.
- Explicit preservation of empty PDF page positions with an OCR-out-of-scope warning.

Phase 2 does **not** identify process steps, infer actors/systems/task characteristics, call an LLM, create a `BusinessProcess`, or run suitability analysis. Those responsibilities remain in later approved phases.

The document-only contract is:

```text
IngestionResult
  ├── status + issues
  └── IngestedDocument
        ├── deterministic document ID and source fingerprint
        ├── source/parser metadata
        ├── canonical text
        └── ordered TextBlock records with exact locators and offsets
```

### Canonical text and locator contract

- `CRLF` and `CR` line endings become `LF`.
- Leading/trailing spaces and tabs are removed from each line.
- Leading/trailing blank lines are removed; internal blank lines are retained as block boundaries.
- Text is otherwise preserved: no case, punctuation, spelling, table, or semantic cleanup.
- Blocks on the same input/page are joined with `LF + LF`.
- PDF pages are joined with `LF + form-feed + LF`; a page with no extractable text remains represented by an empty page block.
- Offsets are zero-based, half-open indexes measured in Python Unicode code points against `IngestedDocument.canonical_text`.
- Identical source bytes processed by the same parser/version produce the same document ID, block order, block IDs, source locators, and offsets.

PDFs with no extractable text do not invoke OCR. Encrypted, invalid, unreadable, empty, fallback-decoded, and page-partial inputs return explicit structured issues.

## Phase 3 status

Phase 3 converts one `IngestedDocument` into a **CANDIDATE / UNCONFIRMED PROCESS EXTRACTION**:

- Provider-independent candidate process, activity, characteristic, uncertainty, and provenance contracts.
- Deterministic Phase 2 block chunking with a one-block overlap and oversized-block slicing.
- Exact-snippet evidence resolution in application code. The provider cannot create trusted offsets.
- Conservative step deduplication, source ordering, and explicit ambiguity warnings.
- One repair attempt for invalid structured or evidence output.
- An optional OpenAI Responses API adapter using strict Pydantic structured output.
- A deterministic fake provider for tests and offline development.

Phase 3 does **not** create a validated `BusinessProcess`, invoke the decision engine, recommend AI adoption, produce a future-state workflow, or bypass Phase 4 human validation.

The initial provider configuration is externalised in [`config/extraction.v0.1.json`](config/extraction.v0.1.json). Its 40,000-character and 30-block chunk limits are engineering defaults, not research-derived optima.

The trusted evidence chain is:

```text
document_id → block_id → exact snippet resolved by Python
            → computed block/document offsets → candidate assertion
```

## Phase 4 status

Phase 4 creates the explicit human-validation boundary:

```text
CandidateBusinessProcess → ProcessReviewSession → explicit approval
                         → ApprovedProcessReview + BusinessProcess projection
```

Reviewers can accept, correct, reject, or explicitly retain unknown assertions; add human-supplied collection items; reorder or remove steps; correct dependencies; select an optional primary actor; and resolve structural conflicts. Every operation appends an immutable audit event containing before/after snapshots and optional rationale.

The canonical `ApprovedProcessReview` retains the original candidate, multiple actors, decisions, branches, exceptions, operational facts, extraction issues, source evidence, human corrections, unresolved non-blocking unknowns, and audit trail. Human-supplied values never receive fabricated Phase 2 evidence. The contained `BusinessProcess` is only the narrower validated projection required by Phase 1.

Approval requires confirmed process identity, explicitly accepted step order, a confirmed activity for every retained step, valid retained dependencies, no unresolved blocking structural conflicts, and an explicit human approval action. Unknown assessment criteria and capability signals do not block process validation.

Phase 4 is provider-independent and has no Streamlit, SQLite, OpenAI, or decision-engine runtime dependency.

## Phase 5 status

Phase 5 enforces the integrated application boundary:

```text
ApprovedProcessReview → validated BusinessProcess
                      → AssessmentEngine(decision_policy.v0.2)
                      → IntegratedAssessmentSuccess
```

`IntegratedAssessmentService` rejects candidates, extraction results, unapproved review sessions, blocked reviews, malformed approval artifacts, and invalid projections before engine invocation. The standalone Phase 1 engine remains independently callable for tests and research experiments.

Successful results retain the unchanged `ProcessAssessment`, cross-phase lineage identifiers, policy/version metadata, and a per-step traceability index linking assessment fields to reviewed assertions and trusted Phase 2 evidence. Human-supplied values retain `HUMAN_SUPPLIED`; accepted model inference remains `MODEL_INFERRED`.

SHA-256 fingerprints are calculated from canonical JSON for the exact validated process content and validated decision-policy content. The run-derived process ID is recorded separately and excluded from the process fingerprint, so assessment timestamps and run identifiers do not change either input fingerprint.

`INVESTIGATE_FURTHER`, unknown characteristics, and incomplete priority remain successful assessment outcomes. Pipeline failure is reserved for approval, projection, policy, engine-output, or traceability contract failures. Phase 5 introduces no OpenAI, Streamlit, SQLite, reporting, roadmap, ROI, or future-workflow functionality.

## Phase 6 status

Phase 6 converts a successful integrated assessment into a structured business-facing decision-support package:

```text
IntegratedAssessmentSuccess → DecisionSupportPackageService
                            → opportunity portfolio
                            → PROPOSED / NOT DEPLOYED future state
                            → roadmap with decision gates
                            → governance and information-gap summaries
                            → rendering-independent report content
```

Every assessed step remains visible in process order, including `INVESTIGATE_FURTHER` and `DO_NOT_RECOMMEND`. Recommendations, capabilities, gates, priority results, reasoning, and traceability are copied from Phase 5 without recalculation.

Future-state intervention patterns are deterministic: `AUTOMATE` becomes `AI_ENABLED_EXECUTION`, `AUGMENT` becomes `AI_ASSISTED_HUMAN_EXECUTION`, investigation retains the current step with an investigation marker, and negative recommendations retain current or conventional execution without an AI intervention. Capabilities remain separate from intervention patterns and never become vendor or solution architecture.

Roadmaps include explicit `GO / REVISE / STOP` and deployment decision points. Investigation roadmaps stop before proof-of-concept planning; negative recommendations receive no AI-deployment roadmap. Governance statements require validation and organisational review and make no legal, compliance, security-approval, ethical-acceptability, or deployment-readiness claim.

Phase 6 always states `ROI / quantified benefit unavailable with current evidence.` Package content is deterministic for equivalent Phase 5 semantic input, retains process/policy fingerprints, labels planning interpretations as `DERIVED_PLANNING_GUIDANCE`, and contains 13 rendering-independent report sections. No OpenAI, UI, HTML/PDF renderer, SQLite, or assessment-engine runtime dependency is introduced.

## Phase 7 status

Phase 7 adds the local Streamlit product and persistence layer over the unchanged Phase 1–6 contracts:

```text
Assessments → Source & Extraction → Process Review
            → Assessment Results → Decision Package
```

The five-page workspace enforces the backend boundaries: extraction is explicit, candidate output remains unconfirmed until Phase 4 approval, assessment requires the immutable approval artifact, and Phase 6 content is rendered without recreating assessment or planning rules. The process-review screen exposes document-supported, model-inferred, human-supplied and unknown information with literal source snippets and controlled Phase 4 service operations. Its persisted review-progress summary follows the actual Phase 4 approval rules, links each blocker to its affected step, and supports scoped confirmation of directly documented facts while retaining an individual assertion disposition and audit event for every confirmed fact.

Offline demo mode is permanently labelled `OFFLINE DEMO — SCRIPTED SYNTHETIC EXTRACTION` and operates only on [`data/demo/synthetic_complaint_process.txt`](data/demo/synthetic_complaint_process.txt). Arbitrary documents may be ingested in demo mode but cannot receive the scripted extraction. Live-provider mode never silently falls back to the demo adapter and requires an explicit extraction action plus local credentials.

SQLite remains an application adapter around the existing Pydantic artifacts. In-progress review state may be updated, while candidate, approval, integrated-assessment and decision-package artifacts are revisioned snapshots. Active-artifact pointers are separate from append-only history, so resetting a workspace makes a downstream chain non-current without rewriting or deleting it. Integrated assessments reference their exact approval artifact ID, and decision packages reference their exact integrated-assessment artifact ID.

The MVP is **local, single-user software for a user-controlled machine**. SQLite is not encrypted at rest. The application is not approved as a shared or public deployment for confidential organisational material. Original upload bytes are not retained; parsed document content and required typed artifacts are stored locally.

## Important methodology warning

The active policy is:

> **decision_policy.v0.2 — PROVISIONAL — NOT YET ACADEMICALLY VALIDATED**

Its thresholds, weights, and decision rules exist to make the architecture implementable and testable. They are not presented as scientific findings. The active policy is externalised in [`config/decision_policy.v0.2.json`](config/decision_policy.v0.2.json) so later literature review, benchmark findings, and expert validation can replace it without redesigning the engine. The tagged `phase1-v0.1` baseline retains the original globally complete evidence policy for historical reproducibility.

## Architecture

```text
Structured BusinessProcess
        │
        ├── supplied task characteristics (no Phase 1 inference)
        ├── hand-authored evidence references
        │
        ▼
Deterministic capability mapper
        │
        ▼
Evidence → technical fit → business value → risk/autonomy gates
        │
        ├── failed/insufficient gate → constrained recommendation
        └── qualifying opportunity → transparent priority score
        │
        ▼
StepAssessment with criterion provenance, evidence, gates, score status,
reasoning, and final mode
```

The engine performs no network calls and contains no LLM dependency.

## Criterion scale

Every Phase 1 criterion uses an ordinal `0–5` scale. `unknown` is represented by a null value and `knowledge_state="unknown"`.

Higher values are favourable for:

- repetition;
- predictability;
- data readiness;
- AI capability fit;
- business value.

Higher values are unfavourable for:

- human-judgement requirement;
- consequence/risk;
- residual risk with human oversight;
- implementation complexity;
- conventional-solution fit.

Each known or inferred criterion includes a rationale and supporting evidence IDs. Inferred values require a `0–1` confidence value. Human-accountability requirements use the same explicit known/inferred/unknown semantics and never default silently to `false`.

The v0.2 policy applies evidence requirements only when a criterion is material to the current gate. An unknown non-material criterion remains visible in `StepAssessment.criteria` but does not automatically force `INVESTIGATE_FURTHER`. Inferred confidence below `0.60`, or missing evidence, blocks a decision only when the affected input is material.

Exact scale meanings are documented in the policy file.

## Provisional decision order

1. The activity itself must have a source evidence reference.
2. AI capability fit is evaluated first; a decisive failure can stop the analysis without demanding unrelated later-gate evidence.
3. Conventional-solution fit is conditionally material when deterministic or workflow-automation signals make a non-AI alternative credible, or when it would cause `DO_NOT_RECOMMEND`. Its absence alone does not otherwise block the gate.
4. Data readiness is material when AI fit remains plausible; known readiness below `2` or materially insufficient evidence produces `INVESTIGATE_FURTHER`.
5. Business value is material at the value gate; a value below `2` produces `DO_NOT_RECOMMEND`.
6. Human judgement, consequence/risk, residual risk with oversight, and accountability are material at the risk/autonomy gate.
7. Residual risk of at least `4`, even with human oversight, produces `DO_NOT_RECOMMEND`.
8. Required human accountability, human judgement of at least `3`, consequence/risk of at least `3`, or residual risk of at least `2` produces `AUGMENT` without requiring predictability to be known.
9. Predictability becomes material only when the remaining evidence permits an `AUTOMATE` decision.
10. `AUTOMATE` requires predictability and data readiness of at least `4`, human judgement no more than `1`, consequence/risk no more than `2`, residual risk no more than `1`, and no mandatory human accountability.

Unknown information is never replaced by a confident invented value.

## Priority score

Only `AUTOMATE` and `AUGMENT` opportunities are eligible for a score. A recommendation can remain valid when a non-gate scoring input is unknown; in that case the priority is explicitly `incomplete`, no value is imputed, and the missing criteria are listed.

| Criterion | Weight | Direction |
|---|---:|---|
| Business value | 25% | Favourable |
| AI capability fit | 20% | Favourable |
| Data readiness | 15% | Favourable |
| Predictability | 10% | Favourable |
| Repetition | 10% | Favourable |
| Consequence/risk | 10% | Inverted |
| Implementation complexity | 10% | Inverted |

Priority bands are High at `70+`, Medium at `50–69.99`, and Low below `50`.

## Capability taxonomy

- `DOCUMENT_INFORMATION_EXTRACTION`
- `CLASSIFICATION`
- `PREDICTION_FORECASTING`
- `ANOMALY_PATTERN_DETECTION`
- `GENERATIVE_AI`
- `KNOWLEDGE_RETRIEVAL`
- `RECOMMENDATION`
- `DECISION_SUPPORT`
- `COMPUTER_VISION`
- `WORKFLOW_AUTOMATION`

`WORKFLOW_AUTOMATION` is represented because workflow orchestration may be part of an intervention, but the engine does not treat it as inherently AI. A high conventional-solution fit causes the engine to prefer rules-based automation or process redesign.

## Sample process

[`data/sample_processes/synthetic_customer_complaint_process.json`](data/sample_processes/synthetic_customer_complaint_process.json) is hand-authored and synthetic. It is not a benchmark and was not tuned against a real-world transformation case.

It intentionally exercises the four modes:

- Intake extraction and categorisation → `AUTOMATE`.
- Deterministic queue routing → `DO_NOT_RECOMMEND` because conventional rules are preferable.
- Knowledge-assisted response drafting → `AUGMENT`.
- Churn prediction without an identified outcome dataset → `INVESTIGATE_FURTHER`.
- Regulated redress approval with unacceptable residual risk → `DO_NOT_RECOMMEND`.

## Setup

Python 3.11 or newer is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install '.[dev]'
```

Install the optional OpenAI adapter only when live extraction is needed:

```bash
python -m pip install '.[dev,openai]'
```

## Run the diagnostic assessment

From the repository root:

```bash
python -m ai_adoption_engine
```

Or after installation:

```bash
ai-adoption-engine
```

The command emits the complete assessment as JSON, including the policy warning, complete criterion and accountability provenance, gate materiality, score status/components, recommendation reasoning, and resolved evidence.

Custom structured inputs can be supplied with:

```bash
python -m ai_adoption_engine --policy path/to/policy.json --process path/to/process.json
```

## Run tests

```bash
python -m pytest
```

The suite covers the complete Phase 1 engine plus document models, normalisation, offsets, stable identifiers, PDF page preservation, text decoding, ingestion warnings/errors, and proof that ingestion does not depend on Phase 1 process or decision modules.

## Run the Phase 7 application

Install the application and development dependencies, then launch Streamlit from the repository root:

```bash
python -m pip install -e '.[dev]'
python -m streamlit run streamlit_app.py
```

The default local database is `var/ai_adoption_engine.db`. Set `AI_ADOPTION_ENGINE_DB_PATH` to use a different local path. `OPENAI_API_KEY` is required only for an explicitly initiated live-provider extraction; the offline demo never needs it.

The report screen provides deterministic, print-friendly HTML export from the immutable Phase 6 decision package. Its Phase 7 presentation projection consolidates process-wide information gaps and governance considerations, leads roadmap and evidence entries with business activity names, and keeps IDs and fingerprints as secondary technical traceability. The underlying per-step Phase 6 records remain unchanged. It does not claim a dedicated PDF-generation feature.

## Use Phase 2 ingestion

```python
from ai_adoption_engine.ingestion import ingest_file, ingest_raw_text

pdf_result = ingest_file("current-process.pdf")
text_result = ingest_file("current-process.txt")
pasted_result = ingest_raw_text("Current-state process description...")
```

Each call returns `IngestionResult`; no call performs process extraction or AI-opportunity analysis.

## Use Phase 3 extraction

Provider-independent extraction can be tested without credentials by supplying an implementation of `StructuredExtractionProvider` to `ProcessExtractionService`.

The approved OpenAI adapter can be composed from versioned configuration:

```python
from ai_adoption_engine.extraction.providers.openai import (
    build_openai_extraction_service,
)

service = build_openai_extraction_service("config/extraction.v0.1.json")
candidate_result = service.extract(ingested_document)
```

That live call requires `OPENAI_API_KEY`. Normal automated tests never require an API key or the optional OpenAI package. No live request is made automatically.

## Repository layout

```text
config/                     Versioned decision policy
data/demo/                  Fixture-bound offline demonstration document
data/sample_processes/      Hand-authored Phase 1 input
.streamlit/                 Restrained local application theme
src/ai_adoption_engine/
  models/                   Typed input and output contracts
  decision/                 Mapper, gates, scoring, and engine
  ingestion/                PDF/text/raw-text document ingestion
  extraction/               Candidate extraction, evidence, merge, and providers
  review/                   Human review operations and explicit approval boundary
  application/              Phase 5 approval-gated integrated assessment
  decision_support/         Deterministic portfolio, workflow, roadmap, and report content
  persistence/              Versioned transactional SQLite adapter
  presentation/             Streamlit pages, components, state, and HTML rendering
  workspace/                Phase 7 guarded workflow and provider composition
  cli.py                    Diagnostic interface
streamlit_app.py            Shared Streamlit frame and five-page navigation
tests/unit/                 Isolated rules and validation tests
tests/integration/          Complete sample/CLI assessment test
tests/ui/                   Headless Streamlit application tests
```

Phase 8 research evaluation remains separate and has not started.
