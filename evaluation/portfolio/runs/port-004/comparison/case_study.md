# PORT-004 retrospective comparison

## Question

Given only the frozen BEFORE procedure for patent-examiner prior-art search, did the AI Adoption Engine identify opportunity areas that align with the later sealed USPTO AI-assisted search intervention, while behaving responsibly where evidence was insufficient?

## Result

Partially. The frozen product retained eight source-backed search activities and mapped `KNOWLEDGE_RETRIEVAL` to the planning activity, “identifying the field of search.” That is broadly compatible with the later AI-assisted Similarity Search feature, which uses application text to return ranked similar documents for examiner prior-art searches.

The product did not identify the specific similarity-search mechanism, the later recordation of AI-search use, or the retained-examiner-discretion boundary. All eight activities remained `INVESTIGATE_FURTHER`; the engine did not recommend deployment.

## Theme comparison

| AFTER theme | Frozen product result | Classification |
|---|---|---|
| AI-assisted similarity retrieval for examiner prior-art search | `KNOWLEDGE_RETRIEVAL` mapped to the field-of-search planning step; adjacent tool-selection, strategy and search activities were reconstructed, but no specific similarity-search mechanism or adoption recommendation was produced | `PARTIAL_ALIGNMENT` |
| Recording AI-search use in examiner search history | A related documentation activity was reconstructed, but no capability or traceability/control design was identified | `NO_DOCUMENTED_ALIGNMENT` |
| Retained examiner discretion and supplementary human judgement | Human search activities were preserved, but accountability, risk and control criteria remained unknown and no governance boundary was identified | `NO_DOCUMENTED_ALIGNMENT` |

Counts:

- Strong alignment: 0
- Partial alignment: 1
- No documented alignment: 2
- Contradiction: 0

## What the sealed AFTER evidence establishes—and does not

The sealed sources distinguish four different facts:

- **Intervention existence:** USPTO sources state that AI search capabilities entered PE2E Search and that utility patent examiners began using Similarity Search for prior-art searches in September 2022.
- **Reported use:** a 2024 USPTO blog reports regular use by more than half of patent examiners and more than 1.5 million AI-feature queries. This is uptake context, not quality or impact evidence.
- **Human control:** USPTO says examiners retain discretion; PPAC advises supplementary use alongside examiner judgement. PPAC’s statement is advisory, not proof of uniform implementation.
- **Measured outcomes:** none appear in the sealed packet. There is no retrieval-quality, time-saving, cost, error, harm or causal-impact measure.

Deployment and reported usage are therefore not treated as proof that the tool was effective, nor as proof that the frozen engine should have recommended adoption.

## Process reconstruction and capability recognition

Phase 3 extracted eight activities, all retained in human review. The first three planning activities have verified dependencies; the others retain source-position order only. Review made no capability-signal edits. It retained the two Phase 3 positive signals on the first activity and mapped them to `DOCUMENT_INFORMATION_EXTRACTION` and `KNOWLEDGE_RETRIEVAL`; only the latter is a broad match for later reference retrieval.

The engine did not identify:

- application-text-to-ranked-documents similarity search as a distinct mechanism;
- explicit AI-search recordation and traceability; or
- an explicit retained-human-discretion / assurance boundary.

## Deterministic recommendation and appropriate uncertainty

For all eight activities, evidence sufficiency passed because the activity was source-backed. Technical fit then failed because `ai_capability_fit` was unknown. Business-value and risk/autonomy gates were not evaluated after that stopping result.

This was appropriate uncertainty, not a contradiction. The procedural BEFORE corpus contained no ordinal fit assessment, performance measure, control design, data-readiness evidence, implementation complexity or quantified business value. The later sealed sources do not retroactively add any of those facts to the frozen product input.

## Human-review contribution

Review preserved structural and evidentiary integrity:

- it accepted the eight source-backed activities;
- it resolved two ambiguous dependencies using existing BEFORE evidence;
- it retained 80 material criteria and 8 accountability fields as unknown;
- it made no capability-signal edit, introduced no `HUMAN_SUPPLIED` assertion and minted no evidence; and
- it did not introduce AFTER content into the production workflow.

The curator had opened the public AFTER sources during pre-reveal collection, so curator blindness is not claimed. The frozen Stage 1–5 records establish product-input separation, not individual reviewer blindness to public information.

## Plain-English conclusion

The engine found a broad search-and-retrieval opportunity that is compatible with a later USPTO AI search feature, but it did not predict the feature, recommend deployment or prove effectiveness. It correctly asked for more evidence because the original procedure did not contain enough information to assess fit, risk, controls or value. The comparison also makes the misses explicit: similarity search itself, AI-use recordation and the human-control boundary.

## Limitations

- The AFTER evidence is retrospective reference evidence, not independently established ground truth or an efficacy study.
- Three sources are USPTO-authored; the PPAC source is advisory.
- The sources describe a broader examiner environment and do not directly observe every frozen process step.
- No measured outcome is available in the sealed packet.
- Curator exposure is disclosed; reviewer blindness is not claimed.
- PORT-004 has a different production fingerprint from PORT-001/002. This document makes no cross-case inference.
