# Phase 9A-0c — Case C selection and freeze record

Status: **SELECTED AND FROZEN — NOT YET RUN**
Version: v0.1
Date: 2026-08-17
Governing protocol: `docs/phase9a-0c-observation-plan-v0.1.md` §3, §3.1, §3.2, §5
Sourcing basis: `docs/observations/9a-0c/case-c-sourcing-candidates.v0.2.md`

Nothing in this record executes the observation. No Phase 3 run, no provider call, no assessment engine, no review or approval flow, no recommendation. No production code, policy, prompt, schema, taxonomy or threshold was changed.

---

## 1. Selected document

| Field | Value |
|---|---|
| Title | Standard Operating Procedure: Recruitment and Selection |
| Organisation | New River Community and Technical College (public, West Virginia) |
| Source URL | `https://www.newriver.edu/wp-content/uploads/2025/09/SOP-HR-Recruitment-and-Selection-Procedures-Final.pdf` |
| Captured to | `docs/observations/9a-0c/case-c/newriver-recruitment-selection-sop.pdf` |
| Capture date (UTC) | 2026-08-17T13:53:42Z |
| File size | 266,591 bytes |
| SHA-256 | `2a8fba60b7264fb38dd6cd3e0308f6673245beffd47e82d855c423bb333a5f3f` |
| Format | PDF 1.6, valid `%PDF` header |
| Effective / revised | 1 March 2024 / 8 September 2025 |

---

## 2. Selection rationale

The final comparison was between two candidates only. The pool was frozen before this comparison; no further candidates were drawn.

- **Both New River and Plymouth passed the substantive C1–C10 screening.** Each satisfies every mandatory item.
- **Plymouth was not rejected for process quality, richness, topical fit, or expected criterion yield.** On C2 and C4 it is the stronger process document: a dedicated Key Duties section and four named exception paths with resolution routes.
- **Plymouth was not selected because a meaningful portion of its workflow is carried in screenshots that Phase 2 cannot read.** Its text layer is genuine and clean, but the substantive content of several pages sits in images introduced by lines such as *"This screen shows that the quantity ordered matches the quantity invoiced (billed):"*. A fact that exists only inside an image is neither `STATED_BUT_UNCITABLE` nor `NOT_STATED` — it falls outside the pre-registered classification entirely and would confound the primary deliverable of 9A-0c.
- **New River is selected because its operational information is available in the text layer**, giving a cleaner instrument for the evidence-reachability observation. Its own extraction hazard is tokenisation noise rather than informational loss: characters are present, only word spaces are lost.

Selection rests on document format and information-carrying medium. It does not rest on which document appears more likely to evidence criterion values, in either direction.

### 2.1 Recognised tension

Preferring a document whose information is wholly in the text layer may bias mildly toward criteria being evidenceable. The confound introduced by unreadable screenshots was judged the larger threat to the measurement. This tension was recognised and decided, not overlooked.

---

## 3. C1–C10 result

| # | Item | Result | Measured basis |
|---|---|---|---|
| C1 | ≥4 named activities | **PASS** | Five numbered steps with lettered sub-activities: request to fill (ERF); hiring manager and committee identified; candidate approval; offer of employment; onboarding |
| C2 | Actors/roles | **PASS** | Hiring Manager, Divisional VP, HR Director, Controller, CFO/VP Finance-Administration, Director of Grants, President or designee, hiring committee |
| C3 | Inputs/outputs | **PASS** | In: Employment Request Form, Additional Advertisement Request Form, application materials, interview score sheets. Out: requisition and job posting, offer letter, candidate disposition emails, onboarding plan |
| C4 | Decision/branch/exception | **PASS** | DocuSign denial-and-resubmit on incorrect funding; President approval/denial; candidate not approved or withdraws → reconsider or repost; Extra Help, Adjunct and Work Study exempt from the committee step; DVP may add an interview or accept the recommendation |
| C5 | Operational constraint | **PASS** | ERFs valid 90 days; postings open a minimum of 10 days; at least three voting committee members; 6-month introductory period with an HR meeting two weeks before it ends |
| C6 | Current state | **PASS** | Revised 8 September 2025, marked Final; describes current operation |
| C7 | Text-native, no OCR | **PASS** | 4 pages, 8,536 raw extracted characters, mean 2,134 chars/page via `PdfReader(strict=False)` + `page.extract_text()` — the same calls Phase 2 uses |
| C8 | Chunking envelope | **PASS** | Exact; see §4 |
| C9 | Confidentiality | **PASS** | See §5 |
| C10 | Redaction | **Not required** | See §5 |

---

## 4. C8 — exact, computed with the project's own logic

Measured by `ingest_pdf_bytes` followed by `plan_chunks` under `config/extraction.v0.1.json`. Both are pure functions; nothing was persisted, no workspace was created and no provider was contacted. This was a pre-run format characterisation, not execution of the observation.

| Field | Value |
|---|---|
| `ingestion_status` | `success` |
| `ingestion_issues` | none |
| `document_id` | `doc-2a8fba60b7264fb38dd6cd3e0308f6673245beffd47e82d855c423bb333a5f3f` |
| `canonical_text_chars` | 8,369 |
| `total_blocks` | 31 |
| `non_empty_blocks` | 31 |
| Limits applied | `max_characters=40000`, `max_non_empty_blocks=30`, `overlap_blocks=1` |
| **Chunks planned** | **2** |

| Chunk | Chars | Blocks | Slices | Previous | Next |
|---|---|---|---|---|---|
| 1 | 7,811 | 30 | 30 | no | yes |
| 2 | 697 | 2 | 2 | yes | no |

**Structural note.** The document exceeds the 30 non-empty-block limit by exactly one block. The split is driven by the block limit, not the character limit — 8,369 canonical characters sit far inside the 40,000 ceiling. The result is a 697-character tail chunk carrying two blocks, one of which is the configured overlap. Case C will therefore exercise the multi-chunk path and cross-chunk merge. Recorded as a property of the document, with no expectation attached to it.

---

## 5. C9 / C10 review

Automated scan over the extracted text:

| Pattern | Count |
|---|---|
| email address | 0 |
| telephone number | 0 |
| URL | 0 |
| UNC path | 0 |
| SSN-like | 0 |
| titled personal name | 0 |

Manual read confirms role titles only — Hiring Manager, HR Director, Controller, CFO, President or designee — with no named individuals, no personal data and no commercially sensitive content. The document is a published procedure of a public college.

**C9 PASS. C10 not required.** No redaction applied, none needed.

---

## 6. Known limitations recorded before the run

**6.1 Word-space / tokenisation noise — qualitative, not quantified.** Extraction collapses spaces between words. Observed examples, verbatim: `isreceived`, `HumanResources`, `willselect`, `individualsto`, `Grantsif`, `departmentsthat`, `ofinterviewers`, `notestaken`, `candidatesin`, `isfilled`, `willsubmit`, `Interviewsfor`, `thisstep`.

Characters are correct and no OCR substitution is present, so C7 is unaffected. Several collisions occur inside role names and verbs, which is where extraction looks for actors and activities, so this may bear on which blocks resolve as evidence.

A heuristic regex returned zero matches. **That zero is a property of the pattern, not of the document** — `\b[a-z]{2,}[A-Z][a-z]{2,}\b` cannot match a leading-capital collision such as `HumanResources`, nor an all-lowercase one such as `isreceived`. No reliable count exists and none is asserted. The limitation stands as qualitative until independently quantified by a sounder method.

**6.2 Sourcing-pool top-up deviation, and the selected document's place in it.** The sourcing memo declared a stopping rule of six candidates; eight were drawn. Three of the first six never reached content assessment, failing on document format or unit-of-document, leaving the pool too thin. The top-up repaired pool size, not pool outcome, and every candidate drawn is reported. Disclosed rather than absorbed, at `case-c-sourcing-candidates.v0.2.md` §1.1.

**The selected document is one of the two top-up candidates.** The original six were Cornell, Gloucestershire, Salisbury, EPA, Vanuatu and Edinburgh. New River and ASUN were added in the top-up. Under the pre-registered six-candidate stopping rule, New River would not have been drawn.

The following are all true and are recorded together:

- the top-up deviation was already disclosed in the sourcing memo before selection;
- all eight candidates drawn are reported, including the three rejected;
- New River was selected on content-independent grounds — document format and information-carrying medium, not expected criterion yield;
- this deviation does not by itself invalidate the observation, provided it remains disclosed and no further candidate-search or selection occurs.

It remains a protocol caveat and must stay visible. It is stated here so that an auditor need not diff the two sourcing memos to discover it. Identifying which candidates entered via the top-up requires `case-c-sourcing-candidates.v0.1.md`, which is retained in the repository for that purpose; `v0.2.md` discloses that a top-up occurred but does not name the two candidates added.

**6.3 Incidental exposure.** Verifying C1–C6 required reading both finalists end to end, so exposure to whatever they state about volumes, timings and controls was unavoidable. This is a property of the checklist, not a failure to follow it. No criterion was scored for either candidate during selection, and the capability taxonomy was not consulted.

**6.4 Domain concentration.** The sourcing memo's top five contained two US community-college HR documents. The pool was less domain-diverse than its length suggests.

---

## 7. Separate product finding — not acted on

A large class of real-world SOPs are screenshot-driven system work instructions in which substantive process content lives in images. The product cannot read them: Phase 2 supports text-native PDF, plain text and raw text, with no OCR and no image interpretation. The Plymouth SOP is a concrete instance.

This is a genuine capability gap surfaced by Case C sourcing. It is recorded as a finding only. **Nothing is fixed, redesigned or scoped in response during 9A-0c**, per observation plan §8. Plymouth would make a suitable deliberate test case for that gap later; that is a different measurement.

---

## 8. Frozen baseline at selection

| Item | Value |
|---|---|
| Repository HEAD at selection | `29bda1159235acbdf19b3c6a30e28622d492b996` (`29bda11`, observation plan) |
| Production baseline commit | `de34e07` (Fix 0) |
| Production subtree fingerprint | `3c5c86bd132d25745ee7fcba2e40c3e3d796a9ff404a36a93aecce60cbaf1a85` |
| Decision policy | `decision_policy.v0.2`, version `0.2.0` |
| Extraction configuration | `extraction.v0.1`, model `gpt-5.6-terra` |

The repository HEAD and the production baseline are distinct. `29bda11` is the commit at which Case C was selected and carries the observation plan; `de34e07` is the last commit to touch production code and is the baseline the fingerprint describes. Commits between them changed documentation only.

The fingerprint must be re-verified as `3c5c86bd…` immediately before the run, per observation plan §2.

---

## 9. Status

Case C is **selected and frozen**. Not ingested, not run.

Remaining before execution, per observation plan §5 and §10: the pre-registered prediction must be committed (`case-c-prediction.v0.1.json`), and separate explicit approval obtained for the live provider call.
