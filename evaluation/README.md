# Phase 8 Evaluation

This directory contains the isolated Phase 8 research-evaluation layer for the
AI Adoption Engine. Phase 8 evaluates the frozen Phase 1-7 system; it does not
change or reimplement application methodology.

## Frozen production baseline

- Git commit: `4f2ba07b30f108f4b78ee5c7dc9ab42bb7956cf9`
- Decision policy: `decision_policy.v0.2`
- Extraction configuration: `extraction.v0.1`
- Extraction prompt: `process-extraction.v0.1`
- Candidate schema: `candidate-process.v0.1`

The governing protocol is
[`protocol/phase8_protocol_v0.1.md`](protocol/phase8_protocol_v0.1.md).
Confirmatory runs are forbidden until the development-case checkpoint has been
reviewed and explicitly approved.

## Study boundary

The four mandatory studies are:

1. unreviewed extraction evaluation;
2. decision-isolated engine and baseline comparison;
3. end-to-end evaluation including review effort; and
4. reduced live-provider repeatability on approximately three cases.

The two development cases are synthetic controlled fixtures. They validate the
evaluation harness only and are excluded from confirmatory claims. The six
confirmatory case packets are source-provenance proposals at this checkpoint;
their sealed after packets must not be opened during before-state work.

## Safety controls

- `harness/case_loader.py` verifies source hashes and denies after-packet access
  unless recommendations have been frozen for post-freeze analysis.
- The baseline runner cannot read the production policy.
- Evaluation code imports the frozen application contracts; production code
  must never import `evaluation`.
- Generated run artifacts must carry a validated run manifest.

