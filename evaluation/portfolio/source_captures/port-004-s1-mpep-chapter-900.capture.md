# PORT-004-S1 frozen source capture

- Publisher: United States Patent and Trademark Office
- Title: Manual of Patent Examining Procedure, Ninth Edition, Revision 10.2019 (June 2020 publication), Chapter 900 — Prior Art, Classification, and Search
- URL: https://www.uspto.gov/web/offices/pac/mpep/old/e9r10-2019/mpep-0900.pdf
- Archive index: https://www.uspto.gov/web/offices/pac/mpep/old/mpep_E9R10-2019.htm
- Independent date anchor: https://www.federalregister.gov/documents/2020/07/10/2020-14931/manual-of-patent-examining-procedure-ninth-edition-revision-of-june-2020
- Local frozen copy: `source_documents/port-004-mpep-0900-e9r10-2019.pdf`
- SHA-256: `a74b4a685afea1976d6e4b035e11ac14aa8850d97dbb006ec14eca9ba2ec29e7`
- File size: 1,885,991 bytes
- Page count: 58 (printed labels 900-1 to 900-58, aligned 1:1 with physical pages)
- Accessed: 2026-08-17
- Provenance: examining-authority-authored operational procedure manual
- Source quality: HIGH

## Capture type

This capture differs from PORT-001 to PORT-003. Those were claim-level paraphrase captures of press and vendor material. This is a **whole-document capture of a primary operational source**: the document itself is frozen in the repository and is used verbatim as the product input. No paraphrase step exists between the source and the engine input.

## Why this source qualifies as BEFORE evidence

- **Operational document.** It is the working procedure manual that governs how patent examiners conduct prior-art search. It is not a description of a process written for an external audience.
- **Authored before AI implementation.** Content current through October 2019, published June 2020. SimSearch entered examiner use in September 2022; the AI-for-PE2E Official Gazette notice was published 20 December 2021.
- **Created independently of AI adoption.** The manual is published to instruct examiners and to inform applicants of examination practice. It has no relationship to, and makes no reference to, any AI programme. Its date is verifiable outside the publishing organisation via the Federal Register notice, and again via the PDF's embedded creation timestamp of 25 June 2020.
- **Contains activities, actors, inputs, outputs and decisions.** Evidenced below.

## Workflow content verified present in body text

### Activities
- § 904: obtain a thorough understanding of the invention as disclosed and claimed, then search the prior art in patents and other published documents including nonpatent literature; conduct an inventor-name search to identify double-patenting references; review parent applications in all continuing applications and consider prior art cited there; rely on the initial search for the first Office action on the merits; complete the Image File Wrapper search notes form recording classification locations, other sources consulted and search dates; record search updates with databases, queries and classifications employed.
- § 904.02: plan the search in three distinct steps — "(A) identifying the field of search; (B) selecting the proper tool(s) to perform the search; and (C) determining the appropriate search strategy for each search tool selected."
- § 904.02(a)–(c): classified search; search tool selection; Internet searching as an Office-approved tool.
- § 904.03: conduct a search commensurate with the limitations in the most detailed claims; cover subject matter reasonably anticipated to be claimed by amendment; select the best references rather than multiplying equivalents; fully consider references cited in an Information Disclosure Statement.

### Actors
Examiner; supervisory patent examiner; Technology Center art units; STIC and EIC search staff; Office of Patent Classification.

### Inputs
Nonprovisional application, claims and disclosure; parent application file and its cited art; applicant-submitted Information Disclosure Statement; international search report and Form PCT/DO/EO/903 for national stage applications; classification schedules and definitions.

### Outputs
Identified references; the Image File Wrapper search notes form with classification locations, sources and dates; the first Office action on the merits; recorded search updates.

### Decisions and exceptions
Whether any of the three mandatory reference sources may be eliminated, and the reasonable-certainty justification standard required to do so; how to prioritise the field of search; which search tools to use, based on examiner knowledge of coverage, strengths and weaknesses; whether a second search is necessitated after the first Office action; the § 904.02(b) decision-tree branches; which references qualify as "best."

### Operational constraints stated
Search must be commensurate with the most detailed claims; the second action should be made final or the application allowed with no further searching beyond an update; tool coverage limits are an explicit selection factor.

## AI-reference scan

Zero occurrences of `artificial intelligence`, `machine learning`, `neural`, `deep learning`, `predictive analytics`, `SimSearch`, `similarity search`, word-boundary `AI`, or `algorithm` across all 58 pages, including OCR of both full-page graphics.

`automated` appears 16 times; every occurrence was inspected and is either a product name (EAST, WEST, FPAS) or a generic reference to electronic full-text and Boolean retrieval.

## Capture limitations

- § 904.02(b) decision tree exists as a graphic and is not visible to text-only ingestion.
- OCR recovery was audit-only and must NOT be added to engine input.
- MPEP is normative, not observational.
- Actual examiner behaviour and time constraints are not represented.
- The document cites USPTO intranet resources (Classification Home Page, Examiner Handbook to Classification, STIC NPL website) that are referenced but not reproduced; the public document therefore does not disclose the full internal procedure.

## Copyright status

Work of the United States federal government, public domain. The complete document is reproduced in this repository without restriction.
