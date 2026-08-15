# PORT-001 retrospective comparison

## Question

Given only the documented BEFORE process, did the AI Adoption Engine identify opportunity areas that substantially align with the AI intervention later documented by EY, while behaving responsibly where evidence was insufficient?

## Result

Yes, but only partially. The product reconstructed the six-step current process accurately and identified three capability areas later used in the EY implementation: broad visual-document processing, document information extraction and classification. It did not identify automated transfer into the claims system or the implementation's specific confidence and organisational-control design.

All six activities received `INVESTIGATE_FURTHER`. That does not predict or endorse the later deployment, but it was consistent with the frozen policy because the BEFORE document did not establish material AI capability fit, accuracy thresholds, verification controls, consequences of error, accountability, data readiness, implementation complexity or quantified value.

## Theme comparison

| AFTER intervention theme | Frozen product result | Classification |
|---|---|---|
| Image cleaning, preprocessing and layout analysis | `COMPUTER_VISION` mapped to document examination and manual extraction; all recommendations remained `INVESTIGATE_FURTHER` | `PARTIAL_ALIGNMENT` |
| OCR/NLP document information extraction | `DOCUMENT_INFORMATION_EXTRACTION` and `COMPUTER_VISION` mapped to examination and extraction; `INVESTIGATE_FURTHER` | `PARTIAL_ALIGNMENT` |
| Information classification | `CLASSIFICATION` mapped to relevance categorisation; `INVESTIGATE_FURTHER` | `PARTIAL_ALIGNMENT` |
| Transfer of structured data to the core claims system | Upload activity reconstructed, but no integration/orchestration capability mapped | `NO_DOCUMENTED_ALIGNMENT` |
| Controlled confidence levels and retained organisational control | Accountability and control evidence remained unknown; the product stayed cautious but did not identify the specific control mechanism | `NO_DOCUMENTED_ALIGNMENT` |

Counts:

- Strong alignment: 0
- Partial alignment: 3
- No documented alignment: 2
- Contradiction: 0

## Process reconstruction

Phase 3 extracted six activities corresponding to the frozen BEFORE sequence. Phase 4 retained all six and explicitly accepted their source order. Every accepted evidence reference resolved to the frozen Phase 2 text. No unsupported activity was added.

The reconstruction remained bounded by the source: exceptions, controls, downstream claim handling and quantitative operating conditions stayed unknown.

## Capability recognition

The product recognised the central extraction and classification opportunity:

- `DOCUMENT_INFORMATION_EXTRACTION` for document examination and manual extraction.
- `COMPUTER_VISION` for those same substantive document-processing activities.
- `CLASSIFICATION` for categorising extracted information by claim relevance.

It did not receive credit for capabilities it did not identify. In particular, the upload step had no routing, orchestration or integration mapping, and the output did not specify confidence thresholds or an organisational-control design.

## Deterministic recommendation

For every activity, evidence sufficiency passed because the activity itself was source-backed. The technical-fit gate then failed because `ai_capability_fit` was materially unknown. Business-value and risk/autonomy gates were not evaluated after that stopping result.

Accordingly, `INVESTIGATE_FURTHER` was a policy-consistent uncertainty outcome. It was neither a recommendation to deploy nor a contradiction of the later implementation. The comparison records partial capability alignment while preserving the difference between recognising a possible capability and establishing adoption suitability.

## Human-review contribution

Phase 4 materially improved input reliability in ways demonstrated by its audit trail:

- Four positive document/image capability assertions were rejected for arrival and opening-only activities.
- One incorrect step input was corrected using document evidence.
- 117 assessment assertions were explicitly retained as unknown rather than completed from external knowledge.
- Accepted inferred outputs remained labelled `MODEL_INFERRED`.
- No AFTER information entered the validated process.

These actions prevented unsupported positives and external case knowledge from becoming trusted deterministic inputs.

## Case conclusion

The engine found the central document-extraction and classification opportunities that later appeared in the EY implementation, but it did not reproduce the full intervention design and did not recommend adoption. Its cautious outcome was justified by missing BEFORE evidence. PORT-001 therefore shows substantial but partial opportunity alignment, responsible uncertainty and no material contradiction.

## Limitations

- EY is both implementation partner and publisher, and the insurer is anonymous.
- The AFTER evidence is a retrospective success story rather than independent ground truth.
- The reported 70% relates to documents correctly extracted and interpreted, not fully autonomous claim completion.
- Sample size, evaluation method, error distribution, implementation cost and negative outcomes are not disclosed.
- Publication bias and model-memorisation contamination remain possible.
- A single case cannot support cross-case or statistical conclusions.

## Recruiter-friendly summary

The completed product was tested on a frozen public case using a real live extraction and its unchanged deterministic policy. It reconstructed six process steps, identified three capabilities later used in practice, and retained an investigation outcome when deployment evidence was missing. The audit trail shows where human review removed unsupported signals and preserved uncertainty.
