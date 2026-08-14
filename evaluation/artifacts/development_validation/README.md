# Development-case harness validation

Validation identifier: `phase8-development-validation.v0.1`

The two controlled synthetic cases exercised both a perfect path and a known-
error path. All eight case packets passed SHA-256 verification, sealed-after
access was denied without a matching persisted freeze record, and the frozen
`decision_policy.v0.2` engine completed an offline five-step smoke assessment
covering all four recommendation modes.

The controlled error fixture produced the preregistered values in
`results.v0.1.json`. One test expectation for Kendall's tau-b was initially
signed incorrectly; manual pair counting established +1/3, and only the Phase
8 test expectation was corrected. This is an evaluation-fixture defect, not a
Phase 1-7 defect.

These are harness-validation results only. They are not performance evidence,
were produced with zero API calls, and make no confirmatory claim.
