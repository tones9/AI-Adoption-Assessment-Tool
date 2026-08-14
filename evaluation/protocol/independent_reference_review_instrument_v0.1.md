# Phase 8 Independent Reference Review Instrument v0.1

Status: **FINAL FOR FREEZE**

## 1. Reviewer instructions

### Purpose

Your role is to independently check whether the proposed reference description of a current business process is accurate, evidence-based, and suitable for evaluating AI-adoption recommendations.

You are reviewing the research reference—not the AI Adoption Engine.

### Materials you may use

Use only:

- the assigned frozen before-state case packet;
- the proposed current-state activity list;
- the cited evidence spans;
- this instrument.

You must not use or request:

- after-state packets or later interventions;
- engine or baseline outputs;
- confirmatory provider extractions;
- policy rules, gates, thresholds, weights or scores;
- external web searches or outside knowledge about the organisation.

Do not fill gaps using what normally happens in similar businesses. If the supplied evidence does not establish something, mark it as unknown or insufficient.

### Independence declaration

Before reviewing a case, confirm:

- [ ] I did not develop the AI Adoption Engine’s methodology, policy, prompts, gates, weights or thresholds.
- [ ] I did not prepare this case’s before/after packet.
- [ ] I have not seen the case’s after-state packet or later intervention.
- [ ] I have not seen engine, baseline or confirmatory provider outputs for this case.
- [ ] I used only the permitted before-state material.
- [ ] I will record my own judgement before adjudication with the primary annotator.

Reviewer name or pseudonym: ____________________

Relevant qualifications or experience: ______________________________

Potential conflicts of interest: ____________________________________

Case ID: ____________________  Review date: ____________________

Before-packet hash verified: Yes / No

---

## 2. Knowledge-state definitions

Use these classifications for factual assertions:

- **Known:** directly stated and supported by the before-state evidence.
- **Inferred:** a reasonable interpretation of the evidence, but not directly stated. The inference must be identified clearly.
- **Unknown:** the supplied material does not support a responsible conclusion.
- **Supported empty:** the evidence explicitly establishes that something is absent or that a collection is empty.

An assertion should not be marked known merely because it is common business practice.

---

## 3. Recommendation-mode guide

Choose the mode that is most defensible from the before-state information.

- **AUTOMATE:** AI could perform the activity or a substantial operational part of it, subject to appropriate governance and exception handling.
- **AUGMENT:** AI could assist a human, while the human remains actively involved in reviewing, deciding, communicating or completing the activity.
- **INVESTIGATE_FURTHER:** the available information is insufficient to make a responsible recommendation. Further evidence or analysis is needed.
- **DO_NOT_RECOMMEND:** AI is not an appropriate response to the documented activity or problem.

If more than one mode is reasonably defensible, select one primary mode and record the others as acceptable alternatives.

Do not recommend a mode simply because a later organisation may have implemented something similar.

---

## 4. Capability-label guide

Select only capabilities that are relevant to the activity and supported by the before-state need.

- **DOCUMENT_INFORMATION_EXTRACTION:** extracting structured information from documents or messages.
- **CLASSIFICATION:** assigning items to categories, labels or routes.
- **PREDICTION_FORECASTING:** estimating a future value, event or outcome.
- **ANOMALY_PATTERN_DETECTION:** identifying unusual cases, patterns or potential exceptions.
- **GENERATIVE_AI:** creating or transforming text or other content.
- **KNOWLEDGE_RETRIEVAL:** locating relevant information from an approved knowledge source.
- **RECOMMENDATION:** suggesting options or possible actions.
- **DECISION_SUPPORT:** helping a human evaluate evidence or make a judgement.
- **COMPUTER_VISION:** interpreting images or visual material.
- **WORKFLOW_AUTOMATION:** moving information or triggering structured workflow actions.

Selecting a capability does not automatically mean that the activity should be automated.

---

# Case Review Questionnaire

## 5. Whole-process review

Review the complete proposed activity list before answering.

### 5.1 Overall process coverage

Does the activity list represent the identifiable current-state process described in the before packet?

- [ ] Accept as written
- [ ] Accept with minor corrections
- [ ] Material changes required
- [ ] Insufficient information to determine

### 5.2 Missing activities

- [ ] No material activity appears to be missing.
- [ ] One or more material activities are missing.
- [ ] The evidence is insufficient to determine completeness.

If missing, identify the activity and supporting evidence:

| Proposed new ID | Missing activity | Position in process | Supporting evidence | Rationale |
|---|---|---:|---|---|
| | | | | |

### 5.3 Activity splitting and merging

- [ ] Activity boundaries are appropriate.
- [ ] One or more activities should be split.
- [ ] One or more activities should be merged.
- [ ] An activity should be removed as unsupported or duplicative.
- [ ] The evidence is insufficient to determine the boundary.

Record exceptions only:

| Existing activity ID(s) | Split, merge or remove | Proposed boundary | Supporting evidence | Rationale |
|---|---|---|---|---|
| | | | | |

### 5.4 Ordering

- [ ] The proposed ordering is supported.
- [ ] The order requires correction.
- [ ] Some activities are parallel, conditional or unordered.
- [ ] The evidence is insufficient to establish the order.

Record corrections or dependencies:

| Activity ID | Proposed predecessor or dependency | Supporting evidence | Comment |
|---|---|---|---|
| | | | |

---

## 6. Activity and evidence review

Review every proposed activity using **one** of the following alternatives.

### Activity ID: __________  Activity name: ____________________

### Alternative A — Accept activity as presented

Select this single grouped confirmation only when the activity requires no correction:

- [ ] **I have reviewed this activity as presented and accept it without amendment.**

This grouped acceptance confirms that the reviewer has substantively considered and accepts:

- the activity definition and boundary;
- its ordering or dependency, where applicable;
- its actors;
- its systems;
- its inputs and outputs;
- whether the cited evidence supports each material assertion; and
- its known, inferred, unknown or supported-empty classifications.

The reviewer does **not** need to tick separate field-level boxes before selecting grouped acceptance.

### Alternative B — Record exceptions or corrections

Select this alternative when any field is incorrect, unsupported, ambiguous or requires amendment:

- [ ] **This activity requires one or more exceptions or corrections recorded below.**

Record only the affected fields. Fields not listed in the exception table are treated as reviewed and accepted as presented.

| Field or assertion | Primary proposed value | Reviewer value or proposed amendment | Evidence supports primary value? | Appropriate knowledge state | Evidence or rationale |
|---|---|---|---|---|---|
| | | | Yes / Partly / No / Unclear | Known / Inferred / Unknown / Supported empty | |

Add rows as required. Repeat Section 6 once for each proposed activity.

---

## 7. Independent AI-adoption judgement

Complete one row for every final reference activity. Record this judgement without seeing the primary annotator’s decision judgement.

| Activity ID | Primary recommendation mode | Acceptable alternative modes | Applicable capabilities | Human oversight required? | Automation unsafe? | Conventional/non-AI solution preferable? | Relative priority | Important missing information or rationale |
|---|---|---|---|---|---|---|---|---|
| | | | | Yes / No / Unclear | Yes / No / Unclear | Yes / No / Unclear | Rank / tie / not rankable | |

### Guidance

- **Human oversight required:** select Yes where an accountable person should actively review, approve, decide, communicate, or manage material exceptions.
- **Automation unsafe:** select Yes where replacing the relevant human activity with automation could create unacceptable harm, loss, control failure or accountability risk.
- **Conventional solution preferable:** select Yes where clearer procedures, validation rules, ordinary software, workflow redesign, integration, training or another non-AI intervention better addresses the documented need.
- **Relative priority:** rank opportunities within this case, with `1` as highest priority. Ties are allowed. Use “not rankable” where the evidence is insufficient.
- Do not manufacture a ranking from missing information.

---

## 8. Unresolved ambiguity

List any issue that cannot be resolved responsibly from the before packet.

| Activity ID or process-level issue | Ambiguity or missing information | Why it matters | Recommended treatment |
|---|---|---|---|
| | | | Unknown / Dual label / Not rankable / Blocks reference completion |

### Overall reviewer conclusion

- [ ] Accept the reference without material change.
- [ ] Accept after the listed corrections.
- [ ] Material adjudication is required.
- [ ] The reference cannot yet be completed from the available evidence.

Reviewer comments:

____________________________________________________________________

Reviewer signature or recorded confirmation: __________________________

Date: ____________________

---

# Disagreement and Adjudication Form

Create one record for each substantive disagreement. Original judgements must remain unchanged in their source records.

## 9. Disagreement record

Case ID: ____________________

Activity ID or process-level item: ____________________

Field or judgement under review:

- [ ] Activity existence or boundary
- [ ] Activity ordering or dependency
- [ ] Actor, system, input or output
- [ ] Evidence support
- [ ] Known/inferred/unknown classification
- [ ] Primary recommendation mode
- [ ] Acceptable alternative modes
- [ ] Capability label
- [ ] Human-oversight requirement
- [ ] Unsafe-automation judgement
- [ ] Conventional-solution preference
- [ ] Relative priority
- [ ] Other: ____________________

Primary annotator’s original judgement:

____________________________________________________________________

Primary annotator’s evidence and rationale:

____________________________________________________________________

Independent reviewer’s original judgement:

____________________________________________________________________

Independent reviewer’s evidence and rationale:

____________________________________________________________________

Material effect on evaluation, if any:

____________________________________________________________________

## 10. Consensus discussion

Adjudication date: ____________________

Participants: ____________________

Evidence considered: ________________________________________________

Outcome:

- [ ] Primary judgement retained
- [ ] Reviewer judgement adopted
- [ ] New consensus judgement
- [ ] Multiple acceptable labels retained
- [ ] Changed to unknown
- [ ] Changed to not rankable
- [ ] Unresolved but non-blocking
- [ ] Unresolved and blocks reference completion

Final adjudicated value:

____________________________________________________________________

Reason for the outcome:

____________________________________________________________________

If unresolved, explain why and how it will be reported:

____________________________________________________________________

Primary annotator confirmation: ____________________  Date: __________

Independent reviewer confirmation: _________________  Date: __________

## Record-preservation rule

The adjudicated value is a new record. It must not replace or obscure either person’s original judgement. Every final reference item must remain traceable to:

1. the frozen before-state evidence;
2. the primary annotator’s original judgement;
3. the independent reviewer’s original judgement; and
4. the recorded adjudication outcome.
