# PORT-004 pre-reveal protocol

Status: **PRE-REVEAL STAGE COMPLETE — AFTER PACKET SEALED, NOT OPENED FOR COMPARISON**  
Version: v0.1  
Date: 2026-08-20  
Case: United States Patent and Trademark Office patent examiner prior-art search workflow

## 1. Scope and authority

This protocol records only the approved pre-reveal stage: neutral AFTER-source collection, claim-level source capture, packet sealing, and integrity verification. It does not compare the AFTER material with any frozen product output.

No production code, policy, prompt, taxonomy, schema, Stage 1–5 artefact, or product database is changed by this stage. No extraction, review, approval, assessment, or package operation is run.

The sealed AFTER packet must not be opened for comparison until a separately explicit authorisation is given.

## 2. Frozen product preconditions

| Item | Value |
|---|---|
| HEAD before collection | `a8118c3c5f9b0d431635ea59702159501715bb0c` |
| HEAD subject | `docs: freeze PORT-004 Stage 5 decision package` |
| Current Stage 1–5 hash manifest | `runs/port-004/port-004.run-hashes.sha256` |
| Current hash-manifest SHA-256 | `5bba8177f25ccfb77aea6a4849af175b8916ebe6b6fcdecc02d38422118e9594` |
| Frozen BEFORE corpus SHA-256 | `98fd4ecece92f0bec27664241013677af1bd67e15816d3f8ba2291b23e017c01` |
| Stage 5 package-record SHA-256 | `f987e4dd7e849977342cbf85e4816fa5bfcdc33406d65332e88eabf1e40a4507` |
| Production fingerprint | `3c5c86bd132d25745ee7fcba2e40c3e3d796a9ff404a36a93aecce60cbaf1a85` |
| Decision Package artefact | `artifact-7d8a9331af1449fea8c5ea905ace1a3b` |
| Decision Package payload SHA-256 | `4c717926f4fd21bd1cecfbd6516553d63be3470e383de2a1a28388a136938862` |

Immediately before source collection, all seventeen entries in the Stage 1–5 manifest verified successfully. The packet is therefore downstream research material, not an input to the product run.

## 3. Neutral source-selection method

The collection question was fixed before source review:

> What later, real USPTO interventions affected patent-examiner prior-art search in the workflow bounded by the frozen BEFORE corpus?

The neutral search queries were:

1. `site:uspto.gov patent examiner prior-art search artificial intelligence`
2. `site:uspto.gov patent examiners AI prior art search`
3. `site:uspto.gov "prior art search" "machine learning" patent examiner`
4. `site:uspto.gov "AI for PE2E" patent examiners`

They did not include any frozen product capability, recommendation, step ID, recommendation mode, or information-gap term. In particular, they did not use `DOCUMENT_INFORMATION_EXTRACTION`, `KNOWLEDGE_RETRIEVAL`, `classification`, `automation`, `AUGMENT`, `INVESTIGATE_FURTHER`, or any product-output wording as a search criterion.

Sources qualified only if they were public, later than the frozen BEFORE corpus, and directly described an operational or officially documented AI-assisted intervention in utility-patent examiner prior-art searching. Generic USPTO AI activity, applicant-only pre-examination pilots, public search tools, design-patent-only tools, and non-AI related-art initiatives were excluded from the packet.

## 4. Qualifying source set

| Source ID | Role in sealed packet | Qualification |
|---|---|---|
| `PORT-004-S2` | Contemporaneous official implementation/recordation context | A USPTO Official Gazette notice dated 2022-12-27 describes AI search capabilities being integrated into PE2E Search for patent examiners conducting prior-art searches and the required search-record notation. |
| `PORT-004-S3` | Official uptake/use context | A USPTO Director's Blog post dated 2024-12-09 reports regular examiner use of PE2E AI search features and an aggregate query count since September 2022. |
| `PORT-004-S4` | Direct later intervention description | A USPTO news item dated 2025-08-14 states that utility patent examiners began conducting prior-art searches with SimSearch in September 2022, describes its operation, and states that examiner discretion is retained. |
| `PORT-004-S5` | Independent advisory corroboration and control context | The 2023 Patent Public Advisory Committee annual report states that AI search capabilities in the examiner search tool assist in finding potential prior art and cautions that examiner judgement remains necessary. |

`PORT-004-S4` is the direct evidence that a later intervention operated in the bounded workflow. The other sources corroborate timing, use, recordation, or the retained human-search boundary. None is treated as an independent outcome evaluation.

## 5. Excluded material and source-selection ambiguity

The neutral search returned several related but out-of-scope materials. They are excluded rather than used to widen the case:

- an applicant-facing, pre-examination AI search pilot, because it is not the examiner's prior-art-search workflow;
- design-patent image-search material, because it concerns a different examination population and modality;
- a relevant-prior-art initiative focused on automatically providing existing citations and search reports, because it is not the documented AI-assisted search intervention; and
- public patent-search tools, because public search access is not evidence of the examiner-side intervention.

The qualifying sources describe related AI search features at different dates and levels of detail. The packet preserves that variation: it does not merge their usage statements, infer a single performance figure, or treat a policy/advisory statement as a deployment outcome.

## 6. Exposure disclosure

The curator conducting this stage opened the qualifying AFTER sources while collecting them and therefore cannot claim blindness to PORT-004 AFTER evidence in any later comparison.

The Stage 1–5 records establish that no PORT-004 AFTER packet or source was collected, opened, or supplied to the product pipeline during the frozen run. They do not establish individual reviewer blindness to all public information. No blindness claim will be made for the production reviewer or any later comparison author unless separately demonstrated.

The curator had access to the frozen product artifacts for integrity verification. The source search itself used only the neutral case/workflow question above, not output-shaped terms.

## 7. Reveal boundary

The AFTER packet becomes eligible for comparison only when all of the following hold:

1. the sealed packet, its source captures, manifest, seal record, and hash listing verify;
2. the Stage 1–5 run manifest still verifies unchanged;
3. the comparison author receives explicit authorisation to open the packet; and
4. the comparison records an `after_unseal_record` before writing any retrospective conclusion.

Until then, `sealed_after/port-004.after.md` is sealed research material. No comparison directory, theme classification, retrospective comparison, case study, or cross-case summary is created in this stage.
