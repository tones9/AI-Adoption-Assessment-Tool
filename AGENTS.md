# AI Adoption Decision Engine — Codex Instructions

## Start here

For a new or ambiguous task, read, in order:

1. `00_PROJECT_CONTEXT.md`
2. `03_CURRENT_STATE.md`
3. `04_CODEX_HANDOFF.md`

For a continuing, tightly scoped implementation slice whose prompt names the governing contract, read only `03_CURRENT_STATE.md`, `04_CODEX_HANDOFF.md`, the directly relevant code/tests, and the cited section(s) of the governing contract. Read `00_PROJECT_CONTEXT.md`, `01_FRAMEWORK_SPEC.md`, or `02_DECISIONS.md` only when the prompt, current state, or handoff exposes a material ambiguity or a cross-boundary conflict.

Do not reread all canonical, historical, or evaluation documents for every task. Load the smallest set that resolves the task safely.

Do not read `05_BUILD_JOURNAL.md` for implementation work. It is a user-facing historical record, not an implementation authority.

## Authority and truth

- Canonical intent: `00_PROJECT_CONTEXT.md`, `01_FRAMEWORK_SPEC.md`, `02_DECISIONS.md`.
- Implemented truth: current code, versioned configuration, tests, and Git; summarized in `03_CURRENT_STATE.md`.
- Immediate execution: `04_CODEX_HANDOFF.md`.
- Older Word/PDF documents, plans, decks, archives, and chat transcripts are supporting or historical material.

The four-gate framework is the adopted target, not current shipped behavior. Do not modify production behavior merely to make it match the target without an approved migration task.

## Working method

Before changing files:

1. Check branch, HEAD, Git status, and relevant diffs.
2. Preserve unrelated and uncommitted user work.
3. Inspect only files and tests directly relevant to the task.
4. State any material conflict between canonical intent and current implementation.

Verify with targeted checks first. Expand to boundary tests or the full suite only for cross-cutting changes or material ambiguity.

## Protected boundaries

For the four-gate framework work, preserve the existing system architecture, UI/UX rules, evidence model, auditability, persistence, and established product behaviour. Treat changes outside the decision framework as out of scope unless they are strictly required by the approved migration contract.

Do not silently change:

- deterministic decision behavior;
- `decision_policy.v0.2`;
- recommendation modes, schemas, taxonomy, or persistence contracts;
- frozen evaluation artifacts or recorded historical outputs;
- the product boundary at the adoption decision.

Changes to these areas require an explicit task, a versioned compatibility plan, and tests. Never replace deterministic decisions with unconstrained LLM judgement. Preserve unknowns, evidence lineage, human approval, and baseline immutability.

Do not commit unless the user explicitly asks.

## Keep project memory current

- New decision → update `02_DECISIONS.md`.
- Verified implementation state → update `03_CURRENT_STATE.md`.
- New immediate task → update `04_CODEX_HANDOFF.md`.
- Stable purpose/boundary → update `00_PROJECT_CONTEXT.md`.
- Framework semantics → update `01_FRAMEWORK_SPEC.md` and version implementation artifacts when authorized.

Be concise. Distinguish verified facts, assumptions, and recommendations.

## Automatic “Update the Brain” protocol

Codex owns project-memory maintenance. Do not ask the user to copy or issue a separate **“Update the Brain”** command. Automatically update the relevant canonical project-memory files after verified work materially changes a contract, release state, policy, schema, persistence boundary, test scope, or immediate execution handoff, and after the user approves a durable product or design decision:

- durable decisions → `02_DECISIONS.md`;
- verified implementation or release state → `03_CURRENT_STATE.md`;
- agreed execution order or next task → `04_CODEX_HANDOFF.md`;
- stable purpose, boundary, or roadmap → `00_PROJECT_CONTEXT.md`;
- target framework semantics → `01_FRAMEWORK_SPEC.md`.

Update only what is verified or explicitly agreed. A pasted completion report may be recorded after it is consistent with the current repository state; do not promote an unverified claim or an unapproved proposal to canonical fact. Preserve unrelated work, and never commit, push, or change application behavior unless separately requested.

Perform the memory update in the same turn as the qualifying completion or approval, before handing off the next task. Do not return a Brain-update prompt for the user to relay. After each automatic update, give a short summary with **Updated** and **Next task**. The phrase **“Update the Brain”** remains a valid manual request but is no longer required.
