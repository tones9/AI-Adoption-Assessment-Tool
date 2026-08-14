# Unconstrained LLM Baseline Protocol v0.1

Identifier: `phase8-llm-baseline.v0.1`

Prompt identifier: `phase8-unconstrained-baseline-prompt.v0.1`

## Primary comparison

The primary baseline participates in decision-isolated Study B. It receives a
neutral rendering of the same adjudicated before-state information supplied to
the deterministic engine.

It must not receive policy thresholds, gates, weights, scores, engine output,
later interventions, after packets, or external tools.

## Configuration

Use the same requested model family as the frozen live extraction configuration
where available. Record requested and effective model, reasoning settings,
token limits, request identifier, timestamps, usage, and failures. Do not
silently substitute a model; a changed effective model forms a separate cohort.

The prompt is frozen in `evaluation/config/baseline_prompt.v0.1.txt`. A minimal
output envelope may be used for scoring but must not reproduce the engine's
criteria or gates.

## Run-selection rule

Record three baseline runs per confirmatory case where practical. The
confirmatory paired result is **the lowest numbered successful valid run**. A
failed or structurally invalid run remains recorded; it is skipped only for the
predeclared validity reason. No semantic-quality judgement may influence run
selection. Remaining valid runs are variability evidence only.

If no run is valid, record baseline failure for that case. Never regenerate
until a favourable result appears and never select the best-looking run.

One format-only repair is allowed only if it is fixed before confirmatory runs,
contains no policy guidance, and is applied identically to every malformed
response. The original and repair attempt must both remain in the run record.

