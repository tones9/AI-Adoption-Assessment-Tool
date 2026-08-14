# Case Selection and Separation Protocol v0.1

Identifier: `phase8-case-selection.v0.1`

## Eligibility

A confirmatory case must:

1. describe one identifiable current-state business process;
2. support at least three reference activities;
3. use a verifiable public source or explicitly permitted private source;
4. permit before-state content to be separated from later intervention content;
5. contain enough evidence for source-backed reference annotation;
6. avoid unnecessary personal or confidential information;
7. add useful domain, document, risk, or capability diversity; and
8. have stable source metadata and hashable case files.

Vendor-authored and anonymized cases may be included, but their evidence
quality and publication bias must be recorded and stratified in reporting.

## Case packet

Each case contains a manifest plus `before/`, `after/`, and `reference/`
directories. The input document in `before/` must not contain after-state
technology, outcomes, or recommendations. The after packet is sealed until
both engine and baseline recommendations are frozen.

The case manifest records the SHA-256 digest of every frozen before and after
file. Hash changes invalidate existing run manifests.

## Contamination controls

- Development and confirmatory cases are physically separated.
- Confirmatory cases cannot be used to revise production methodology.
- After packets cannot be loaded by before-state harness operations.
- No evaluated provider call may use tools or web access.
- The baseline and engine receive the same eligible before-state information in
  the decision-isolated comparison.
- The confirmatory baseline run is selected by rule, never by observed quality.
- Public-model memorization risk is recorded as low, medium, or high.

## Exclusion log

Every excluded candidate records the reason and decision date in
`evaluation/artifacts/case_selection_log.csv`. A case may not be removed merely
because its evaluation result is poor.

