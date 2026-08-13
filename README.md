# AI Business Process Opportunity Assessment Engine

This repository contains the Phase 1 backend foundation for an explainable decision-support system that identifies and prioritises potential AI adoption opportunities within **one documented business process at a time**.

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

Not implemented in Phase 1:

- PDF or text ingestion, OCR, LLM integration, or LLM abstractions.
- Human-review or Streamlit UI.
- SQLite persistence or HTTP APIs.
- RAG, report generation, or future-state workflow generation.
- Enterprise integrations or benchmark experiments.

Phases 1–7 produce the working product MVP. Phase 8 is the mandatory MSc research evaluation phase.

## Important methodology warning

The active policy is:

> **decision_policy.v0.1 — PROVISIONAL — NOT YET ACADEMICALLY VALIDATED**

Its thresholds, weights, and decision rules exist to make the architecture implementable and testable. They are not presented as scientific findings. The policy is externalised in [`config/decision_policy.v0.1.json`](config/decision_policy.v0.1.json) so later literature review, benchmark findings, and expert validation can replace it without redesigning the engine.

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
StepAssessment with evidence, gates, score, reasoning, and final mode
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

Each known or inferred criterion includes a rationale and supporting evidence IDs. Inferred values require a `0–1` confidence value. The provisional evidence gate treats inferred confidence below `0.60` as materially insufficient.

Exact scale meanings are documented in the policy file.

## Provisional decision order

1. Materially unknown, unsupported, or low-confidence evidence produces `INVESTIGATE_FURTHER`.
2. No mapped capability, AI fit below `3`, or conventional-solution fit of at least `4` produces `DO_NOT_RECOMMEND`.
3. Known data readiness below `2`, where AI remains plausible, produces `INVESTIGATE_FURTHER`.
4. Business value below `2` produces `DO_NOT_RECOMMEND` and identifies conventional process improvement as preferable.
5. Residual risk of at least `4`, even with human oversight, produces `DO_NOT_RECOMMEND`.
6. Required human accountability, human judgement of at least `3`, consequence/risk of at least `3`, or residual risk of at least `2` produces `AUGMENT`.
7. `AUTOMATE` requires predictability and data readiness of at least `4`, human judgement no more than `1`, consequence/risk no more than `2`, residual risk no more than `1`, and no mandatory human accountability.
8. Other viable cases conservatively produce `AUGMENT`.

Unknown information is never replaced by a confident invented value.

## Priority score

Only `AUTOMATE` and `AUGMENT` opportunities receive a score.

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
python -m pip install -e '.[dev]'
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

The command emits the complete assessment as JSON, including the policy warning, capabilities, gate trace, score components, recommendation reasoning, and resolved evidence.

Custom structured inputs can be supplied with:

```bash
python -m ai_adoption_engine --policy path/to/policy.json --process path/to/process.json
```

## Run tests

```bash
python -m pytest
```

The suite covers model validation, evidence sufficiency, every recommendation path, conventional-solution preference, capability mapping, scoring, deterministic repeatability, and the CLI integration path.

## Repository layout

```text
config/                     Versioned decision policy
data/sample_processes/      Hand-authored Phase 1 input
src/ai_adoption_engine/
  models/                   Typed input and output contracts
  decision/                 Mapper, gates, scoring, and engine
  cli.py                    Diagnostic interface
tests/unit/                 Isolated rules and validation tests
tests/integration/          Complete sample/CLI assessment test
```

Future-phase packages will be added only when those phases are approved.

