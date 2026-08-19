# PORT-004 Stage 2 observation record

- Case ID: PORT-004
- Organisation: United States Patent and Trademark Office (USPTO)
- Process: patent examiner prior-art search workflow
- Stage: 2 (Phase 4 human review only)
- Record date: 2026-08-19
- Checkpoint status: **READY FOR APPROVAL / DELIBERATELY UNAPPROVED**

This record is factual and observational. It describes a completed Phase 4 human review that satisfies the product's approval boundary and has deliberately **not** been approved. Nothing in `production-run-v0.1/` was modified to produce it, and the Stage 2 `workspace.db` was opened read-only for every verification reported here.

## 1. Execution identity

| Field | Value |
|---|---|
| Git commit executed from | `f3fdd657c0705d4ffcf63f8d5355b263baef4c98` |
| Commit subject | `docs: implement PORT-004 Stage 2 authorised review execution path` |
| Operator | `evaluation/portfolio/_run_port004_stage2_review.py` |
| Operator SHA-256 | `8712251774eeff7caaf94c31ff784fa266ad12f037e402c67cb6b228788b3522` |
| Operator mode | `--execute-authorised-review` |
| Production fingerprint (this run) | `3c5c86bd132d25745ee7fcba2e40c3e3d796a9ff404a36a93aecce60cbaf1a85` |
| Phase 8 portfolio baseline fingerprint | `4deca4251d4a9840d6948411544fdf506f1953c16a56eaca803099d2cf81be5a` |
| Action plan | v1.1 (accepted before execution) |

The operator carries a committed-operator gate: both persistent modes refuse to run unless the executing file is byte-identical to the version stored in HEAD. The execution record confirms `operator_matches_head: true`, with `operator_blob_in_head` and `operator_blob_working` both `f84096378c2cec5c5933cc74f56a2b8dd0493642`. This checkpoint is therefore attributable to an exact commit.

**Baseline drift.** As recorded for Stage 1, PORT-004 runs against the current production fingerprint rather than the Phase 8 portfolio baseline that PORT-001/002/003 used. This remains a recorded **portfolio-comparability limitation**, not a reverted baseline. No production file was changed for this run.

## 2. Review identity

| Field | Value |
|---|---|
| `assessment_id` | `assessment-088291801b5e4e208b0a1d6078aed1bc` |
| `review_id` | `review-8f199803fc07467e95dba9950d5ed399` |
| `REVIEW_SESSION` artefact ID | `artifact-ffc7fe4a9f6540eabd5683fcf50c550b` |
| Artefact revision | 1 |
| Artefact schema version | `phase4-v0.1` |
| Artefact `payload_sha256` | `0bd62671726c9a3f6cebfc3359b09a5bfcc0c2016bac6c7d158c80e4eb7af522` |
| Review created at | 2026-08-19T12:28:51.519608+00:00 |
| First review event | 2026-08-19T12:28:51.576981+00:00 |
| Last review event | 2026-08-19T12:29:00.046548+00:00 |

Only one `REVIEW_SESSION` revision exists. `save_review(replace_current_review=True)` replaces the active review artefact in place, so the 104 individual saves did not produce 104 revisions.

## 3. Review execution summary

**104 ReviewEvents**, matching the authorised plan exactly:

| ReviewAction | Count |
|---|---|
| `correct-dependency` | 2 |
| `resolve-conflict` | 4 |
| `accept` | 9 |
| `retain-unknown` | 88 |
| `accept-step-order` | 1 |
| **Total** | **104** |

The nine `accept` events are the process name plus the eight step activities.

### 3.1 Structure

All **8** extracted steps are retained. There was **no merge, no deletion, no reorder, no regrouping, and no activity rewrite**. The retained sequence is unchanged from Stage 1:

| Seq | `candidate_step_id` | Activity | Activity disposition |
|---|---|---|---|
| 1 | `candidate-step-8761540c3fb724d5` | identifying the field of search | accepted |
| 2 | `candidate-step-df4f0ee1970efb51` | selecting the proper tool(s) to perform the search | accepted |
| 3 | `candidate-step-55d273f0f007cf1f` | determining the appropriate search strategy for each search tool selected | accepted |
| 4 | `candidate-step-56dffd383d81b62b` | Prioritize areas to be searched | accepted |
| 5 | `candidate-step-77a07b30101d76fe` | Select search tools | accepted |
| 6 | `candidate-step-2d9417a14cf0f937` | Conduct Internet searching | accepted |
| 7 | `candidate-step-69b86f080884cb5a` | Document Internet search strategies | accepted |
| 8 | `candidate-step-a154c8ee145a50f9` | Conduct a careful and comprehensive search | accepted |

Step order was accepted as displayed (`order_accepted = True`). Every step carries `order_basis = source_position`, so this acceptance records **document/source order only**. It is not a claim that the eight activities execute in this sequence in practice.

The Stage 1 reading that steps 1–3 form an abstract planning framework which later steps elaborate remains **human interpretation only**. It was not applied to the step list, the order, the dependencies or any field.

### 3.2 The only content-changing human-review actions

Exactly two of the sixteen authorised actions changed stored content. Both populated a previously null dependency target:

1. **Step 2** (`candidate-step-df4f0ee1970efb51`, `dependencies[0]`, raw schematic label `step-1`) — target set to `candidate-step-8761540c3fb724d5` ("identifying the field of search").
2. **Step 3** (`candidate-step-55d273f0f007cf1f`, `dependencies[0]`, raw schematic label `step-2`) — target set to `candidate-step-df4f0ee1970efb51` ("selecting the proper tool(s) to perform the search").

Both corrections **reused existing trusted Phase 3 evidence and minted no new evidence**:

| Correction | Relationship evidence | Target-label evidence |
|---|---|---|
| Step 2 | `cev-08b516894d50a1d4d2b10386f2759f9d489b8d41eb72e34eaab6378ad802f8fb` | `cev-9f8a9e0432a9273d8b73d7853594521e6ce3112e704d8ea18d0d4d50c79b5b53` |
| Step 3 | `cev-92f08c226d88c620589d2bf13f1f6f5abef6196dee65054db4a205fd9fdc4002` | `cev-6dfb5b66fcf5e24500eb1febf2ecfb16dbc12c0bb7291d1bdcbaaf8ddb48f78a` |

Neither `relationship` value was altered; the raw schematic `target_label` values are preserved as extracted. The step 7 dependency (`Conduct Internet searching` → `candidate-step-2d9417a14cf0f937`) was already resolved by Phase 3 and was not touched.

## 4. Conflict outcomes

All four blocking conflicts are `resolved`. Live conflict IDs from the persisted review, in the order the product constructed them:

| Position | `conflict_id` | Code | Status |
|---|---|---|---|
| `conflicts[0]` | `conflict-633ee10af8eb41f6a6d6847987ea8692` | `snippet-not-found` | resolved |
| `conflicts[1]` | `conflict-b72c8905baef47fda7744ca75aee60a8` | `ambiguous-dependency` | resolved |
| `conflicts[2]` | `conflict-79d597606de24e8983c1609d470609e5` | `ambiguous-dependency` | resolved |
| `conflicts[3]` | `conflict-14bb52ffdfe541cc9a5bae43837aca22` | `process-field-conflict` | resolved |

### 4.1 `snippet-not-found` — `multiple_processes_detected`

The provider's snippet could not be resolved against block `t-b0032` of `chunk-0002`, so the assertion **failed closed to UNKNOWN**. The reviewer supplied no value.

- The field **remained UNKNOWN**.
- It was **NOT converted to FALSE**.
- The closure is **reviewed-and-acknowledged, not an adjudicated factual finding**.

The narrowed PORT-004 scope (MPEP Ninth Edition Rev. 10.2019, §§904–904.03, pages 900-40 to 900-46, corrected at `841d066`) is a **scoping decision**. It is not evidence that the wider source contains no additional process, and this record makes no such claim.

### 4.2 and 4.3 The two `ambiguous-dependency` conflicts

Neither conflict object stores a `field_path`, `chunk_id` or `block_id`, so they are not distinguishable by field content. Attribution rests on **deterministic construction order**, verified against the frozen artefact before execution and again against the persisted session:

`extraction/merge.py` emits one `ambiguous-dependency` issue per unresolvable dependency while iterating retained steps in ascending final sequence (the sort by `_earliest_position` precedes that loop). The frozen candidate contains exactly two unresolvable dependencies, on steps 2 and 3 in that order, stored at `issues[1]` and `issues[2]`. `ProcessReviewService.start_review()` builds conflicts with an order-preserving comprehension over `result.issues`.

- `conflicts[1]` → **Step 2** dependency, corrected target `candidate-step-8761540c3fb724d5`.
- `conflicts[2]` → **Step 3** dependency, corrected target `candidate-step-df4f0ee1970efb51`.

This is a positional correspondence, not a stored identifier. It is deterministic and reproducible, not a reviewer convention, and both closures state the basis explicitly. Both dependencies were corrected in the same session. The positional mapping was verified before execution and again against the persisted review, so the two closures are attributable as recorded.

### 4.4 `process-field-conflict` — `process_name`

The retained value `"How to Search"` was accepted, not rewritten.

- The retained value is **independently document-supported** by existing evidence `cev-6915c0b9d0439cd7bce10948efcf7471e95ab05d6b8f4adf025cc1abe7f65b42`, exact snippet `904 How to Search [R-10.2019]` at `lines 15-47` — the MPEP §904 section heading, quoted verbatim.
- The competing chunk-0002 value was **not persisted** by the Phase 3 first-supported-wins process-field merge and was therefore unavailable at review time. **No two-way adjudication is claimed.**
- No process-name rewrite occurred. `process_name` remains `origin = DOCUMENT_SUPPORTED`.

The non-observability of superseded process-field values is recorded as a limitation of the current merge.

The two non-blocking `process-field-conflict` issues on `process_description` and `process_objective` produced no `ReviewConflict` object, are not part of the approval boundary, and required no action. None was taken.

## 5. UNKNOWN discipline

| Field group | Count | State |
|---|---|---|
| Material criteria (10 × 8 steps) | 80 | UNKNOWN, `disposition = unknown-retained` |
| `human_accountability_required` (× 8 steps) | 8 | UNKNOWN, `disposition = unknown-retained` |
| **Total explicitly reviewed** | **88** | all via `retain_unknown` |

- **No `HUMAN_SUPPLIED` values** were introduced anywhere in the review (verified: 0 assertions carry that origin).
- **No `DOCUMENT_SUPPORTED` criterion or accountability values** were added.
- **No capability-signal Phase 4 edits** (0 capability-signal assertions have a disposition other than `unreviewed`). The two Phase 3 `known` signals on step 1 are untouched, and the current UI does not expose an evidence-choice route for capability signals — recorded as an observed product limitation, not worked around.
- **Zero newly minted evidence references.** The persisted review carries exactly the 71 evidence identifiers present in the frozen candidate; the set difference is empty.

**What `retain_unknown` does and does not do.** It changes `disposition` from `unreviewed` to `unknown-retained` and records a `ReviewEvent` carrying the reviewer's per-field rationale. It changes **no value**: `approval._criterion` and `_boolean_data` both map an assertion with `value is None` to `value=None, knowledge_state=UNKNOWN` regardless of disposition, so the projected values are identical whether or not the retention was recorded. The 88 retentions therefore record reviewer consideration and nothing else. That distinction is the point: `unreviewed` means nobody looked; `unknown-retained` means a human looked and declined to invent a value.

Each of the 88 rationales is field-specific — composed from why that criterion type cannot be read off a procedural manual plus what that step's own evidence pool actually contains — not one generic string repeated.

Step 7's `human_accountability_required` was retained UNKNOWN despite `cev-e0c26d1568f9443a1413` ("must document their search strategies"), on the recorded ground that the corpus evidences a present human duty rather than the future-model accountability classification this Boolean carries.

## 6. Progress semantics — documentation clarification

Observed progress:

| Point | `total_required` | `completed_required` | `remaining_required` | `is_ready` |
|---|---|---|---|---|
| Initial | 16 | 0 | 16 | False |
| Final | 10 | 10 | 0 | True |

**This is expected behaviour, not a product defect.** From `presentation/review_progress.build_review_progress`:

- **Base requirements = 10**, fixed by the reviewed shape: process identity (1), step order (1), activity confirmation (× 8 retained steps).
- **Initial dynamic requirements = 6**: `invalid-retained-dependency` × 2 and `unresolved-structural-conflict` × 4.
- `dynamic_required` is recomputed from the live `approval_errors(session)` on every call, not held as a stored checklist. A dynamic requirement exists only while the defect that generates it exists.
- Once the two dependency targets were populated and the four conflicts closed, those six codes stopped being emitted, so they **left the denominator** rather than moving into the numerator: `total = 10 + 0`, `completed = max(0, 10 − 0) = 10`.

The progress projection is therefore an **outstanding-work meter, not a cumulative 16-item completion ledger**, and `16/16` was never a reachable display state. Proof that the complete authorised review occurred is the **104-event ledger** in §3, together with the dispositions recorded in §3.1, §4 and §5.

This is recorded as a **documentation clarification to action plan v1.1**, which described sixteen approval requirements in a way that implied a fixed denominator. The count of authorised *actions* was correct; the implied progress-widget behaviour was not.

## 7. Ready-but-unapproved boundary

| Check | Value |
|---|---|
| `approval_errors(session)` | `[]` |
| `build_review_progress(session).is_ready` | `True` |
| Review status | `in-review` |
| Workflow stage | `in-review` |

Explicitly recorded:

- **No `APPROVED_REVIEW` artefact persisted.** The Stage 2 workspace holds exactly three artefact types: `INGESTION_RESULT`, `CANDIDATE_EXTRACTION_RESULT`, `REVIEW_SESSION`.
- **No validated `BusinessProcess` persisted or passed into integrated assessment.**
- **No `AssessmentEngine` execution.** Recorded operations are `ingest` (completed) and `extract` (completed) only — no approve, assess or package operation was ever started.
- **No integrated assessment result.**
- **No decision package result.**
- **No recommendation output** of any kind.

The operator installed a runtime guard making `AssessmentWorkspaceService.approve`, `.assess` and `.generate_package` raise, and never called `approve_review` itself.

**Technical nuance, preserved deliberately.** `presentation.review_progress.approval_errors` — which `build_review_progress` calls internally — evaluates readiness by invoking the product's real `approve_review` and reading its `.errors`. Because `ApprovalResult` validates that exactly one of `approved` / `errors` is populated, a session that *is* ready causes `approve_review` to construct an in-memory `ApprovedProcessReview`, including a projected `BusinessProcess`, before returning. That object is discarded immediately. It was **not persisted and was not passed into assessment**, the session itself is untouched (`approve_review` deep-copies before mutating its snapshot), and no `APPROVED_REVIEW` artefact exists. This is the product's own side-effect-free readiness path — the review UI exercises it on every render — and it was not modified for PORT-004.

## 8. AFTER boundary

**No PORT-004 AFTER evidence was collected, opened or used in Phase 4 review.** At this checkpoint, no PORT-004 AFTER artefact existed in this repository. No PORT-001/002/003 AFTER material was accessed during Stage 2. This record contains no AFTER-derived statement of any kind.

## 9. Frozen hashes at this checkpoint

| Artefact | SHA-256 |
|---|---|
| Stage 2 `production-run-v0.2-review/workspace.db` | `0fc81b4a14f2336dc672148fcd91a77db86fb92ac518144cf4ace1718ef82612` |
| Stage 2 `production-run-v0.2-review/stage2-execution-record.v0.1.json` | `1c33e51a56ea4482d77ab930cccb5319dccaea92e1d1e4541301ba52505ef51b` |
| `REVIEW_SESSION` payload | `0bd62671726c9a3f6cebfc3359b09a5bfcc0c2016bac6c7d158c80e4eb7af522` |
| Frozen Stage 1 `candidate_extraction.json` | `ffbefc0eef7ad68b90859576d60aa0c09606c1eb6fd267d4fe2dca13b2c8ad65` |
| Frozen Stage 1 `ingestion_result.json` | `caaeb9534c827202fac910ba715e88ff93086dccfd9f637fb0919f364438eb58` |
| Frozen Stage 1 `run_state_after_extraction.json` | `1f346ee7bf5911ad4e1e3e23fc57cf08962ed0dd54934a5246eb0b9d564f9a19` |
| Frozen Stage 1 `workspace.db` | `f4a5c97503ec9a7f3c989fec8a2d5048f0678f2994e9b93e52802af55d2ac49f` |
| Corrected BEFORE corpus | `98fd4ecece92f0bec27664241013677af1bd67e15816d3f8ba2291b23e017c01` |
| Production fingerprint | `3c5c86bd132d25745ee7fcba2e40c3e3d796a9ff404a36a93aecce60cbaf1a85` |
| Operator `_run_port004_stage2_review.py` | `8712251774eeff7caaf94c31ff784fa266ad12f037e402c67cb6b228788b3522` |

All four frozen Stage 1 artefacts were hash-verified before execution and again after execution, and were re-verified read-only when this record was written. All four are unchanged. The frozen Stage 1 `workspace.db` was never opened as a database at any point in Stage 2; it was copied byte-for-byte and verified as raw bytes only.

## 10. Execution-record completeness

`stage2-execution-record.v0.1.json` was independently audited against the persisted database. Every field it carries is accurate. Four items are absent from it and are recorded here instead, rather than by editing an artefact now treated as immutable:

1. The `REVIEW_SESSION` artefact identity `artifact-ffc7fe4a9f6540eabd5683fcf50c550b` and its `payload_sha256` (§2).
2. The explicit absence of `INTEGRATED_ASSESSMENT_RESULT` and `DECISION_PACKAGE_RESULT`, which the record only implies through `approved_review_present: false` (§7).
3. Confirmation that the pure in-memory Phase 4 preflight and the post-persistence verification both passed before any review action was applied.
4. Its own SHA-256, which cannot appear inside itself and is carried in `port-004.run-hashes.sha256`.

Consistent with the project convention established by `_run_port004_stage1.py`, the execution record carries no injected wall-clock field; the product's own review timestamps are recorded instead (§2), which keeps the file reproducible from the workspace.

## 11. Checkpoint boundary

Phase 4 human review is complete and satisfies the product's approval boundary. The review is **deliberately left unapproved** pending an explicit, separately authorised human approval decision.

Not performed, and not authorised by this checkpoint: `approve_review(...)`, `APPROVED_REVIEW` creation, validated `BusinessProcess` projection into assessment, deterministic assessment, recommendation generation, decision-package generation, and any collection or inspection of PORT-004 AFTER evidence.
