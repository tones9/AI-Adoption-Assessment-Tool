# PORT-002 retrospective comparison

## Question

Given only the documented BEFORE customer-call process, did the AI Adoption Engine identify opportunity areas that substantially align with the later documented Elisa intervention, while behaving responsibly where evidence was insufficient?

## Result

Partially. The live product reconstructed the six-step customer-call process. Source-bounded human review then corrected one structural dependency and three capability signals that the live extraction had left unknown. The validated process mapped `CLASSIFICATION` to topic selection and `WORKFLOW_AUTOMATION` to initial routing and misroute retransfer.

Those are the same broad process boundaries later changed by Elisa. The output did not identify natural-language or speech understanding, self-service question answering, or an explicit rule for deciding which contacts should remain with a human. All six activities received `INVESTIGATE_FURTHER`; the engine did not recommend deployment.

## Theme comparison

| AFTER intervention theme | Frozen product result | Classification |
|---|---|---|
| Natural-language intent capture and classification | `CLASSIFICATION` mapped to the existing topic-selection boundary, but no natural-language or speech capability was identified | `PARTIAL_ALIGNMENT` |
| Automated specialist routing | `CLASSIFICATION` plus `WORKFLOW_AUTOMATION` mapped to topic selection and routing; recommendation remained `INVESTIGATE_FURTHER` | `PARTIAL_ALIGNMENT` |
| Reduced wrong routing and retransfers | The retransfer activity was reconstructed and mapped to `WORKFLOW_AUTOMATION`; no outcome magnitude was predicted | `PARTIAL_ALIGNMENT` |
| Self-service chatbot answers | Human answering was reconstructed, but no generative or knowledge-retrieval capability was mapped | `NO_DOCUMENTED_ALIGNMENT` |
| Retained human handling | Human-agent work was preserved, but accountability and the human/self-service boundary remained unknown | `NO_DOCUMENTED_ALIGNMENT` |

Counts:

- Strong alignment: 0
- Partial alignment: 3
- No documented alignment: 2
- Contradiction: 0

## Process reconstruction

Phase 3 extracted six activities matching the frozen BEFORE sequence:

1. Customer calls the service centre.
2. The interactive voice-response menu presents choices.
3. The customer selects an option using the keypad.
4. The system routes the call to a specialist agent.
5. A receiving agent retransfers a misrouted call.
6. The appropriately specialised agent addresses the question.

All six activities were retained. The candidate incorrectly attached a forward dependency to step 3 pointing toward the later routing activity. Phase 4 rejected that dependency, resolved the blocking conflict and accepted the explicit numbered order.

## Capability recognition

The final validated assessment identified:

- `CLASSIFICATION` for customer topic selection.
- `WORKFLOW_AUTOMATION` for specialist routing.
- `WORKFLOW_AUTOMATION` for misroute retransfer.

This recognition materially depended on human review: the live extraction left all three positive signals unknown even though the activities were explicit. The review corrected them from literal BEFORE evidence. No natural-language, speech-recognition, generative-answering or knowledge-retrieval capability was added.

## Deterministic recommendation

For all six activities, evidence sufficiency passed because the activity was source-backed. Technical fit then failed because `ai_capability_fit` remained materially unknown. Business-value and risk/autonomy gates were not evaluated after that stopping result.

Accordingly, all six outcomes were `INVESTIGATE_FURTHER`. This was policy-consistent caution, not a prediction or endorsement of Elisa's later deployment. It is not treated as a contradiction merely because AI was later implemented.

## Human-review contribution

The Phase 4 audit trail shows that review:

- corrected three explicit classification/routing signals;
- rejected one incorrect forward dependency;
- resolved the resulting blocking conflict;
- retained 123 unsupported assertions as unknown;
- kept all six source activities in their documented order; and
- added no AFTER facts to the validated process.

The reviewer had prior exposure to the public AFTER evidence during the earlier source audit. Every correction is independently traceable to literal BEFORE wording, but fully blind reviewer independence cannot be claimed.

## Reported outcomes

The published figures are deliberately not combined:

- Elisa reports approximately 90% routing accuracy versus 70–75% for the previous keypad menu and three times fewer retransfers.
- MindTitan reports up to 70% of inbound contacts handled by the chatbot, with 42% of handled contacts fully resolved, described as 34% of all inbound contacts.
- Elisa's 2022 sustainability report separately reports 8% of all incoming Estonia contacts resolved by Annika.

These figures concern different channels, years, scopes or denominators. They are reference context, not a single comparable performance measure.

## Plain-English conclusion

The product found the call-classification and routing opportunity that later appeared in Elisa's system, but only after human review corrected missed extraction signals. It did not identify the later self-service chatbot capability, and it refused to recommend adoption because the BEFORE document lacked evidence about fit, controls, quality and risk. This is an honest partial alignment result with responsible uncertainty.

## Limitations

- Elisa's sources are organisation-authored success accounts, and MindTitan was the implementation partner.
- No independent routing-quality, customer-harm or resolution-quality evaluation was found.
- Published outcome figures use incompatible scopes and denominators.
- Final capability recognition depended materially on human review rather than the live extraction alone.
- The reviewer was not blind to public AFTER evidence, although corrections are source-bounded and fully audited.
- The anonymised input reduces but does not eliminate model-memorisation risk.
- One case cannot support statistical or cross-case conclusions.

## Recruiter-friendly summary

The unchanged product was tested on a frozen public call-centre case using live extraction and a deterministic policy. It reconstructed six steps; human review fixed one dependency and three missed capability signals; the final assessment identified classification and routing opportunities later used in practice while withholding an adoption recommendation when evidence was missing. The comparison also records what the product missed: natural-language processing and self-service answering.
