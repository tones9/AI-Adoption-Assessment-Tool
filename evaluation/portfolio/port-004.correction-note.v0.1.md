# PORT-004 corpus correction note

- Date: 2026-08-17
- Corrects: commit `e24e495` — "docs: freeze PORT-004 USPTO prior-art search BEFORE corpus"
- Method: **supersession by a follow-on commit. History is not rewritten.** Commit `e24e495` remains valid as the record of what was frozen at the time, and the superseded corpus bytes remain retrievable from it.
- Corpus revision: 1 → 2
- Extraction status at time of correction: **none. No extraction was ever run against the defective corpus and no provider call was ever made.**

## The defect

MPEP Chapter 900 is typeset in two columns. Corpus revision 1 was produced with `pdftotext -layout`, which preserves visual position and therefore concatenates left-column and right-column text onto shared output lines. Every line of the revision 1 corpus spliced two unrelated passages.

Observed at line 795 of the revision 1 corpus:

```
divergent from the disclosure as is permitted by the        requires three distinct steps by the examiner: (A)
```

The left fragment belongs to § 904.01(a) on variant embodiments. The right fragment belongs to § 904.02 on search planning. They are unrelated sentences from different sections presented as one line.

The same passage in revision 2:

```
requires three distinct steps by the examiner: (A)
identifying the field of search; (B) selecting the
proper tool(s) to perform the search; and (C)
determining the appropriate search strategy for each
search tool selected. Each step is critical for a
complete and thorough search.
```

## How it was missed

The revision 1 suitability check recorded "text extraction quality: PASS" on the basis that section numbering, revision stamps and page footers all survived extraction — which they did, and still do. Reading order was not tested. For a single-column document that check would have been sufficient; for a two-column document it was the wrong test.

Had the defect reached extraction, every chunk would have carried interleaved text from two sections, and any resulting finding would have been an artefact of the extraction command rather than a property of the engine or the document.

## What changed

| | Revision 1 (superseded) | Revision 2 (current) |
|---|---|---|
| Page range | 900-27 to 900-46 | **900-40 to 900-46** |
| Sections | §§ 902–904.03 | **§§ 904–904.03** |
| Extraction command | `pdftotext -f 27 -l 46 -layout` | **`pdftotext -f 40 -l 46`** |
| Reading order | interleaved, scrambled | **correct** |
| Characters | 88,319 | **22,888** |
| Lines / non-empty lines | 1,049 / 909 | **556 / 501** |
| Words | 10,449 | 3,514 |
| SHA-256 | `7bc9242a67e9400392c590e181db4ec7ca81880b44e4a903a5c71446467e492d` | **`98fd4ecece92f0bec27664241013677af1bd67e15816d3f8ba2291b23e017c01`** |
| Projected chunks | ~54 (upper bound) | ~18 (upper bound) |

The source PDF is unchanged: `source_documents/port-004-mpep-0900-e9r10-2019.pdf`, SHA-256 `a74b4a685afea1976d6e4b035e11ac14aa8850d97dbb006ec14eca9ba2ec29e7`, 1,885,991 bytes, 58 pages.

## Why the narrower scope was approved

- Preserve the strongest BEFORE methodology.
- Avoid including unrelated classification administration material — the § 903.08 family and § 903.09 occupied roughly a third of revision 1.
- Avoid the § 901.08 spill present at the head of revision 1.
- Avoid an artificial multi-range assembly step, which would have introduced an editorial decision into the frozen corpus.
- Keep the input as close as possible to a single bounded operational workflow.

## Composition of revision 2

| Component | Characters | Share |
|---|---|---|
| § 904–904.03 body (target workflow) | 21,385 | 93.4% |
| Leading spill — § 903.09 tail at the top of 900-40 (Patent Transfer Inquiry system, patent file wrapper) | 300 | 1.3% |
| Trailing spill — § 905 / § 905.01 opening at the foot of 900-46 (CPC scheme hierarchy, section symbols) | 1,143 | 5.0% |

Spill is retained unedited. Page-contiguity is preserved in preference to trimming so that no editorial decision enters the frozen corpus. This is the same principle applied in revision 1; the narrower range reduces spill from roughly a third of the corpus to 6.3%.

## Re-verification performed on revision 2

- Reading order confirmed continuous within column at the § 904.02 three-step passage.
- AI-term scan re-run on the new corpus: zero hits for `artificial intelligence`, `machine learning`, `neural`, `deep learning`, `predictive analytics`, `SimSearch`, `similarity search`.
- No OCR-derived text present. The § 904.02(b) decision tree remains a graphic, absent from the engine input, and the audit-only OCR remains outside the repository.
- Source PDF hash re-verified unchanged.

## Files updated in the correction commit

- `product_inputs/port-004.before.txt` — regenerated
- `provenance/port-004.manifest.json` — scope, hashes, counts, section map, composition, limitations
- `leakage_audits/port-004.audit.json` — new corpus hash, superseded hash, reading-order check block
- `port-004.freeze-record.v0.1.md` — corrected figures and correction history
- `register.v0.2.json` — corpus hash and revision
- `port-004.hashes.sha256` — recomputed
- `port-004.correction-note.v0.1.md` — this file, new

PORT-001, PORT-002 and PORT-003 artefacts are untouched. `register.v0.1.json`, `hashes.sha256` and `freeze_manifest.v0.1.json` remain byte-identical.
