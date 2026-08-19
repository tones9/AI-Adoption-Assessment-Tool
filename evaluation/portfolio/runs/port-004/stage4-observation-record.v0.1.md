# PORT-004 Stage 4 observation record

- Case ID: PORT-004
- Organisation: United States Patent and Trademark Office (USPTO)
- Process: patent examiner prior-art search workflow
- Stage: 4 (Phase 5 deterministic assessment only)
- Record date: 2026-08-19
- Checkpoint status: **ASSESSMENT COMPLETE / NO DECISION PACKAGE GENERATED**

This record is factual and observational. It describes a completed deterministic assessment run against the frozen, approved PORT-004 review. Nothing in `production-run-v0.1/`, `production-run-v0.2-review/` or `production-run-v0.3-approved/` was modified to produce it, and the Stage 4 database was opened read-only for every verification reported here.

## 1. Execution identity

| Field | Value |
|---|---|
| Git commit executed from | `84b7772cb6539bffa192befef46f087fa5f48fa6` |
| Commit subject | `docs: add PORT-004 Stage 4 assessment operator` |
| Operator | `evaluation/portfolio/_run_port004_stage4_assessment.py` |
| Operator SHA-256 | `353fb280a8a0504d02640e8dae2913d2138a46b1c3582fff207decde11eaeb53` |
| Operator mode | `--confirm-run-assessment` |
| Operator blob in HEAD | `9c8ee85616d4fd25245ac912bb5bc8aa0b3a5f7e` |
| Operator blob executed | `9c8ee85616d4fd25245ac912bb5bc8aa0b3a5f7e` |
| `operator_matches_head` | `true` |
| Production fingerprint (this run) | `3c5c86bd132d25745ee7fcba2e40c3e3d796a9ff404a36a93aecce60cbaf1a85` |
| Phase 8 portfolio baseline fingerprint | `4deca4251d4a9840d6948411544fdf506f1953c16a56eaca803099d2cf81be5a` |

The committed-operator gate held: both persistent Stage 4 modes refuse unless the executing file is byte-identical to the version stored in HEAD, and the two blob identifiers above are equal. This checkpoint is therefore attributable to an exact commit.

**Baseline drift.** As recorded for Stages 1 to 3, PORT-004 runs against the current production fingerprint rather than the Phase 8 portfolio baseline used by PORT-001/002/003. This remains a recorded **portfolio-comparability limitation**, not a reverted baseline. No production file was changed for this run.

**Operator independence.** The Stage 4 operator imports no private production symbol. Its readiness checks are operator-owned; the authoritative approval-artefact and projection-consistency validation runs inside the product's own assessment pipeline.

## 2. Stage 3 frozen approval lineage

The assessment was run against a byte-for-byte copy of the frozen Stage 3 approved database. The Stage 3 checkpoint itself was not opened as a database and was not modified.

| Frozen Stage 3 artefact | SHA-256 |
|---|---|
| `production-run-v0.3-approved/workspace.db` | `09b4399987814a32b9bc48b01bcd246daee319180ae4d6a2d208932d0ca33e46` |
| `production-run-v0.3-approved/stage3-approval-record.v0.1.json` | `3cab058cbdf590ab73e45031a9921fd081ea85bfee44fc0dd71c51c97cb4fe7e` |
| `stage3-observation-record.v0.1.md` | `341bf6c083e64e9264d96e0256b08b4bcb6c97f0bcd76ff24f1c1588dff44a1b` |

Lineage chain: frozen Stage 1 candidate → frozen Stage 2 ready-but-unapproved review → frozen Stage 3 `APPROVED_REVIEW` → Stage 4 assessment. Each stage was copied rather than mutated, so every earlier checkpoint remains inspectable at its committed hash.

## 3. Assessment identity

| Field | Value |
|---|---|
| `assessment_id` | `assessment-088291801b5e4e208b0a1d6078aed1bc` |
| `review_id` | `review-8f199803fc07467e95dba9950d5ed399` |
| `APPROVED_REVIEW` artefact ID | `artifact-5d7e6631ce3042e1871e19a9d8d39010` |
| `APPROVED_REVIEW` payload SHA-256 | `c886848bba58ab762410e950083a497977b579157eeba6ac08728aee5368f960` |
| `INTEGRATED_ASSESSMENT_RESULT` artefact ID | `artifact-61ee88e2be40437598864e7f634b2243` |
| `INTEGRATED_ASSESSMENT_RESULT` payload SHA-256 | `eedf5c3a70b0144987d1d7af5fc4ccbdafd5895f0baddd6555b398724700820b` |
| Artefact revision | 1 |
| Parent artefact | `artifact-5d7e6631ce3042e1871e19a9d8d39010` (the `APPROVED_REVIEW`) |
| `assessment_run_id` | `assessment-485eee54ece54f46aba333b6e72e4307` |
| `assessed_at` | 2026-08-19T14:38:30.168538+00:00 |
| Integration schema version | `phase5-v0.1` |
| Phase 1 contract version | `phase1-v0.3` |

## 4. Decision policy

| Field | Value |
|---|---|
| `policy_id` | `decision_policy.v0.2` |
| `policy_version` | `0.2.0` |
| `policy_status` | `PROVISIONAL — NOT YET ACADEMICALLY VALIDATED` |
| `decision_policy_fingerprint` | `b72e528b102bf893b45e6de9ec311e0888341d12b8aa3f99b8047e324d6a6d66` |

The policy status is carried through unchanged from the configuration. It is recorded here because every recommendation mode below is qualified by it.

## 5. Result and workflow state

The integrated assessment returned **`IntegratedAssessmentSuccess`**. That means the *integration* completed and the result is well-formed; it is not a statement that any step was recommended for adoption.

| Check | Value |
|---|---|
| Result type | `IntegratedAssessmentSuccess` |
| Workflow stage | `assessed` |
| `APPROVED_REVIEW` payload SHA | unchanged (`c886848b…5368f960`) |
| Standalone `REVIEW_SESSION` payload SHA | unchanged (`0bd62671…7af522`) |
| Standalone `REVIEW_SESSION` status | `in-review` |
| `assess` operation | recorded and `completed` |
| `generate_package` operation | absent |
| `DECISION_PACKAGE_RESULT` | absent |
| Recorded operations | `assess`, `extract`, `ingest` |

As recorded at the Stage 3 checkpoint, the standalone `REVIEW_SESSION` artefact still reads `in-review` by design: `approve_review` snapshots the session rather than mutating it, and the approved snapshot lives inside the `APPROVED_REVIEW` artefact. Assessment reads the `APPROVED_REVIEW` and touches neither.

## 6. Step assessments

Eight step assessments were produced, one per retained process step, in sequence order.

| Seq | `step_id` | Recommendation mode | Priority | Priority status | Capabilities |
|---|---|---|---|---|---|
| 1 | `candidate-step-8761540c3fb724d5` | INVESTIGATE_FURTHER | none | `not_applicable` | `DOCUMENT_INFORMATION_EXTRACTION`, `KNOWLEDGE_RETRIEVAL` |
| 2 | `candidate-step-df4f0ee1970efb51` | INVESTIGATE_FURTHER | none | `not_applicable` | none |
| 3 | `candidate-step-55d273f0f007cf1f` | INVESTIGATE_FURTHER | none | `not_applicable` | none |
| 4 | `candidate-step-56dffd383d81b62b` | INVESTIGATE_FURTHER | none | `not_applicable` | none |
| 5 | `candidate-step-77a07b30101d76fe` | INVESTIGATE_FURTHER | none | `not_applicable` | none |
| 6 | `candidate-step-2d9417a14cf0f937` | INVESTIGATE_FURTHER | none | `not_applicable` | none |
| 7 | `candidate-step-69b86f080884cb5a` | INVESTIGATE_FURTHER | none | `not_applicable` | none |
| 8 | `candidate-step-a154c8ee145a50f9` | INVESTIGATE_FURTHER | none | `not_applicable` | none |

**All eight steps: `INVESTIGATE_FURTHER`, with `priority_status = not_applicable`.** No priority score was computed for any step, because `INVESTIGATE_FURTHER` is not among the policy's eligible recommendations for scoring (`AUTOMATE`, `AUGMENT`).

All eight steps share an identical gate pattern:

| Gate | Status | Rationale |
|---|---|---|
| `evidence_sufficiency` | passed | *"The activity is source-backed. Criterion sufficiency is evaluated only when a criterion becomes material to the current gate."* |
| `technical_fit` | failed | *"Material evidence is insufficient: ai_capability_fit is unknown."* |
| `business_value` | not_evaluated | *"Not evaluated because an earlier gate determined the outcome."* |
| `risk_and_autonomy` | not_evaluated | *"Not evaluated because an earlier gate determined the outcome."* |

The determining condition is uniform: each step's activity is source-backed, so evidence sufficiency passes, and each step then fails technical fit because `ai_capability_fit` is UNKNOWN. The two later gates are short-circuited once the outcome is determined.

**This is the expected consequence of the Phase 4 UNKNOWN discipline, not a defect.** MPEP §§904–904.03 is a procedural instruction manual; it states no 0–5 adoption-suitability rating, so Phase 3 returned UNKNOWN for every material criterion and Phase 4 explicitly retained those UNKNOWNs rather than inventing values. A deterministic policy that requires material criteria before recommending adoption must therefore answer "investigate further" — that is the policy behaving correctly on honest inputs, and it is the reportable portfolio finding for this case.

**No expected outcome was asserted anywhere in the operator.** Every Stage 4 gate is an integrity gate; the recommendation modes, gate statuses and priority values above were recorded exactly as the engine produced them, with no comparison to any expectation.

## 7. Data integrity across assessment

| Check | Value |
|---|---|
| Material criteria still UNKNOWN | **80** |
| `human_accountability_required` still UNKNOWN | **8** |
| `HUMAN_SUPPLIED` assertions | **0** |
| Evidence references outside the frozen candidate | **0** |
| Step assessments | 8, one per process step, in order |

Assessment introduced no value, no origin change and no evidence. Every evidence identifier appearing in the assessment result is present in the frozen Stage 1 candidate.

### Capability observations

Capability signals are not recomputed by assessment. `map_capabilities` is a pure lookup that emits a capability only where a signal's value is literally `True`.

- **Step 1** carries the two Phase 3 `known = true` signals — `reads_unstructured_documents` and `searches_reference_knowledge` — which map to `DOCUMENT_INFORMATION_EXTRACTION` and `KNOWLEDGE_RETRIEVAL`.
- **Steps 2–8** carry no `true` signal, so no capability is emitted for them.

This is a derivation from the frozen review, not an inference: the underlying signals are unchanged, and the derived capabilities did not affect any gate outcome, since every step was determined by the UNKNOWN `ai_capability_fit` criterion.

## 8. AFTER boundary

**No PORT-004 AFTER evidence was collected, opened or used in Stage 4.** At this checkpoint, no PORT-004 AFTER artefact existed in this repository. No PORT-001/002/003 AFTER material was accessed. This record contains no AFTER-derived statement of any kind.

## 9. Hashes at this checkpoint

| Artefact | SHA-256 |
|---|---|
| Stage 4 `production-run-v0.4-assessed/workspace.db` | `9c144be8b2ca2d8fa3f0cf88a6d4ea4e344371afc13fc856a4a52bc94148cce3` |
| Stage 4 `production-run-v0.4-assessed/stage4-assessment-record.v0.1.json` | `42f399ac5bc0c8f86ff9dcda58b9c5c2cd5af2240a284606eedd94e6cd4df32e` |
| `INTEGRATED_ASSESSMENT_RESULT` payload | `eedf5c3a70b0144987d1d7af5fc4ccbdafd5895f0baddd6555b398724700820b` |
| `APPROVED_REVIEW` payload | `c886848bba58ab762410e950083a497977b579157eeba6ac08728aee5368f960` |
| `REVIEW_SESSION` payload | `0bd62671726c9a3f6cebfc3359b09a5bfcc0c2016bac6c7d158c80e4eb7af522` |
| Frozen Stage 3 `workspace.db` | `09b4399987814a32b9bc48b01bcd246daee319180ae4d6a2d208932d0ca33e46` |
| Frozen Stage 2 `workspace.db` | `0fc81b4a14f2336dc672148fcd91a77db86fb92ac518144cf4ace1718ef82612` |
| Frozen Stage 1 `candidate_extraction.json` | `ffbefc0eef7ad68b90859576d60aa0c09606c1eb6fd267d4fe2dca13b2c8ad65` |
| Frozen Stage 1 `ingestion_result.json` | `caaeb9534c827202fac910ba715e88ff93086dccfd9f637fb0919f364438eb58` |
| Frozen Stage 1 `run_state_after_extraction.json` | `1f346ee7bf5911ad4e1e3e23fc57cf08962ed0dd54934a5246eb0b9d564f9a19` |
| Frozen Stage 1 `workspace.db` | `f4a5c97503ec9a7f3c989fec8a2d5048f0678f2994e9b93e52802af55d2ac49f` |
| Corrected BEFORE corpus | `98fd4ecece92f0bec27664241013677af1bd67e15816d3f8ba2291b23e017c01` |
| Production fingerprint | `3c5c86bd132d25745ee7fcba2e40c3e3d796a9ff404a36a93aecce60cbaf1a85` |
| Stage 4 operator | `353fb280a8a0504d02640e8dae2913d2138a46b1c3582fff207decde11eaeb53` |

All eleven frozen Stage 1, Stage 2 and Stage 3 artefacts were hash-verified before the assessment and again after it, and are unchanged. The run manifest was verified at `4462b37f2832123db34b075cfefba96ac22766130bdcc4790506e3c923653597` and was not modified by the Stage 4 run; it does not yet carry the Stage 4 entries.

## 10. Checkpoint boundary

Phase 5 deterministic assessment is complete and persisted. Nothing downstream of it was produced.

Not performed, and not authorised by this checkpoint: `generate_package(...)`, `DECISION_PACKAGE_RESULT` creation, recommendation or executive-report authoring, roadmap or governance output, implementation planning, any re-run of assessment, and any collection or inspection of PORT-004 AFTER evidence.

**No decision package, recommendation document, implementation output or AFTER evidence was generated or accessed.**
