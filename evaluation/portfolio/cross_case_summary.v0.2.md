# Portfolio validation — v0.2 cross-case summary

## Scope

This is a new descriptive portfolio composition for the valid forward-analysis cases: **PORT-001, PORT-002 and PORT-004**. It does not replace or edit the historical v0.1 summary, which remains the accurate record of its original PORT-001/PORT-002/PORT-003 composition.

PORT-003 is retained historically with status **`SUPERSEDED_CONTAMINATED_BEFORE`**. Its source audit found that the prior workflow was knowable only from AFTER-dated material. It is therefore excluded from every v0.2 aggregate, count and conclusion.

This is not statistical validation, a measure of precision or recall, predictive accuracy, causal impact, scoring performance, or cross-industry generalisation.

## Included cases and production cohorts

| Case | Domain | Activities | Alignment | Recommendation distribution | Production cohort |
|---|---|---:|---|---|---|
| PORT-001 | Insurance claims-document processing | 6 | 0 strong / 3 partial / 2 none / 0 contradiction | 6 × `INVESTIGATE_FURTHER` | Historical Phase 8: `4deca425…` |
| PORT-002 | Telecommunications customer-call routing | 6 | 0 strong / 3 partial / 2 none / 0 contradiction | 6 × `INVESTIGATE_FURTHER` | Historical Phase 8: `4deca425…` |
| PORT-004 | Patent-examiner prior-art search | 8 | 0 strong / 1 partial / 2 none / 0 contradiction | 8 × `INVESTIGATE_FURTHER` | Later PORT-004: `3c5c86bd…` |

PORT-001 and PORT-002 share the historical Phase 8 production fingerprint. PORT-004 used a later production fingerprint, although it retained the same recorded decision-policy identity (`decision_policy.v0.2`, `0.2.0`, fingerprint `b72e528b…`) and Phase 1 contract version (`phase1-v0.3`). The cases are reported together descriptively; they are **not** one identical frozen-production-baseline cohort.

## Aggregate descriptive counts

| Measure | Count |
|---|---:|
| Activities assessed | 20 |
| AFTER intervention themes | 13 |
| Strong alignment | 0 |
| Partial alignment | 7 |
| No documented alignment | 6 |
| Contradiction | 0 |
| Appropriate-uncertainty findings | 6 |
| Unsupported activities added | 0 |
| Capability-bearing activities | 7 |
| Reviewed unknown-retention events | 328 |

All 20 recommendations were `INVESTIGATE_FURTHER`. No included activity reached `AUTOMATE`, `AUGMENT`, or `DO_NOT_RECOMMEND`.

## What the engine consistently did well

**Source-bounded reconstruction.** The portfolio retained 20 source-backed activities and added no unsupported activity. This is evidence of disciplined reconstruction of the submitted documents; it is not independent proof that each frozen process is a complete description of real operational practice.

**Preserving uncertainty.** In each case, the product left material evidence unknown rather than importing AFTER facts or manufacturing fit, control, risk, value, or outcome evidence. The six appropriate-uncertainty findings distinguish the actual technical-fit stopping reason from additional evidence that would be needed for adoption planning.

**Broad opportunity recognition.** The included cases exercised `DOCUMENT_INFORMATION_EXTRACTION`, `COMPUTER_VISION`, `CLASSIFICATION`, `WORKFLOW_AUTOMATION`, and `KNOWLEDGE_RETRIEVAL`. Those broad capabilities produced seven partial alignments with later documented interventions.

## Role of human review

Review made a different, evidence-bounded contribution in every included case:

- **PORT-001 — suppression and correction.** Review prevented four unsupported positive capability assertions from becoming trusted findings, corrected one input from document evidence, and retained 117 assertions as unknown.
- **PORT-002 — recovery and structural correction.** Review recovered three source-supported capability signals missed by extraction, rejected an incorrect dependency, resolved the resulting conflict, and retained 123 assertions as unknown.
- **PORT-004 — structural integrity and unknown preservation.** Review resolved two planning dependencies, made no capability-signal edit, and retained 80 material criteria plus 8 accountability fields as unknown.

These results show review as a meaningful control boundary rather than a uniform rewrite or rubber stamp. Reviewer blindness is not claimed in any included case; the case records disclose curator/reviewer exposure limitations.

## What the engine did not establish

**Specific intervention mechanisms.** The broad capability mappings did not establish later-specific mechanisms: automated core-system transfer and confidence-control design in PORT-001; speech/natural-language handling, self-service answering and human-service eligibility in PORT-002; and similarity search, AI-use recordation and retained-examiner-discretion design in PORT-004.

**Human-control and governance design.** Each included AFTER packet described a human or organisational control boundary. All three corresponding themes were `NO_DOCUMENTED_ALIGNMENT`. Conservative non-deployment is not credited as identifying a control design.

**Measured effectiveness.** The sealed sources do not form a comparable outcomes dataset. PORT-001 and PORT-002 have organisation or implementation-partner outcome accounts with limited methods and incompatible scopes; PORT-004 has no measured retrieval-quality, time-saving, cost, error, harm or causal outcome measure in its sealed packet. Deployment and reported usage do not prove effectiveness.

## Deterministic-policy behaviour

The real cases demonstrate one cautious gate pattern:

1. All 20 source-backed activities passed evidence sufficiency.
2. All 20 stopped at technical fit because `ai_capability_fit` was unknown.
3. No included activity reached the business-value or risk-and-autonomy gates.
4. No priority score was produced.

This supports a narrow statement: the policy preserved an evidence gap and stopped conservatively on these inputs. It does **not** validate threshold choices, weights, scoring bands, recommendation accuracy, predictive performance, or real-world adoption outcomes. Unit tests can exercise branches synthetically, but no included portfolio case reached later gates or scoring bands.

Zero contradictions is similarly limited. An `INVESTIGATE_FURTHER` result does not conflict with a later intervention, but its absence does not demonstrate that the engine predicts successful adoption or makes validated recommendations.

## Evidence and portfolio limitations

- Three selected public adoption cases cannot support statistical, causal, precision/recall, predictive, or cross-industry claims.
- The AFTER sources are mainly organisation-authored or implementation-partner accounts, not independent effectiveness evaluations.
- There is no negative case: no evidence of a process where AI was considered and appropriately rejected, or deployed and withdrawn.
- Model-memorisation and publication-selection risk cannot be eliminated; PORT-003 is excluded precisely because its BEFORE contamination risk was disqualifying.
- The included portfolio spans two production-fingerprint cohorts, so PORT-004 is not an identical-baseline replication of PORT-001/002.

## Product learning from portfolio validation

### What belonged to the original Phase 1–7 product

The evaluated product consisted of decision intake, document ingestion, evidence-bounded extraction, human review and approval, deterministic assessment, decision-package generation, and presentation/output. It preserved `UNKNOWN`, kept AFTER research outside the frozen product run, and still produced a Decision Package when evidence was insufficient.

### What validation revealed as limitations

The product could reconstruct process activity and identify some broad opportunity areas, but thin process documentation rarely supplied the operational fit, control, performance, risk, complexity and value evidence needed for a stronger adoption decision. It could identify important missing information, but the historical product had no controlled, user-friendly way for a customer to strengthen selected gaps and request reassessment.

### Later product extensions proposed

**Gap Resolution Workspace (GRW)** is a discovered, post-validation extension. It responds to the specific validation finding above: after a useful initial Decision Package, customers should be able to optionally provide the minimum trustworthy additional evidence needed to strengthen—or leave unchanged or weaken—the next decision. GRW was **not** part of the original Phase 1–7 architecture and was **not** implemented or tested in PORT-001, PORT-002 or PORT-004.

The **Adoption Execution Layer (AEL)** remains future and out of scope. It would address governance, pilots, implementation, deployment and measured outcomes after an organisation chooses to proceed. It was not part of the evaluated product and is not implemented here.

## Honest headline

> Across three valid but two-cohort retrospective cases, the engine reconstructed source-backed process activities, found some broad opportunity overlap, and consistently preserved uncertainty. The portfolio does not validate real-world recommendation accuracy, scoring performance, or generalisation.
