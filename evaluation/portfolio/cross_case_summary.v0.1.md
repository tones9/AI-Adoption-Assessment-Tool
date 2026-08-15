# Phase 8 portfolio validation — three-case cross-case summary

A small retrospective public before/after portfolio validation of the completed AI Adoption Engine. Three frozen public cases, each run through the unchanged Phase 1–7 product using only anonymised BEFORE evidence, with the AFTER packet opened only after the product output was hash-frozen and committed.

This is a portfolio demonstration. It is not scientific proof, statistical validation, causal evidence, or proof of generalisation.

## The three cases

| Case | Domain | Activities | Capabilities identified | Alignment | Recommendations |
|---|---|---|---|---|---|
| PORT-001 | Insurance claims-document processing | 6 | `DOCUMENT_INFORMATION_EXTRACTION`, `COMPUTER_VISION`, `CLASSIFICATION` | 0 strong / 3 partial / 2 none / 0 contra | 6 × `INVESTIGATE_FURTHER` |
| PORT-002 | Telecoms customer-call routing | 6 | `CLASSIFICATION`, `WORKFLOW_AUTOMATION` | 0 strong / 3 partial / 2 none / 0 contra | 6 × `INVESTIGATE_FURTHER` |
| PORT-003 | Wealth-management meeting documentation | 4 | `GENERATIVE_AI` | 1 strong / 3 partial / 2 none / 0 contra | 4 × `INVESTIGATE_FURTHER` |

All three ran against an identical production baseline: fingerprint `4deca425…`, policy `decision_policy.v0.2` (`0.2.0`, fingerprint `b72e528b…`), contract `phase1-v0.3`, model `gpt-5.6-terra`.

**Totals:** 16 activities, 16 intervention themes, 8 capability-bearing activities, 321 unknowns retained by review, 0 unsupported activities invented, 0 contradictions, 16/16 `INVESTIGATE_FURTHER`.

## What held up

**Process reconstruction — the product's most reliable behaviour.** All sixteen documented activities across three industries were reconstructed in source order with resolved evidence. No case invented an activity. On PORT-003, a high-profile case with high recorded memorisation risk, the extraction notably did *not* reconstruct the widely reported email-drafting or CRM steps that were deliberately absent from the anonymised input.

**Human review works, and works differently each time.** This is the strongest finding in the portfolio, because the three cases exercised three different failure modes:

- **PORT-001 — suppression.** Review rejected four unsupported positive capability assertions the extraction had asserted on arrival and opening-only activities. It caught *false positives*.
- **PORT-002 — recovery.** Review corrected three explicit capability signals the extraction had left unknown, rejected an incorrect forward dependency and resolved the resulting conflict. It caught *false negatives*.
- **PORT-003 — verification.** Review changed nothing, because nothing was wrong. It correctly *abstained*.

A human boundary that only ever rubber-stamps, or only ever rewrites, would be evidence of a decorative control. Three distinct profiles across three cases is evidence of a functional one.

**Consistent refusal to over-claim.** No case produced a quantified benefit; every decision package stated `ROI / quantified benefit unavailable with current evidence.` Every future-state workflow stayed labelled `PROPOSED / NOT DEPLOYED`. No contradiction arose in sixteen themes.

## What did not

**The deterministic decision engine was never actually exercised.** All sixteen activities returned `INVESTIGATE_FURTHER`, and every single one stopped at the same gate — technical fit — for the same reason: `ai_capability_fit` unknown. The business-value and risk-and-autonomy gates were never evaluated. No priority score was ever produced. Not one threshold, weight or scoring band in `decision_policy.v0.2` was tested.

This matters more than any alignment count in this document. The deterministic policy is the product's central claim, and this evaluation provides almost no evidence about it. What it does validate is Phases 2–4 and the gate *ordering*.

The root cause is a mismatch between the evidence class and the policy's inputs. Public BEFORE evidence describes what an organisation did; the policy consumes operational criterion values — repetition, predictability, data readiness, error consequence, quantified value. Press releases and vendor case studies do not report those. They are structurally unavailable in this kind of source, which means no amount of additional public cases would fix it.

**Zero contradictions is a weaker result than it looks.** A system that always answers "investigate further" cannot contradict a later deployment. The absence of contradictions is a real absence of false negatives, but it should not be read as decision accuracy.

**Governance and control design was never reconstructed — three for three.** Every case documented an AFTER control boundary: confidence thresholds and retained organisational control (PORT-001), the retained human-service boundary (PORT-002), adviser verification and discretion (PORT-003). None was identified from BEFORE evidence. Public process descriptions appear to omit control design systematically.

**Half the capability taxonomy is untouched, and one needed capability cannot be expressed.** Five of ten capabilities never appeared across sixteen activities: prediction, anomaly detection, knowledge retrieval, recommendation, decision support. Separately, PORT-003 established that the taxonomy has no speech, audio or transcription signal at all — so the defining capability of that intervention could not have been expressed no matter how good the evidence was. This is a product expressiveness gap, discovered by the evaluation. The taxonomy was not modified.

**No negative case, so specificity is unmeasured.** All three organisations adopted AI and published about it. The portfolio contains no case where AI was considered and rejected, or deployed and withdrawn. There is no evidence at all about whether the product would correctly decline to identify an opportunity where none existed.

## Evaluation integrity

The protocol order — freeze BEFORE, seal AFTER, run the real product, freeze and commit the output, then open AFTER — was preserved in all three cases. Across the whole exercise, no production code, policy, prompt, schema, model configuration or capability taxonomy was modified. The production fingerprint was verified as `4deca425…` at every stage of every case.

Reviewer blindness is **not** claimed in any case. The reviewing research agent had prior exposure to public AFTER evidence through the source audit, and in PORT-003 knew the organisation identity before the run. Each unseal record discloses the specific exposure. PORT-003 additionally discloses a withdrawn review proposal that was based on a reviewer misreading, targeted the AFTER-aligned signal, and was blocked by a script precondition check before reaching any artefact.

One reproducibility defect is recorded honestly: the PORT-001 and PORT-002 operator scripts were never committed and are unrecoverable. Those runs remain hash-verifiable through their frozen artefacts but cannot be re-executed. PORT-003 committed its operator scripts, and its freeze manifest records their digests.

## Honest headline

> The product reliably reconstructs documented processes from thin public evidence, identifies a partially overlapping subset of the capability areas organisations later deployed, and consistently refuses to recommend adoption when the evidence does not support one. Its deterministic recommendation layer, which is the product's central claim, was not meaningfully exercised by this evaluation.

## Suitable portfolio phrasing

Accurate claims:

- "Retrospective alignment on a small set of frozen public before/after cases."
- "Identified opportunity areas later used in practice, including one case where the extraction found the deployed capability unaided."
- "Preserved uncertainty where evidence was insufficient — 321 assertions retained as explicitly unknown rather than completed from outside knowledge."
- "Human review prevented unsupported model assertions from entering trusted assessment, and in a separate case recovered signals the model had missed."

Claims this evidence does **not** support:

- "Scientifically validated", "proved accurate", "predicts successful AI adoption", "validated across industries", "high real-world accuracy."
- Any claim about the accuracy of the deterministic recommendation, which returned a single value in every case.

## Limitations

- Three self-selected cases, all published adoption success stories.
- Every AFTER source is organisation-authored or relies materially on company sources; no independent accuracy, client-impact or risk evaluation was found for any intervention.
- Reported outcome figures are non-comparable within and across cases, and were never merged.
- The reviewer was not blind to public AFTER evidence in any case.
- Model-memorisation contamination cannot be excluded; recorded as high for PORT-003.
- The deterministic decision policy remains provisional and is effectively untested by this exercise.
- Three cases cannot support statistical, causal or cross-industry generalisation.
