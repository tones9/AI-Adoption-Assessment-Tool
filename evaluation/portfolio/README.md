# Phase 8 portfolio validation

This directory contains the isolated three-case retrospective portfolio validation of the completed AI Adoption Engine. It is separate from the earlier six-case confirmatory/reviewer infrastructure, which remains preserved under `evaluation/cases/confirmatory/` and `evaluation/protocol/`.

The experimental sequence is:

1. Freeze the neutral, anonymised BEFORE process document.
2. Seal the separate AFTER reference packet.
3. Run the unchanged Phase 1–7 production pipeline with the BEFORE document as its only case input.
4. Complete source-bounded human review and explicit approval.
5. Freeze all production outputs and lineage records.
6. Only then unseal AFTER evidence for retrospective comparison.

`product_inputs/` is the only case-data directory permitted as production input. Production extraction must never receive a provenance manifest, source capture, leakage audit, case register, or file under `sealed_after/`.

The frozen production baseline is commit `c201cbbde33fd18a72c9dd0ca0106a1c754f31c7`. Exact configuration and production-subtree fingerprints are recorded in `freeze_manifest.v0.1.json`.

The portfolio cases are:

- `PORT-001`: anonymised claims-document intake and recording.
- `PORT-002`: anonymised customer-call routing and handling.
- `PORT-003`: anonymised client-meeting documentation and follow-up planning.

BMW is historical evaluation material only and is not part of this portfolio.

Source captures in this directory are claim-level research records with public locators and faithful paraphrases. They do not reproduce complete copyrighted pages. Source and outcome claims remain subject to the limitations recorded in each provenance manifest.
