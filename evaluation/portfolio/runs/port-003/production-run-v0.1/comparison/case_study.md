# PORT-003 retrospective comparison

## Question

Given only the documented BEFORE adviser meeting-documentation process, did the AI Adoption Engine identify opportunity areas that substantially align with the later documented Morgan Stanley intervention, while behaving responsibly where evidence was insufficient?

## Result

Partially, with the strongest single alignment of the three portfolio cases. The live product reconstructed all four documented activities, added none, and identified the meeting-summary activity as a generative content-creation opportunity — without any human assistance. That is the activity and capability family Morgan Stanley later automated.

It did not identify speech transcription, which its capability taxonomy structurally cannot express. It identified nothing for follow-up email drafting or CRM updating, both of which were deliberately excluded from the BEFORE input because public sources did not document them as prior activities. All four activities received `INVESTIGATE_FURTHER`; the engine did not recommend deployment anywhere.

## Theme comparison

| AFTER intervention theme | Frozen product result | Classification |
|---|---|---|
| Meeting recording, transcription and note capture | Correct activity boundary with `GENERATIVE_AI` mapped, but no speech or transcription capability identified | `PARTIAL_ALIGNMENT` |
| Automated summarisation of key points | `GENERATIVE_AI` mapped to "Prepare a meeting summary" by the extraction unaided | `STRONG_ALIGNMENT` |
| Action-item extraction and surfacing | Activity reconstructed with a generative signal, but no action-item extraction or orchestration capability identified | `PARTIAL_ALIGNMENT` |
| Draft follow-up client email | Nothing identified; activity absent from the BEFORE input by design | `NO_DOCUMENTED_ALIGNMENT` |
| Customer-record updating in the CRM | Nothing identified; activity absent from the BEFORE input by design | `NO_DOCUMENTED_ALIGNMENT` |
| Retained adviser review and discretion | Accountability recorded on the meeting activity, no autonomy recommended, future state labelled not deployed; per-activity oversight boundary unknown | `PARTIAL_ALIGNMENT` |

Counts:

- Strong alignment: 1
- Partial alignment: 3
- No documented alignment: 2
- Contradiction: 0

Two of the six themes were excluded from the BEFORE input by evaluation design. Their `NO_DOCUMENTED_ALIGNMENT` labels measure the evaluation boundary, not a product failure.

## Process reconstruction

Phase 3 extracted four activities matching the frozen BEFORE sequence:

1. Conduct a meeting with a client.
2. Record notes and action items manually.
3. Review and clean up the notes.
4. Prepare a meeting summary.

All four were retained with `order_basis` explicit. One dependency was extracted, from the summary activity to the note-cleanup activity, citing the source phrase "from the cleaned notes". It is consistent with the numbered order and was accepted rather than corrected. The extraction raised no issues and required no repair attempt. All evidence references resolve exactly to the frozen Phase 2 document.

Nothing was invented. This matters more here than in the other two cases: PORT-003 is a high-profile case with high recorded contamination risk, and a memorising model would plausibly have reconstructed email drafting or Salesforce entry, both prominent in public reporting and both absent from the anonymised input. Neither appeared. That is weak evidence against memorisation-driven reconstruction on this case, not proof of its absence.

## Capability recognition

The final validated assessment identified:

- `GENERATIVE_AI` for manual note and action-item recording.
- `GENERATIVE_AI` for meeting-summary preparation.

Both came from the live extraction, each citing a literal source phrase. Steps 1 and 3 carry no capability. Every one of the remaining thirty-eight capability signals stayed unknown.

**Taxonomy finding.** The frozen taxonomy has ten capability signals and none covers speech, audio or transcription; `interprets_images_or_video` covers vision only. Transcription is the defining capability of the deployed intervention, so theme T1 could not have been fully recognised regardless of how good the evidence was. This is an expressiveness gap in the product, not an evidence gap in the case. It is recorded as a finding only — the taxonomy is frozen, and changing it now using AFTER knowledge would violate the evaluation protocol.

## Deterministic recommendation

For all four activities, evidence sufficiency passed because each activity is source-backed. Technical fit then failed because `ai_capability_fit` remained materially unknown. Business value and risk-and-autonomy were never evaluated.

Accordingly, all four outcomes were `INVESTIGATE_FURTHER`. Notably, two activities carried an identified `GENERATIVE_AI` capability and the engine still withheld a recommendation. Identifying that a capability family is relevant is not the same as establishing that it fits the task, and the policy correctly refused to conflate the two. This is policy-consistent caution, not a prediction or endorsement of the later deployment, and it is not a contradiction merely because AI was subsequently implemented.

## Human-review contribution

The Phase 4 audit trail shows that review:

- accepted 46 source-supported assertions;
- retained 81 assertions as unknown, including all forty decision criteria;
- accepted the explicit numbered activity order;
- accepted the order-consistent dependency;
- made zero corrections, zero rejections, and resolved zero conflicts; and
- added no fact absent from the frozen BEFORE document.

This is the inverse of PORT-002, where review recovered three capability signals the extraction had missed and rejected one incorrect dependency. Here the extraction missed no supported signal and produced no incorrect structure, so review contributed verification and disciplined unknown-retention rather than recovery. Across the portfolio this demonstrates two distinct Phase 4 profiles rather than a single rehearsed one.

The reviewing research agent knew the organisation identity before the run and had read the case leakage audit, which itself refers to later intervention functions. Reviewer blindness is not claimed. The mitigating fact specific to this case is that the review altered nothing. A withdrawn review proposal — based on a reviewer misreading of a truncated diagnostic, and blocked by a script precondition check before it reached any artefact — is disclosed in full in `after_unseal_record.v0.1.json`, because it concerned exactly the signal most likely to align with the AFTER evidence.

## Reported outcomes

The published figures are deliberately not combined:

- Morgan Stanley reports that one adviser estimated a saving of about half an hour per meeting.
- CIO reports that some advisers previously spent up to an hour after calls cleaning up notes.
- Morgan Stanley and CIO both report that some support professionals attended meetings primarily to take notes and create summaries.

Only the first is an intervention outcome, and it is a single testimonial inside an organisation-authored announcement rather than a measured average. The other two describe the BEFORE state. They are reference context, not a performance measure. The product produced no ROI figure and stated `ROI / quantified benefit unavailable with current evidence.`

## Plain-English conclusion

The product found the summarisation opportunity that later became the core of Morgan Stanley's tool, and it found it on its own, from four plain sentences with no company name attached. It did not find transcription, because its capability vocabulary has no word for it. It found nothing for email drafting or CRM entry, because the evidence deliberately did not describe them. And it refused to recommend adopting anything, because the source said nothing about fit, controls, data quality or risk. That combination — a real hit, a structural blind spot, two out-of-scope themes and consistent refusal to over-claim — is an honest partial alignment result.

## Limitations

- The principal AFTER source is an organisation-authored launch announcement with positive pilot testimonials.
- No independent accuracy, completeness, client-impact or risk evaluation of the intervention was found.
- The only quantified benefit is one adviser's estimate, not a measured average.
- Two of six themes were excluded from the BEFORE input by evaluation design and could not have been identified.
- The capability taxonomy cannot express speech or transcription.
- `GENERATIVE_AI` is broad; matching it to summarisation is a family-level correspondence, not evidence that the product specified the deployed solution.
- The reviewer was not blind to the organisation identity or the leakage audit, although the review altered no extracted content and is fully audited.
- High-profile case with high model-memorisation risk; anonymisation reduces but does not eliminate it.
- One case cannot support statistical, causal or cross-industry conclusions.

## Recruiter-friendly summary

The unchanged product was tested on a frozen, anonymised public description of an adviser meeting-documentation process, using live extraction and a deterministic policy. It reconstructed the four documented activities, added none, and identified meeting summarisation as a generative-AI opportunity area that the organisation later automated in practice. It did not identify speech transcription, which its capability taxonomy cannot express, and it withheld any adoption recommendation because the source evidence did not establish capability fit or risk. Human review made no corrections in this case — the extraction needed none — which is itself a reportable result alongside PORT-002, where review materially rescued the assessment.
