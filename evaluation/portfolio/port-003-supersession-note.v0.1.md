# PORT-003 supersession note

- Date: 2026-08-17
- Status of PORT-003 artefacts: **UNCHANGED, BYTE-IDENTICAL, RETAINED**
- Superseded by: PORT-004 (USPTO patent examiner prior-art search workflow)

## What happened

A source audit of the Morgan Stanley Wealth Management case was performed on 17 August 2026 against the required BEFORE-evidence criteria. The audit found:

- AFTER evidence is strong and multi-source: the Morgan Stanley launch announcement, the OpenAI case study, CNBC and InvestmentNews.
- No independent, pre-2024, Morgan Stanley-specific document describes the client-meeting note-taking, CRM and follow-up workflow.
- The only available description of the prior process exists **inside AFTER-dated sources**, framed as what the AI replaced.
- Next Best Action material (Forbes, May 2020) does not salvage the case: it covers a different process and that process was already machine-learning-driven from 2018.

Audit verdict: **REJECT AND FIND ALTERNATIVE.**

## Relationship to the existing frozen record

This finding does not contradict the frozen PORT-003 artefacts — it independently re-derives a limitation they already record. `leakage_audits/port-003.audit.json` states `residual_contamination_risk: "HIGH"`, and `provenance/port-003.manifest.json` records that "Strong AFTER documentation does not fully reconstruct the prior workflow" and that "publication bias and model-memorisation risk are high."

The 2026-08-15 freeze proceeded despite that risk. This note records the later decision that the risk is disqualifying for forward portfolio analysis.

## Effect

- PORT-003 remains in the repository exactly as frozen. No file was edited, renamed or deleted. `register.v0.1.json` and `hashes.sha256` are untouched.
- Commits `15ee707` (PORT-003 freeze), `72b24ce` (PORT-003 comparison) and `ad8351f` (three-case cross-case summary) remain valid records of what was done at the time.
- PORT-003 is marked `SUPERSEDED_CONTAMINATED_BEFORE` in `register.v0.2.json` and is excluded from forward portfolio analysis.
- PORT-004 takes the third-case position in the portfolio narrative.
- The existing `cross_case_summary.v0.1.md` and `.json` describe the PORT-001/002/003 portfolio and remain accurate for that composition. They have not been modified. A regenerated cross-case summary covering PORT-001, PORT-002 and PORT-004 is a separate step and has not been performed.

## Recorded as a successful exclusion

Both BMW and Morgan Stanley were excluded for insufficient independent BEFORE evidence. Both exclusions are treated as the validation discipline working as designed, not as project setbacks. The screening rule derived from them:

> Reject any candidate whose BEFORE process is only knowable from vendor case studies, press releases, or retrospective accounts of what the AI replaced. Require a source class authored for a non-AI reason — SOPs, operational manuals, audit or inspection reports, regulatory filings describing workflow.

PORT-004 was selected under this rule.
