# Phase 8 Research-Evaluation Protocol v0.1

Protocol identifier: `phase8-evaluation-protocol.v0.1`

Status: **FROZEN FOR DEVELOPMENT-CASE VALIDATION**

## Purpose

Evaluate the frozen Phase 1-7 AI Adoption Engine honestly across an approved
reduced corpus. Phase 8 is not a development or tuning phase. Negative and
mixed findings are valid research results.

## Frozen system

Confirmatory evaluation uses Git commit
`4f2ba07b30f108f4b78ee5c7dc9ab42bb7956cf9`, policy
`decision_policy.v0.2`, extraction configuration `extraction.v0.1`, prompt
`process-extraction.v0.1`, and candidate schema `candidate-process.v0.1`.

No Phase 1-7 prompt, policy, model, schema, threshold, gate, weight, or
methodology may be changed in response to development or confirmatory cases.
Evaluation-tool defects may be corrected with versioned tests and an audit
entry. A suspected production defect must be reported before any change.

## Research questions

1. **RQ1 - Extraction:** How accurately does the live Phase 3 provider recover
   activities, order, attributes, evidence, and knowledge states from current-
   state documents?
2. **RQ2 - Decision methodology:** Given an adjudicated current-state process,
   how closely does the frozen deterministic engine align with independent
   reference judgements?
3. **RQ3 - Baseline:** Does the structured approach produce safer and more
   accurate recommendations than one unconstrained LLM-only baseline supplied
   with the same before-state information?
4. **RQ4 - End to end:** How reliably does the complete workflow produce a
   traceable decision package, and how much review effort does it require?
5. **RQ5 - Repeatability:** How much does live extraction vary across identical
   calls for activities, evidence, and known/inferred/unknown classifications?
6. **RQ6 - Reference interventions:** Does the engine identify opportunities
   substantively related to later documented interventions, treating those
   interventions as non-exhaustive reference evidence rather than ground truth?

## Corpus

- Two development cases, excluded from confirmatory claims.
- Six confirmatory cases initially.
- Extension to eight only before confirmatory execution, and only when readily
  available cases improve evidence quality or diversity without delaying the
  study.
- The bundled synthetic demo is never used for confirmatory claims.

Evidence quality, before/after separability, and domain diversity take
precedence over sample size.

## Mandatory studies

### A. Extraction evaluation

Compare unreviewed Phase 3 candidates with frozen reference annotations. Human
corrections are excluded from extraction metrics.

### B. Decision-isolated evaluation

Feed adjudicated `BusinessProcess` representations directly into the frozen
engine. Compare engine output with independent decision references and the
frozen unconstrained LLM baseline using identical before-state information.

### C. End-to-end evaluation

Execute: raw before document -> live extraction -> human review -> explicit
approval -> deterministic assessment -> decision package. Reviewers must not
see after packets or downstream recommendations before approval.

### D. Provider repeatability

Select approximately three confirmatory cases before results are known, based
on domain, length, and document complexity. Run three identical extractions per
selected case initially. Extra runs require a recorded justification.

## Optional work

External human-output evaluation, advanced statistical models, de-identified
sensitivity variants, more repetitions, and extension to eight cases are
optional and are not Phase 8 completion conditions.

## Completion

Phase 8 completes when the frozen system has been evaluated honestly across
the approved corpus, all four mandatory studies are complete, results and
errors are documented, before/after separation is demonstrable, and the result
bundle is reproducible. The hypothesis need not be supported.

