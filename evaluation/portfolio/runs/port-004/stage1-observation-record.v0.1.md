# PORT-004 Stage 1 observation record

- Case ID: PORT-004
- Stage: 1 (Phase 2 ingestion + Phase 3 candidate extraction only)
- Record date: 2026-08-18
- Status: **STAGE 1 COMPLETE — NOT YET FROZEN FOR COMMIT** (see instruction boundary at the end of this record)

This record is factual and observational. It does not alter, re-run, re-interpret in the code sense, or supplement the extraction. Nothing in `candidate_extraction.json`, `ingestion_result.json`, `run_state_after_extraction.json` or `workspace.db` was modified to produce it.

## 1. Frozen preconditions

| Field | Value |
|---|---|
| Corrected BEFORE corpus SHA-256 | `98fd4ecece92f0bec27664241013677af1bd67e15816d3f8ba2291b23e017c01` |
| Corpus revision | 2 (revision 1, commit `e24e495`, superseded — two-column interleaving; corrected in commit `841d066`) |
| Source PDF SHA-256 | `a74b4a685afea1976d6e4b035e11ac14aa8850d97dbb006ec14eca9ba2ec29e7` |
| Production fingerprint (this run) | `3c5c86bd132d25745ee7fcba2e40c3e3d796a9ff404a36a93aecce60cbaf1a85` |
| Phase 8 portfolio baseline fingerprint | `4deca4251d4a9840d6948411544fdf506f1953c16a56eaca803099d2cf81be5a` |

**Baseline drift.** PORT-001, PORT-002 and PORT-003 ran against the Phase 8 portfolio baseline fingerprint above. PORT-004 runs against the current production fingerprint instead, by operator decision recorded in `_run_port004_stage1.py`. Production code has moved on since the Phase 8 freeze (most recently the Case C review-UI provenance fix, commit `de34e07`) and reverting it was out of scope. This is recorded here as a **portfolio-comparability limitation** — PORT-004 is not running under bit-identical production code to the cases it will be compared against in the portfolio narrative. It is not a reverted baseline, and no production file was changed to produce this run.

## 2. Execution summary

| Field | Value |
|---|---|
| `extraction_status` | `partial` |
| `extraction_run_id` | `extraction-e55a1dc6-8394-48ad-a8a2-7f0dafc3fe34` |
| `candidate_status` | `CANDIDATE / UNCONFIRMED PROCESS EXTRACTION` |
| Ingestion status | `success` |
| Blocks | 56 |
| Canonical text | 22,830 characters |
| Deterministic chunk count | **2** (matches `EXPECTED_CHUNK_COUNT` pinned in the operator script) |
| Chunk-0001 | 13,458 characters, 30 blocks |
| Chunk-0002 | 9,273 characters, 27 blocks |
| Logical provider calls | **3** (within the descriptive range [2, 4] for 2 chunks with `repair_attempts=1`; this range was never used as a hard gate) |

### Provider-call chronology

| # | chunk_id | attempt | input tokens | output tokens | request_id |
|---|---|---|---|---|---|
| 1 | chunk-0001 | 1 | 6,751 | 8,411 | `resp_062eb6eb1312c9ce016a84aad81d90819f889b5f8945cf6dc9` |
| 2 | chunk-0002 | 1 | 5,625 | 9,347 | `resp_0fc07ad82aec400b016a84ab1927c487d2b18d53691ea93cc5` |
| 3 | chunk-0002 | 2 (repair) | 5,647 | 10,296 | `resp_0b2f8378b7e29f1b016a84ab5f18d087d2a7719b962410da51` |

**Chunk-0002 required one repair attempt; chunk-0001 did not.** The repair was triggered by an evidence-resolution failure on chunk-0002's first attempt (see `snippet-not-found` below); the repair call did not fully resolve it, and the affected field was correctly discarded rather than passed through unverified.

## 3. Artefact hashes (this run)

| File | SHA-256 |
|---|---|
| `production-run-v0.1/candidate_extraction.json` | `ffbefc0eef7ad68b90859576d60aa0c09606c1eb6fd267d4fe2dca13b2c8ad65` |
| `production-run-v0.1/ingestion_result.json` | `caaeb9534c827202fac910ba715e88ff93086dccfd9f637fb0919f364438eb58` |
| `production-run-v0.1/run_state_after_extraction.json` | `1f346ee7bf5911ad4e1e3e23fc57cf08962ed0dd54934a5246eb0b9d564f9a19` |
| `production-run-v0.1/workspace.db` | `f4a5c97503ec9a7f3c989fec8a2d5048f0678f2994e9b93e52802af55d2ac49f` |

The `workspace.db` SQLite store contains exactly two artefact rows (`INGESTION_RESULT`, `CANDIDATE_EXTRACTION_RESULT`). The stored `payload_json` for `CANDIDATE_EXTRACTION_RESULT` is byte-identical to `candidate_extraction.json` and its own recorded `payload_sha256` matches. No third, pre-merge, per-chunk artefact is persisted anywhere in this run.

## 4. Persisted document order vs. global sequence

Every candidate step carries two distinct order fields, and they diverge. This is recorded explicitly because reading `document_order` alone, out of context, would be misleading.

| Final `sequence` (global, persisted) | Activity | `document_order.value` | `document_order.knowledge_state` | `order_basis` | Source block |
|---|---|---|---|---|---|
| 1 | identifying the field of search | 1 | known | source_position | t-b0018 (chunk-0001) |
| 2 | selecting the proper tool(s) to perform the search | 2 | known | source_position | t-b0018 |
| 3 | determining the appropriate search strategy for each search tool selected | 3 | known | source_position | t-b0018 |
| 4 | Prioritize areas to be searched | **1** | inferred | source_position | t-b0031 (chunk-0002) |
| 5 | Select search tools | **2** | inferred | source_position | t-b0032 |
| 6 | Conduct Internet searching | **3** | inferred | source_position | t-b0040 |
| 7 | Document Internet search strategies | **4** | inferred | source_position | t-b0044 |
| 8 | Conduct a careful and comprehensive search | **5** | inferred | source_position | t-b0050 |

`document_order.value` resets to 1 at the start of chunk-0002, because each chunk was extracted independently with no visibility of the other chunk's numbering. Read in isolation, step 4's `document_order = 1` could be misread as the document's first activity.

**The final global `sequence` (1–8) is correct despite this reset.** `extraction/merge.py` only trusts `document_order` as authoritative (`OrderBasis.EXPLICIT`) when every retained step's `document_order.knowledge_state` is `known` and the values are unique across the whole candidate. Here only 3 of 8 steps qualify as `known` (the ones with explicit "(A)/(B)/(C)" labels in the source); the remaining 5 are `inferred`. Because not all steps qualify, the merge falls back entirely to `_earliest_position` — the true document character offset (`document_start_offset`) — to sort every step, and every step is stamped `order_basis: "source_position"`. The underlying offsets (6535 → 6572 → 6632 → 13627 → 13885 → 14407 → 18606 → 19058) are strictly increasing and match the persisted `sequence` field exactly. The chunk-relative `document_order` field is the artefact that could mislead a reader; the merge outcome itself is not affected by it.

## 5. Issue interpretation

Six issues were recorded: 1 `snippet-not-found`, 2 `ambiguous-dependency`, 3 `process-field-conflict`. No `duplicate-step-merged`, `possible-duplicate-step`, `ordering-conflict`, `self-dependency` or `multiple-processes-detected` issue was raised.

**`snippet-not-found`** (error; field `multiple_processes_detected`; chunk-0002; block `t-b0032`). The provider's cited quotation for this field could not be located verbatim in the source block. Per `extraction/evidence.py::resolve_assertion`, any assertion with an unresolvable evidence pointer is unconditionally demoted to `value=None, knowledge_state=UNKNOWN, evidence=[]` — a fail-closed mechanism, not a soft warning. Consequence: `multiple_processes_detected` for chunk-0002 is **UNKNOWN, not FALSE**. Because it is unknown, it is excluded from the check in `merge_chunks` that would otherwise raise a `multiple-processes-detected` warning. The absence of that warning in the final six issues does not mean chunk-0002 found no evidence of a second process — it means that specific claim was discarded as unverifiable. This is an open coverage gap for Phase 4, not a confirmed negative.

**`ambiguous-dependency` × 2**. Step 2's dependency ("selecting the proper tool(s)...") declares `target_label.value = "step-1"`; step 3's dependency declares `target_label.value = "step-2"`. `extraction/merge.py`'s dependency resolver matches `target_label` only by normalised literal text against the final steps' activity values, with no mechanism to resolve schematic placeholders such as `"step-1"`/`"step-2"`. Neither string is a substring match of any step's actual activity text, so both resolve to zero matches and `target_candidate_step_id: null`. The `relationship` field and rationale text attached to each dependency ("Having determined the field of search..." / "The selected search tools are the objects for which strategies are determined") make the intended targets legible to a human reader — step 2's dependency appears to be on step 1, step 3's on step 2 — but this record does not resolve them. **They are left unresolved for Phase 4 review**, as the persisted data requires.

**`process-field-conflict` × 3** (`process_name`, `process_description`, `process_objective`). Chunk-0001 and chunk-0002 each proposed values for these three process-level fields, and the proposals differed. `extraction/merge.py::_select_process_assertion` retains the **first supported assertion** among the chunks (chunk-0001's, given chunk processing order) and discards the other, logging only that a conflict occurred — not what the discarded value was. The `workspace.db` SQLite store was inspected directly and confirmed to hold no separate pre-merge, per-chunk record. **Chunk-0002's alternative values for these three fields are not persisted anywhere in this run and are unrecoverable from it.** The values retained in the merged candidate are: `process_name = "How to Search"`, `process_objective = "conduct a thorough search of the prior art"`, and a synthesised `process_description` (confidence 0.95, knowledge_state `inferred`).

## 6. Observation — HUMAN INTERPRETATION, not a system finding

The following is this record's own reading of the extracted content. It is not produced by, or flagged by, any issue code in the production pipeline, and should be weighted accordingly at Phase 4.

Steps 1–3 (chunk-0001) state the document's abstract three-step planning framework verbatim from §904.02's opening: identify the field of search, select tools, determine strategy. Steps 4–8 (chunk-0002), drawn from the more granular subsections that follow (§§904.02(a)–904.03), largely appear to **elaborate or refine that same three-step framework** rather than represent five additional, independent sequential activities that simply come after it. For example: step 4 ("Prioritize areas to be searched") reads as part of step 1's field-of-search activity; step 5 ("Select search tools") restates step 2 at a more concrete level; step 8 ("Conduct a careful and comprehensive search") reads as the execution of the plan set out in steps 1–3, rather than an eighth step following step 7. The chunk boundary falls close to the abstract/concrete divide in the source text. This observation does not indicate a factual contradiction in the extracted data, and the character-offset ordering underlying `sequence` is not affected by it — it is a note about how the eight steps should be read together, offered for Phase 4's benefit.

## 7. What has and has not happened

The following are stated explicitly and factually, not as recommendations:

- No Phase 4 review has occurred.
- No approval has occurred.
- No assessment has occurred.
- No recommendation has been generated.
- No decision package has been generated.
- No PORT-004 AFTER evidence has been collected or accessed.

## 8. Instruction boundary for this record

This record was produced under an explicit instruction not to modify `candidate_extraction.json`, `ingestion_result.json`, `run_state_after_extraction.json`, `workspace.db`, production code, prompts, schemas, taxonomy, policy or thresholds, and not to run Phase 4, assessment, recommendations, or access/collect AFTER evidence. None of those actions were taken to produce this record.
