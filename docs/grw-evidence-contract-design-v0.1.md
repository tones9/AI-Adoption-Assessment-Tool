# GRW evidence contract — design proposal

Status: **DESIGN ONLY — NOT APPROVED, NOT IMPLEMENTED**  
Version: v0.1  
Date: 2026-08-20  
Scope: proposed contract and product behaviour for the optional Gap Resolution
Workspace (GRW). This document makes no production-code, schema, policy,
taxonomy, prompt, migration, evaluation, or portfolio change.

## 1. Decision and product principle

The Engine must give a customer a useful Decision Package from their normal
process-document upload. That package states what can responsibly be concluded
now, including uncertainty and `InformationGap` records. GRW is the optional
next step for strengthening a later decision; it is not an intake requirement
and it must not become a prerequisite for receiving value.

> The customer should receive useful value from the first process-document
> upload. Gap Resolution improves the strength of the decision; it is not a
> prerequisite for obtaining one.

> The purpose of Gap Resolution is to identify the minimum trustworthy
> additional evidence needed to improve the next decision, not to maximise the
> amount of data collected.

The desired conversation is therefore:

```text
Normal process documentation → initial assessment → Decision Package
                                                  ↓
                    “This appears to be a potential AI-adoption opportunity,
                 but stronger evidence is required before a more confident
                               recommendation can be made.”
                                                  ↓
                           optional, prioritised GRW questions
                                                  ↓
                          reviewed evidence → reassessment → successor package
```

The design does not assume that more evidence produces a more favourable
answer. A successor can remain `INVESTIGATE_FURTHER`, become more strongly
supported, become less favourable or `DO_NOT_RECOMMEND`, and expose different
gaps.

## 2. Verified current boundary

The following current semantics are constraints on this proposal.

| Current construct | Verified meaning | GRW consequence |
|---|---|---|
| `KnowledgeState` | `KNOWN`, `INFERRED`, or `UNKNOWN` describes the state of an assessed value. Unknown values are null and are never imputed. | It is not an evidence-strength scale. An estimate can support a known, inferred, or still-unknown value only through an explicit reviewed mapping. |
| `InformationOrigin.DOCUMENT_SUPPORTED` | A reviewed assertion has resolved evidence from the reviewed source document. A known document-supported assertion requires that evidence. | Do not label a customer statement, unreviewed attachment, or dataset as document-supported merely because a human says it is true. |
| `InformationOrigin.HUMAN_SUPPLIED` | A current Phase 4 manual correction with no document evidence. The current model prohibits it from carrying document evidence, and Phase 4 projection deliberately supplies no evidence IDs for it. | Do not silently repurpose it as a general GRW provenance label or use it to make a gate appear evidenced. |
| `InformationOrigin.MODEL_INFERRED` | An inferred reviewed value requiring confidence. | It remains distinct from a customer answer or a deterministic computation over new data. |
| `EvidenceReference` | Current assessment evidence is a document-oriented reference: source ID, locator, exact supporting snippet, provenance, state and uncertainty. | It is not yet a generic record for a customer response, dataset, calculation, or attestation. A future GRW contract needs a separate generic evidence record rather than overloading this model. |
| `InformationGap` | A frozen Phase 6 record linked to a step, field, knowledge state, materiality flags and assessment/review/evidence paths. Kinds include unknown input, material inference requiring confirmation, incomplete priority and investigation required. | It is a traceable reason to consider a question, not itself a customer prompt, a priority category, or proof that one answer resolves it. |
| Decision policy v0.2 | A material gate input must be known/inferred within confidence rules and have evidence IDs. Gates stop in order: evidence sufficiency, technical fit, business value, then risk and autonomy. | Current policy has no provenance-tier admissibility. GRW must not create a hidden exception to it. |

In particular, the current Phase 4-to-assessment projection can consume
document-supported criterion evidence, but it cannot honestly represent a
customer estimate, a structured attestation, or a measured result as a
gate-satisfying input. Phase 9A identified this boundary. This design extends
that analysis; it does not change the current policy or claim that the current
product already supports GRW evidence.

## 3. Three separate questions

Every GRW item must keep the following questions separate. A `yes` to one does
not imply a `yes` to either of the others.

| Question | Meaning | Example |
|---|---|---|
| Was information supplied? | A customer submitted an answer, document, dataset, result, or explicit unknown. | “Usually 18,000–22,000 tickets per month.” |
| What is its provenance and strength? | What kind of source it is, how it was produced, and what limits attach to it. | An accountable operator's unverified range: `OPERATOR_PROVIDED_ESTIMATE`. |
| Is it admissible for this criterion and gate? | The versioned decision policy says whether reviewed evidence of this kind may support a particular assertion or gate use. | The estimate may support opportunity context but not a measured error-rate claim or a high-consequence autonomy gate. |

This separation prevents two recurring errors: rejecting useful customer
context merely because it cannot clear a gate, and treating supplied text as
if it automatically cleared one.

## 4. What a customer may supply

The workspace should accept the lightest useful input first. Each submitted
item is immutable after submission, retains its verbatim content, submitter and
time, and can be reviewed, rejected, or leave the original unknown intact.

| Customer input | Initial record | Proposed provenance/strength treatment | Important limitation |
|---|---|---|---|
| Plain-English estimate or range | Verbatim text plus optional structured observation (quantity, unit, time period, qualifier and range) | `OPERATOR_PROVIDED_ESTIMATE` | Useful context, not measured data and not automatically an ordinal criterion value. |
| Plain-English factual answer | Verbatim statement, optional accountable role and source hint | `OPERATOR_PROVIDED_FACT` | A stated fact is still a human claim unless a document, system result, or other verification supports it. |
| Structured operator response | Versioned question ID, response, answer options/anchors, accountable role, time and declaration | `STRUCTURED_ATTESTATION` when the record is complete; otherwise the applicable operator-provided category | Structure improves traceability; it does not automatically make a claim measured or universally gate-admissible. |
| Existing company document | Immutable document identity, content hash, locator, quoted passage and reviewer linkage | `DOCUMENT_SUPPORTED` after a reviewer confirms the cited passage supports the specific claim | The document can be incomplete, stale or out of scope; a location alone is not semantic validation. |
| CSV or other data export | Immutable dataset identity, content hash, source system/owner, field description, coverage and access status | `DATASET_SUPPLIED` is a source state, not an evidence-strength conclusion | A file upload alone is not a measured result. It may be invalid, incomplete, incorrectly scoped or uninterpreted. |
| Measured operational result | Source dataset/report, content hash, time window, population/denominator, calculation method/version, result and reviewer validation | `MEASURED` only when the result is reproducible from a verifiable operational source | A dashboard screenshot or an unsupported aggregate is not automatically measured. |
| Explicit “I do not know” | Verbatim unknown response, optionally with reason or proposed later owner | `UNKNOWN` / explicit-unknown outcome, not weak evidence | It retains unknown; it must never be converted to zero, a negative answer, or a failure to cooperate. |

`DATASET_SUPPLIED` is deliberately a handling state rather than a final
strength category. It prevents the system from claiming that a CSV became
measured merely because it was uploaded. Likewise, an existing document is
only `DOCUMENT_SUPPORTED` after a reviewer links the relevant passage to the
claim.

## 5. Proposed provenance and evidence-strength vocabulary

The following are proposed GRW concepts, not changes to the existing
`InformationOrigin` enum. Exact enum names can be decided when the contract is
approved, but the distinctions are required.

| Proposed label | Meaning | Required traceability | Must not be presented as |
|---|---|---|---|
| `UNKNOWN` | No justified answer is available, including an explicit “I do not know.” | Linked gap, response (if any), reason and reviewer decision. | A zero value, an adverse answer, or a requirement to guess. |
| `OPERATOR_PROVIDED_ESTIMATE` | An approximate judgement, range or qualitative frequency supplied by a person. | Verbatim answer; optional role, scope/timeframe and stated basis. | Measured operational data or document evidence. |
| `OPERATOR_PROVIDED_FACT` | A person asserts a concrete fact in normal language without the stronger anchored record required for an attestation. | Verbatim statement; person/role if available; source hint and review result. | Independently verified fact, document evidence, or an attestation merely because it sounds precise. |
| `STRUCTURED_ATTESTATION` | A named, accountable responder answers a versioned and anchored question, with the exact question, anchors, response and time retained. | Instrument/version, question, answer, accountable role/identity, timestamp and review. | A free-text opinion or operational measurement. |
| `DOCUMENT_SUPPORTED` | A source document supports the precise reviewed assertion. | Document identity/hash, locator, excerpt, reviewer and assertion link. | A source that has merely been uploaded or a customer recollection of a document. |
| `MEASURED` | A reproducible result from verifiable operational data. | Source identity/hash, source system, scope/timeframe, population/denominator, transformation/calculation version, result and review. | A raw CSV, dashboard screenshot, estimate, or single anecdote. |
| `DERIVED` | A deterministic calculation or mapping over accepted inputs, with its rule version and all upstream evidence retained. | Rule/instrument version, inputs, calculation/mapping and reviewer treatment where required. | Independent source evidence or a way to hide an estimate behind a score. |

These labels are not a universal ranking. Relevance to the question, recency,
coverage, scope, internal consistency, and review result all matter. For
example, a recent measured value from the wrong population can be less useful
than a directly relevant document statement. The invariant is narrower and
more important: no lower-strength source is silently promoted to a stronger
one.

### 5.1 Relationship to current origins

Future GRW provenance must coexist with, rather than replace, current origin
semantics:

- `HUMAN_SUPPLIED` remains the current unstructured Phase 4 correction
  origin. It must not become an alias for estimate, attestation or measurement.
- Current `DOCUMENT_SUPPORTED` continues to mean a reviewed assertion backed
  by the resolved document evidence required today. A future supporting-company
  document would need the same explicit source-and-claim linkage before it can
  receive that label.
- `MODEL_INFERRED` continues to express the existing inference path and
  confidence rule. A `DERIVED` result is not a model inference unless an
  approved future contract explicitly says so.
- `KnowledgeState.UNKNOWN` remains the only honest assessed state where no
  approved assertion is justified. The existence of a response does not change
  it by itself.

## 6. Customer interaction and evidence escalation

The customer should see a small, prioritised set of plain-language questions,
each explaining why it matters, what the current package can still say without
an answer, and the lightest known route that could help.

For ticket routing, the workspace should ask:

> About how many tickets does your team handle in a typical month? A range or
> best estimate is okay.

not “Provide monthly transaction volume.” It should ask:

> Roughly how often are tickets sent to the wrong team? An estimate is fine if
> you do not know the exact percentage.

not “Provide historical routing error-rate distribution.”

The default evidence route is contextual and progressive, not an immediate CSV
request:

```text
Can a cited existing document answer this?
        ↓ no
Can an accountable person provide an estimate, fact or structured answer?
        ↓ insufficient for the intended use
Would a focused supporting document clarify it?
        ↓ insufficient or verification is required
Is the minimum relevant operational export or reproducible measure necessary?
        ↓ unavailable or disproportionate
Retain UNKNOWN and explain the remaining decision limitation
```

The route is neither a checklist nor a fixed strength ladder. The policy and
question determine the lightest admissible source. For example, a field-list
description from a system owner may establish the next data-readiness question;
a reported historical routing error rate requires an explicit denominator and
usually stronger, reproducible operational evidence before it can be called
measured.

GRW must be able to say:

> Your estimate strengthens our understanding of scale. Verified operational
> data would still be required before this criterion can support a stronger
> adoption decision.

That message is a transparent admissibility outcome, not a demand for data.

## 7. Natural-language ranges and deterministic parsing boundary

Natural language remains an input, not an implicit measurement. A parser may
produce a structured *observation candidate* to reduce transcription burden;
it may not produce a final criterion value or recommendation.

| Customer wording | Safe structured representation | Not permitted automatically |
|---|---|---|
| “roughly 20k per month” | stated magnitude `20,000`; unit `tickets`; period `month`; qualifier `roughly`; exactness `approximate` | Treating it as exactly 20,000, or silently selecting a 0–5 repetition band. |
| “usually 10–15%” | lower `10`; upper `15`; unit `percent`; explicit/required denominator; qualifier `usually` | Turning it into 12.5%, a verified error rate or a business-value score. |
| “rarely” | verbatim qualitative frequency; optional unresolved reference period | Mapping it to a numerical frequency or criterion band. |
| “around five minutes” | stated duration `5`; unit `minutes`; qualifier `around`; context/task if supplied | Treating it as a time study or a precise savings calculation. |

Deterministic parsing may identify numbers, units, ranges, durations, percent
signs, periods and explicit qualifiers. It must preserve the raw response and
return “ambiguous” where a referent, denominator, period, population or unit is
missing. It may validate obvious format errors. It must stop before:

- deciding what the answer means for a particular workflow;
- deciding it applies to every process step;
- converting qualitative language to a score; or
- mapping an approximate observation to an ordinal criterion band.

Those acts require a human reviewer, and—where a 0–5 input is proposed—a
versioned criterion instrument that exposes its question, anchors and mapping.
The reviewer may accept the observation as context, map it under that
instrument, request clarification, reject it, or retain the original value as
unknown. The raw answer remains visible in every case.

## 8. Gap prioritisation: retain all, ask only what matters now

Phase 6 can retain every `InformationGap`; PORT-004 showed why this is
important for auditability. GRW should form a separate customer-facing work
queue rather than expose raw technical gaps one by one.

| Priority category | Meaning | Initial mapping guidance |
|---|---|---|
| `DECISION_CRITICAL` | Missing evidence directly prevents evaluation of the current earliest material gate, could change the recommendation, or concerns a high-consequence risk/autonomy decision. | Start from a material-to-recommendation gap and the actual failing/not-evaluated gate. Consolidate several technical gaps into one understandable root-cause question where possible. |
| `DECISION_STRENGTHENING` | Evidence could materially clarify confidence, opportunity scale, business case or prioritisation but is not needed to make the present limited conclusion. | Includes a material inference needing confirmation or information useful for prioritisation once the gate path allows it. |
| `EXECUTION_STAGE` | Information is relevant to a business case, pilot, governance, integration or deployment after an organisation elects to proceed. | Often derived from material-to-planning gaps or roadmap needs; defer by default. |
| `SUPPORTING / LOW_PRIORITY` | Useful context without an immediate decision effect. | Keep available but collapsed; do not make it a required answer. |

The classification should consider the gap's `basis` paths, materiality flags,
current recommendation, gate order, criterion role, whether one response can
address several gaps, anticipated evidence burden, and timing. An
`INVESTIGATION_REQUIRED` gap is an outcome summary, not automatically a new
customer question; GRW should connect it to its underlying unknown or
insufficient criterion gaps rather than duplicate it.

No percentage of answered questions can establish decision readiness. One
unresolved `DECISION_CRITICAL` risk may matter more than many resolved
supporting items. Priority order describes what to offer first, not how to
manufacture completeness.

## 9. Future evidence-policy admissibility

Current policy v0.2 has a binary material-evidence-reference rule. A future
policy version should make the missing judgement explicit: *what kind of
reviewed evidence is acceptable for which claim and gate?* This is a proposal
for the policy shape, not a proposed change to `decision_policy.v0.2.json`.

For each criterion and gate use, a versioned evidence-admissibility policy
should declare at least:

| Policy element | Purpose |
|---|---|
| Policy/instrument ID, version and fingerprint | Pins the rule that the successor assessment used. |
| Criterion and gate/decision use | Distinguishes a contextual observation, a priority input, a material gate input and a high-consequence decision. |
| Accepted provenance categories | Names the strengths that may be considered, without making all supplied information gate-sufficient. |
| Required record attributes | For example: responder accountability; document passage; dataset hash; timeframe; population/denominator; calculation method; source-system declaration. |
| Required review/approval roles | Requires appropriate accountable, risk, legal, security or subject-matter review where the claim warrants it. |
| Permitted transformation | States whether the evidence may only inform narrative context, may map through an instrument to a criterion, or may satisfy a material gate. |
| Limits and escalation instruction | States what it cannot establish and the lightest stronger evidence route. |

Illustrative policy decisions—not current rules—would include:

- A monthly volume estimate could be accepted as `OPERATOR_PROVIDED_ESTIMATE`
  for opportunity context or a carefully labelled preliminary business-value
  input, while a stronger claim about realised savings needs a reproducible
  measure.
- A verified routing error rate needs a defined numerator, denominator,
  timeframe and method. An estimate can describe the suspected problem but
  must not be displayed as a verified error rate.
- Data readiness may be partially supported by a structured accountable answer
  and a reviewed system/field description. Whether that is enough for the
  technical-fit gate is a policy decision, not an interface decision.
- Risk consequence, residual risk, human judgement and human accountability
  should require explicit accountable review, with stronger provenance or
  corroboration where a high-consequence decision demands it. An optimistic
  estimate must never silently clear an autonomy safeguard.
- AI capability fit retains its separate relationship to mapped capabilities.
  Customer operational information must not manufacture a capability signal.

The engine must return one of three transparent statuses for each reviewed
item: **recorded but not admissible for this use**, **admissible for limited
context or criterion mapping**, or **admissible for the specified gate**. The
policy must be evaluated before, not after, a desired recommendation is known.

## 10. Reassessment and immutable lineage

GRW does not edit a Decision Package, approved review, assessment or source
document. It creates a successor lineage only when a human authorises specific
reviewed items for use.

```text
immutable baseline Decision Package
        ↓ optional GRW workspace linked to original gap IDs
immutable submitted evidence / explicit unknown responses
        ↓ human evidence-and-mapping review
accepted, rejected or unknown-retained resolution assertions
        ↓ explicit reassessment approval (selected assertions + policy version)
immutable successor approved review
        ↓ existing deterministic assessment against that successor
immutable successor Decision Package + read-only comparison
```

The comparison must identify:

- baseline and successor package, review, assessment and policy identifiers;
- every newly supplied item, its raw answer/source reference, provenance and
  evidence strength;
- the reviewed assertion produced, rejected, or retained unknown;
- criterion state and evidence changes;
- the first gate whose result changed, if any, and later gates that consequently
  became evaluable or remained unavailable;
- recommendation and priority changes, or an explicit explanation of why there
  was none; and
- new, resolved and still-open `DECISION_CRITICAL` gaps.

The approval boundary is essential. A customer response is not an assessment
input merely because it was submitted. A reviewer does not by themselves
authorise a rerun. The decision owner selects the approved assertions, pins the
policy/instrument versions and authorises a successor assessment. The system
must record when the same person supplied, reviewed and approved evidence; it
must not imply independent review that did not occur.

Until a future approved contract implements new evidence types and a matching
admissibility policy, a genuine GRW reassessment cannot route an estimate or
measurement through today's Phase 4 projection by pretending it is
document-supported evidence. The correct current outcome remains the baseline
package with its unknowns.

## 11. Boundary with the future AEL

GRW asks: **“Do we now know enough to make a better AI-adoption decision?”**

The future Adoption Execution Layer (AEL) asks: **“We decided to pursue it;
what happens next?”** It would govern initiatives, business cases, pilots,
implementation, deployment and measured outcomes.

Some information overlaps—for example, routing-field availability may later
help a pilot—but the purpose and timing are different. GRW may identify that
such information would strengthen a decision. It must not create an initiative,
pilot, deployment record, benefits-realisation claim or AEL hand-off merely
because a recommendation exists. AEL remains future and out of scope.

## 12. Smallest useful implementation milestone (M1)

**M1: one optional, end-to-end evidence-strengthening loop for one
`DECISION_STRENGTHENING` gap, including a successor comparison that may
correctly remain `INVESTIGATE_FURTHER`.**

Recommended scenario: an existing Decision Package asks, “About how many cases
do you handle in a typical month? A range is okay.” A customer responds,
“Usually around 18,000–22,000 per month.” The milestone must preserve that
text as an estimate, not a measured count.

M1 should contain only:

1. The unchanged baseline package, one linked original `InformationGap`, and a
   prioritised plain-language question with estimate/range and “I do not know”
   options.
2. An immutable raw response and a proposed structured observation retaining
   its range, period and approximate qualifier.
3. Human review that records one of: accepted as estimate/context, rejected,
   or unknown retained; no automatic 0–5 mapping.
4. A narrowly approved, versioned admissibility-policy row that states exactly
   what the estimate may inform. It should not let the estimate clear unrelated
   material gates.
5. Explicit reassessment authorisation, successor approved-review/assessment/
   package lineage, and a read-only baseline-to-successor comparison.

M1 is successful if the provenance, approval and comparison behaviour is
truthful—even if the successor remains `INVESTIGATE_FURTHER` because technical,
data, business or risk evidence is still insufficient. It should deliberately
avoid bulk uploads, general dataset processing, a full question catalogue,
multi-user workflow, AEL entities and any pressure to resolve every gap.

Implementing even M1 requires a separately approved change plan because the
current models and policy cannot represent its new evidence path honestly.
That future plan must specify the necessary contract, projection, policy,
reporting, test and production-fingerprint changes; none are made here.

## 13. Unresolved decisions and risks

1. **Admissibility policy:** Which provenance categories may satisfy which
   criterion/gate uses, and with what role separation or corroboration? This is
   the central future policy decision.
2. **Criterion instrument:** Which anchored questions and mappings may turn a
   reviewed observation into a 0–5 criterion value? No free-text answer should
   receive an implicit score.
3. **Semantic evidence validation:** A document locator proves source location,
   not necessarily that a passage supports the asserted value. High-consequence
   assertions need proportionate reviewer controls.
4. **Measurement validation and data handling:** Dataset provenance, scope,
   privacy, retention, access, calculation reproducibility and security need a
   distinct design before CSV/export intake is implemented.
5. **Priority policy:** The four categories need transparent mapping rules and
   human-readable explanations, but not a target completion percentage or an
   optimisation toward a preferred recommendation.
6. **Roles and authority:** A local/single-user workflow may combine supplier,
   reviewer and approver. The system must disclose that fact and future policy
   must decide when separation is mandatory.
7. **Fingerprint boundary:** Any later production implementation will change
   the production fingerprint. Frozen portfolio cases and their historical
   product outputs must stay unchanged and must not be described as exercising
   GRW.

