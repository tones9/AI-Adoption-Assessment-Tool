# PORT-004 frozen corpus record

- Case ID: PORT-004
- Supersedes: PORT-003 (see `port-003-supersession-note.v0.1.md`)
- Freeze date: 2026-08-17
- Freeze status: **ACCEPTED FOR CASE 3 FREEZE**
- Scope of this record: frozen corpus only. No extraction, no assessment, no recommendations, no AFTER comparison.

## Selected BEFORE process

- Organisation: United States Patent and Trademark Office (USPTO)
- Process: Patent examiner prior-art search workflow
- Frozen source scope: MPEP Ninth Edition, Revision 10.2019 (June 2020 publication), Chapter 900

## 1. Source provenance

| Field | Value |
|---|---|
| Frozen filename | `source_documents/port-004-mpep-0900-e9r10-2019.pdf` |
| Original filename | `mpep-0900-e9r10-2019.pdf` |
| Source URL | https://www.uspto.gov/web/offices/pac/mpep/old/e9r10-2019/mpep-0900.pdf |
| Archive index URL | https://www.uspto.gov/web/offices/pac/mpep/old/mpep_E9R10-2019.htm |
| Independent date anchor | Federal Register, 10 July 2020 — Manual of Patent Examining Procedure, Ninth Edition, Revision of June 2020 |
| SHA-256 | `a74b4a685afea1976d6e4b035e11ac14aa8850d97dbb006ec14eca9ba2ec29e7` |
| File size | 1,885,991 bytes |
| Page count | 58 pages (printed labels 900-1 to 900-58, aligned 1:1) |
| Accessed / downloaded | 2026-08-17 |

### PDF metadata

| Field | Value |
|---|---|
| Format | PDF 1.4, not encrypted, no JavaScript, tagged |
| Title | MPEP - Chapter 0900 - Prior Art, Classification, and Search |
| Subject | MANUAL OF PATENT EXAMINING PROCEDURE |
| Author / Creator | United States Patent & Trademark Office |
| Producer | XEP 4.19 build 20110414 |
| CreationDate | 25 June 2020, 22:20:55 |
| ModDate | 26 June 2020, 20:21:59 |
| Page size | 576 x 792 pts |

The embedded creation timestamp independently corroborates the June 2020 publication label without relying on the archive index page.

### Section revision stamps

| Section | Stamp |
|---|---|
| 902 Search Tools and Classification Information | R-07.2015 |
| 903 Classification in USPC | R-07.2015 |
| 904 How to Search | **R-10.2019** |
| 904.01 Analysis of Claims | R-08.2012 |
| 904.01(a) Variant Embodiments Within Scope of Claim | R-08.2012 |
| 904.01(b) Equivalents | R-08.2012 |
| 904.01(c) Analogous Arts | R-08.2012 |
| 904.02 General Search Guidelines | R-07.2015 |
| 904.02(a) Classified Search | R-08.2017 |
| 904.02(b) Search Tool Selection | R-07.2015 |
| 904.02(c) Internet Searching | **R-10.2019** |
| 904.03 Conducting the Search | R-07.2015 |

Latest substantive revision anywhere in the § 904 family is R-10.2019, content current through October 2019.

## 2. BEFORE justification

**Operational document.** Chapter 900 is the working procedure manual governing how patent examiners conduct prior-art search. It instructs examiners and informs applicants of examination practice. It is not a retrospective description of a process written for an external audience, and not a vendor or press account.

**Authored before AI implementation.** Content current through October 2019; published June 2020. The AI-for-PE2E Official Gazette notice followed on 20 December 2021 and SimSearch entered examiner use in September 2022. The next MPEP revision forward, E9R-07.2022 (published February 2023), is post-implementation and was rejected as a BEFORE source for that reason.

**Created independently of AI adoption.** The manual has no relationship to any AI programme and makes no reference to one. Its publication date is verifiable in the Federal Register — a source outside the publishing organisation — and again in the PDF's own embedded creation timestamp. Nothing in the document was written to contrast a prior state against a later intervention. This is the property that PORT-001, PORT-002 and PORT-003 lacked.

**Contains activities, actors, inputs, outputs and decisions.** All five verified present in body text, not merely in the table of contents:

- *Activities* — § 904 search obligation and trigger, scope of the first search, inventor-name search, parent-application prior-art review, the rule that no second search is ordinarily required absent amendment, mandatory completion of the Image File Wrapper search notes form, and search-update recording. § 904.02 states the three planning steps verbatim: "(A) identifying the field of search; (B) selecting the proper tool(s) to perform the search; and (C) determining the appropriate search strategy for each search tool selected." § 904.03 sets the comprehensiveness standard and reference-selection practice.
- *Actors* — examiner, supervisory patent examiner, Technology Center art units, STIC and EIC search staff, Office of Patent Classification.
- *Inputs* — application, claims and disclosure; parent application file and its cited art; applicant Information Disclosure Statement; international search report and Form PCT/DO/EO/903; classification schedules and definitions.
- *Outputs* — identified references, Image File Wrapper search notes form with classification locations, sources and dates, first Office action on the merits, recorded search updates.
- *Decisions and exceptions* — whether any of the three mandatory reference sources may be eliminated and the reasonable-certainty justification required; field-of-search prioritisation; search tool choice based on coverage, strengths and weaknesses; whether a second search is necessitated; the § 904.02(b) decision-tree branches; which references qualify as "best."

## 3. AI separation

| Fact | Value |
|---|---|
| SimSearch entered examiner use | **September 2022** |
| AI-for-PE2E Official Gazette notice | **December 2021** |
| Frozen document content current through | October 2019 |
| Frozen document published | June 2020 |
| Margin to earliest AI event | 2 years 2 months |
| Margin to implementation | 2 years 3 months |

**The frozen document contains no AI-assisted search references.**

Scan across all 58 pages plus OCR of both full-page graphics (900-39 and 900-44), and separately across the frozen 20-page product input:

| Term | Hits |
|---|---|
| artificial intelligence | 0 |
| machine learning | 0 |
| neural | 0 |
| deep learning | 0 |
| predictive analytics | 0 |
| SimSearch | 0 |
| similarity search | 0 |
| AI (word boundary) | 0 |
| algorithm | 0 |

`automated` occurs 16 times. All 16 were inspected individually: each is either a proper product name — Examiner's Automated Search Tool (EAST), Web-based Examiner Search Tool (WEST), Foreign Patent Access System (FPAS) — or a generic reference to electronic full-text and Boolean retrieval. No occurrence implies inference, ranking, or model-based retrieval.

AFTER evidence has not been collected or sealed. That is a separate gated step and no AFTER material exists in this case directory.

## 4. Limitations

Preserved exactly as recorded at audit:

- § 904.02(b) decision tree exists as a graphic and is not visible to text-only ingestion.
- OCR recovery was audit-only and must NOT be added to engine input.
- MPEP is normative, not observational.
- Actual examiner behaviour/time constraints are not represented.

Additional limitations identified during freeze:

- Pages 900-34 to 900-40 inside the frozen page-contiguous range contain § 903.08 family and § 903.09 material — application assignment, inspection, transfer procedure and classification order administration — which lies outside the prior-art search workflow.
- Boundary spill is present and unedited: the closing text of § 901.08 (WIPO-CASE) appears at the top of 900-27, and the opening text of § 905 / § 905.01 (CPC hierarchy) appears at the foot of 900-46.
- The document cites USPTO intranet resources (Classification Home Page, Examiner Handbook to Classification, STIC NPL website) that are referenced but not reproduced. The public document therefore does not disclose the full internal procedure.

## 5. Engine suitability

| Field | Value |
|---|---|
| Recommended upload unit | §§ 902–904.03 only |
| Frozen product input | `product_inputs/port-004.before.txt` |
| Product input SHA-256 | `7bc9242a67e9400392c590e181db4ec7ca81880b44e4a903a5c71446467e492d` |
| Extraction range | physical pages 27–46 (printed 900-27 to 900-46) |
| Extraction command | `pdftotext -f 27 -l 46 -layout` |
| Size | 88,319 characters (1,049 lines, 10,449 words) |
| Estimated tokens | ~22,000 |
| Text extraction quality | **PASS** |

Text extraction quality basis: digital text layer throughout, no OCR required for body text; section numbering, revision stamps and page footers all survive extraction as reliable delimiters. The single extraction defect is the § 904.02(b) graphic, recorded under Limitations.

Input form: **verbatim primary-source extract**. No anonymisation, no paraphrase, no researcher inference, and no editorial trimming inside the frozen corpus. This is a deliberate methodological departure from PORT-001 to PORT-003, whose product inputs were anonymised researcher-authored descriptions. Page-contiguity was preserved in preference to trimming the boundary spill, so that no editorial decision enters the frozen input; the spill and the in-range administrative material are recorded above instead.

The corresponding leakage audit variant is `portfolio-leakage-audit.v0.2` in `leakage_audits/port-004.audit.json`. Its `organisation_identity_absent` and `ai_vendor_product_names_absent` checks are marked NOT_APPLICABLE_BY_DESIGN, replaced by source-integrity and AI-reference checks. Residual contamination risk: **LOW**.

## 6. Freeze status

**ACCEPTED FOR CASE 3 FREEZE**

Frozen artefacts in this case:

| Artefact | Path |
|---|---|
| Source document | `source_documents/port-004-mpep-0900-e9r10-2019.pdf` |
| Source capture | `source_captures/port-004-s1-mpep-chapter-900.capture.md` |
| Product input (BEFORE) | `product_inputs/port-004.before.txt` |
| Provenance manifest | `provenance/port-004.manifest.json` |
| Leakage audit | `leakage_audits/port-004.audit.json` |
| Freeze record | `port-004.freeze-record.v0.1.md` |
| Hash record | `port-004.hashes.sha256` |
| Register | `register.v0.2.json` |

Not created, by instruction: AFTER packet, extraction, review, assessment, recommendations, comparison, run directory.

Existing frozen artefacts for PORT-001, PORT-002 and PORT-003 were not modified. `register.v0.1.json` and `hashes.sha256` were left byte-identical; PORT-004 is registered in a new `register.v0.2.json` and hashed in a separate `port-004.hashes.sha256`.
