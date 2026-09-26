# AI Adoption Decision Engine — Project Context

Status: **CANONICAL**  
Last reconciled: **2026-09-05**

## Purpose

Build an evidence-traceable decision-support product that helps a business decide whether a specific activity should change, whether it is ready for intervention, which intervention is appropriate, and how much AI autonomy is safe.

The product must not manufacture an AI use case. A sound result may recommend no change, AI automation, AI-assisted work, a conventional solution, process improvement, continued human leadership, or more discovery.

## Product boundary

The product starts with one documented business process and assesses its activities. It supports intake, document ingestion, candidate extraction, human review and approval, deterministic assessment, a decision package, and controlled follow-up where evidence is insufficient.

It ends at the adoption decision. It does not implement, pilot, deploy, operate, or measure the realised outcomes of an AI system. Those activities belong to a future Adoption Execution Layer.

## Core principles

1. Start with the activity, not the technology.
2. Separate language extraction from deterministic decision logic.
3. Preserve `unknown`; never turn missing evidence into an assumption.
4. Require human review and explicit approval before assessment.
5. Trace material claims and decisions to evidence.
6. Treat non-AI and no-change outcomes as valid.
7. Treat **Discovery Required — insufficient evidence for the active decision** as a first-class result, not an error.
8. Keep policy thresholds and weights versioned, transparent, and explicitly provisional until validated.

## Current and target states

- **Current product:** Portfolio Version 1, implemented in Python/Streamlit with `decision_policy.v0.2`. Its coded decision flow is evidence sufficiency → technical fit → business value → risk and autonomy, and its recommendation enum has four modes.
- **Target product direction:** the approved successor four-gate contract in [01_FRAMEWORK_SPEC.md](01_FRAMEWORK_SPEC.md), with `docs/four-gate-migration-design-v0.2.md` as its detailed design authority. Its explicitly invoked Slice 1 domain, Phase 5/6 contracts, persistence adapters, presentation projections, and narrowly scoped `grw-m2-four-gate-v0.1` lifecycle through successor DCW are implemented and verified. The target is not integrated with default selection; all other successor reassessment paths remain unavailable.

Never describe the target framework as shipped behavior until [03_CURRENT_STATE.md](03_CURRENT_STATE.md) records the migration as implemented and verified.

## Agreed delivery sequence

- Git tag `v1.0.0` at commit `052a445` remains the historical Portfolio V1 baseline.
- The locally committed Validate Process usability redesign is a separate pending release decision. It must not be folded into, or used to relabel, the four-gate successor.
- The four-gate migration contract in `docs/four-gate-migration-design-v0.2.md` is approved. Its explicitly invoked, non-default Slice 1 was verified on 2026-09-04; successor Phase 5/6, persistence, presentation, DCW discrimination, the narrow same-contract GRW/M2 lifecycle, and a synthetic-only evaluation-cohort harness were verified by 2026-09-06. Governed real-world cohort cases, a broader successor reassessment path, and full product migration each need separate authorization.
- Later framework slices require separate authorisation and verification. Remaining reliability and productisation work can then resume in priority order. Authentication, tenancy, hosted commercialisation, and the Adoption Execution Layer remain future work, not approved implementation scope.

## One source-of-truth system

Planning, framework/design documentation, and canonical-memory updates happen in ChatGPT Project chats. Codex implements and verifies production code in this repository. Chats are working conversations, not durable authority.

Use this compact spine:

| File | Question answered |
|---|---|
| `00_PROJECT_CONTEXT.md` | What is the product and what must remain true? |
| `01_FRAMEWORK_SPEC.md` | What is the target four-gate framework? |
| `02_DECISIONS.md` | What has been decided, deferred, or superseded? |
| `03_CURRENT_STATE.md` | What is actually implemented and what is active now? |
| `04_CODEX_HANDOFF.md` | How should Codex work, verify, and continue? |

Authority is resolved as follows:

1. The user's current explicit instruction.
2. Adopted decisions in `02_DECISIONS.md`.
3. Product intent and target behavior in `00_PROJECT_CONTEXT.md` and `01_FRAMEWORK_SPEC.md`.
4. Implemented state in `03_CURRENT_STATE.md`, verified against code, configuration, tests, and Git.
5. Historical specifications, plans, research, decks, and binary documents.

If intent and implementation differ, record both. Do not silently rewrite one to resemble the other.

## Context budget

For a normal task, read only `00_PROJECT_CONTEXT.md`, `03_CURRENT_STATE.md`, `04_CODEX_HANDOFF.md`, Git status, and the directly relevant files. Read `01_FRAMEWORK_SPEC.md` and `02_DECISIONS.md` when the task affects the framework, policy, outcomes, schemas, or product direction. Open historical material only to resolve a named ambiguity.

## Durable update rule

- New product or framework decision → update `02_DECISIONS.md` first, then affected canonical files.
- Implemented or verified state changes → update `03_CURRENT_STATE.md`.
- Immediate execution priority changes → update `04_CODEX_HANDOFF.md`.
- Stable purpose or boundary changes → update `00_PROJECT_CONTEXT.md`.
- Framework semantics change → update `01_FRAMEWORK_SPEC.md` and version the decision policy when implemented.

Do not paste full chat histories into the repository. Compress decisions and evidence into these files.

`05_BUILD_JOURNAL.md` is a user-facing historical record. It is not part of the Codex reading set or implementation authority.

For new decision-ready design documents in `docs/`, also create a companion named `NTT-<technical-file-name>` in plain language. The technical document remains the implementation authority; its NTT companion is for user review and does not add or change requirements.
