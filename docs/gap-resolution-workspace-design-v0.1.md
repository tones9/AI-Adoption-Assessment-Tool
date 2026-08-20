# Gap Resolution Workspace (GRW) — design proposal

Status: **PROPOSAL — NOT APPROVED, NOT IMPLEMENTED**  
Version: v0.1  
Revised: 2026-08-20  
Scope: design only. No production code, schema, policy, migration, prompt, taxonomy, or evaluation artefact is changed by this document.

## 1. Purpose and design history

The Gap Resolution Workspace (GRW) is an optional, customer-facing evidence-strengthening workspace that begins after a Phase 6 `DecisionSupportPackage`.

The customer must receive a useful, evidence-based decision package from their first process-document upload. GRW does not make the initial product usable; it gives the customer a controlled way to strengthen a decision later when doing so is worthwhile.

> **Product principle:** The customer should receive useful value from the first process-document upload. Gap Resolution improves the strength of the decision; it is not a prerequisite for obtaining one.

> **Collection principle:** The purpose of Gap Resolution is to identify the minimum trustworthy additional evidence needed to improve the next decision, not to maximise the amount of data collected.

The intended customer experience is:

```text
Process documentation
        ↓
Initial AI opportunity assessment
        ↓
Decision Package
        ↓
“Here is what we can responsibly conclude now”
        +
“Here are the specific facts that would most strengthen the decision”
        ↓
Optional Gap Resolution
        ↓
Reassessment
        ↓
Stronger, unchanged, or weaker recommendation
```

### 1.1 Why GRW was discovered

GRW was discovered during portfolio and product validation; it was not part of the original architecture.

The original engine correctly preserves `UNKNOWN` values and creates explicit `InformationGap` records rather than inventing evidence. PORT-004 demonstrated that behaviour end to end: the package was valid and useful, while correctly reporting `COMPLETE_WITH_INFORMATION_GAPS`, 174 missing-information entries, and no quantified ROI.

Validation exposed the next product problem: the system could identify what it did not know, but had no controlled, user-friendly mechanism for customers to strengthen those gaps and request reassessment. GRW is therefore a discovered product extension. It must not later be represented as though it had been part of the original engine from day one.

GRW does not attempt to make recommendations pass. It may confirm the original conclusion, make it more cautious, or support a more specific recommendation. `INVESTIGATE_FURTHER`, `AUGMENT`, `AUTOMATE`, and `DO_NOT_RECOMMEND` are all valid reassessment outcomes.

## 2. Relationship with the existing product

GRW is a named product extension, not a new formal numbered phase. Existing phase numbering has established meanings and is unchanged.

| Existing phase | Existing responsibility | GRW relationship |
|---|---|---|
| 1 | Deterministic gates, recommendation and priority scoring | Remains authoritative. GRW supplies a newly approved input revision only when a customer elects to strengthen evidence. |
| 2 | Ingestion and source locators | Supplies existing-document evidence. GRW should refer to source locators; it must not duplicate or rewrite source text. |
| 3 | Candidate extraction | Remains the origin of extracted process facts and resolved snippets. GRW does not re-extract merely because a gap exists. |
| 4 | Human review and explicit approval | Remains the canonical correction and approval boundary. Approved GRW assertions may form a successor review revision. |
| 5 | Integrated assessment and traceability | Runs again only on an explicitly approved successor review. Baseline assessments remain immutable. |
| 6 | Decision package, information gaps, roadmap and report | Creates the baseline customer value and the optional GRW intake. A successor package is created only after reassessment. |
| 7 | Local workspace, persistence and UI | Would host the first GRW surface, following the existing append-only artefact and active-pointer approach. |
| 8 | Frozen evaluation | Remains isolated. GRW never edits frozen evaluation artefacts or treats later evidence as part of a historical baseline. |

GRW asks:

> Do we now have enough evidence to make a stronger adoption decision?

The future Adoption Execution Layer (AEL) asks:

> Now that the organisation has chosen to proceed, how do we govern, pilot, implement and measure it?

Some facts may be useful to both, but their timing and purpose differ. GRW establishes decision readiness; AEL manages execution after an explicit human choice to proceed.

## 3. Customer workflow and gap prioritisation

### 3.1 Initial value is unconditional

The Decision Package remains the primary first outcome. It must:

- state what the engine can responsibly conclude from the submitted process documentation;
- show recommendations, reasoning, evidence and uncertainty;
- explain any important information limitations in clear business language; and
- be delivered even when the customer supplies no additional information.

GRW is an optional next action. The product must never say, imply, or require that every gap be resolved before a customer can receive an assessment. A customer can close GRW immediately and retain the original package as their valid decision baseline.

### 3.2 Retain all gaps; prioritise the customer view

The product may retain every `InformationGap` internally for traceability, reporting and later use. The customer-facing GRW should not present a flat backlog of raw technical gaps. It should prioritise and group them into these conceptual categories:

| Customer-facing category | Meaning | Customer treatment |
|---|---|---|
| `DECISION_CRITICAL` | Missing evidence could materially block, constrain, or change the current recommendation. | Show first. Explain the decision consequence and ask the lightest useful question. |
| `DECISION_STRENGTHENING` | Evidence could materially increase confidence, clarify business value, or improve the adoption assessment. | Present as optional, high-value strengthening work. |
| `EXECUTION_STAGE` | Information is useful for a later business case, pilot, implementation, governance, or deployment decision, but need not block the current assessment. | Defer until the organisation is ready for that stage; do not burden the initial assessment. |
| `SUPPORTING / LOW_PRIORITY` | Useful context that does not need immediate resolution. | Keep available but collapsed or deferred by default. |

These categories are explanation and ordering tools, not a numerical completion score. No percentage of resolved gaps is automatically sufficient. One unresolved critical risk gap may matter more than a hundred resolved supporting gaps.

### 3.3 Priority rationale

Each prioritised GRW item should retain a human-readable explanation of:

- the linked internal `InformationGap` and process activity;
- whether it affects a recommendation, priority, confidence, or only a later execution decision;
- the decision or gate that could be affected;
- what the system can still conclude without it; and
- the lightest acceptable evidence route currently known.

The internal criterion name, `InformationGap` field name, policy paths, and artefact IDs remain available for audit, but are not the primary customer interface.

## 4. Customer questions and the lightest acceptable evidence

### 4.1 Separate the internal model from the customer experience

GRW must preserve four separate concepts:

| Layer | Purpose | Example |
|---|---|---|
| Internal criterion / `InformationGap` | The engine's precise reason for uncertainty | `repetition` unknown for ticket triage |
| Customer-facing question | Plain-language request for a fact the customer can reasonably answer | “About how many tickets does your team handle in a typical month? A range is okay.” |
| Evidence supplied | The customer's verbatim answer, a document reference, or measured data | “Normally 18,000–22,000, higher around renewals.” |
| Resulting criterion assertion | The reviewed, traceable value consumed by the engine, if one is justified | A proposed repetition band, its evidence-strength label, rationale and approval record |

A natural-language answer must be stored verbatim. The product may offer a proposed interpretation, but it must be visible, explainable, and confirmed or reviewed before it becomes a criterion assertion. It must never silently transform “around 20,000” into a precise measured value or silently select a favourable criterion band.

### 4.2 Questions use normal business language

Questions should ask for the smallest understandable fact, state why it is helpful, and make uncertainty safe to express.

Avoid:

> Provide historical routing error-rate distribution.

Prefer:

> Roughly how often are tickets sent to the wrong team? An estimate is fine if you do not know the exact percentage.

Avoid:

> Provide monthly transaction volume.

Prefer:

> About how many cases does your team handle in a typical month? A range is okay.

Appropriate response controls include free-text answers, ranges, “I do not know”, an optional supporting-document link, and an optional indication of who supplied the answer. A CSV upload must never be the default request.

### 4.3 Lightest acceptable evidence route

For each high-priority item, GRW should determine or display the least burdensome evidence route that could improve the next decision. The route is guidance, not a demand for all possible evidence.

```text
Can an existing source document answer the question?
        ↓ yes: cite it as document-supported evidence
        ↓ no
Can an accountable person give a reasonable estimate or structured answer?
        ↓ yes: record the response at its explicit evidence strength
        ↓ no, or not sufficient for this decision
Would a supporting document clarify the fact?
        ↓ yes: invite an optional document reference or upload
        ↓ no, or stronger verification is required
Is measured operational data necessary and proportionate?
        ↓ yes: request only the minimum relevant export or calculation
        ↓ no / unavailable
Retain UNKNOWN and explain what the current package can still conclude
```

The evidence route must distinguish “helpful” from “sufficient for this gate.” An estimate may strengthen a business discussion while remaining insufficient for a high-consequence decision. Conversely, the product must not demand measured data where a credible document citation or accountable estimate would be adequate under the approved policy.

## 5. Evidence-strength model

Evidence strength must remain explicit in the GRW, reassessment comparison, and every successor package that uses new information.

The following are conceptual labels, not final production enum or policy names:

| Evidence strength | Meaning | What it must not be mistaken for |
|---|---|---|
| `UNKNOWN` | No justified value is available. | A failure, blank default, or invitation to guess. |
| `OPERATOR_PROVIDED_ESTIMATE` | A person has supplied an approximate natural-language answer, range, or best judgement. It is useful but unverified. | Measured operational data or a documented fact. |
| `DOCUMENT_SUPPORTED` | The fact is supported by a cited process or supporting document. | Proof that the statement is current, complete, or independently verified. |
| `MEASURED` | The value is derived from verifiable operational data with an identified source, time window and reproducible method. | A guarantee that the resulting recommendation is appropriate. |
| Future: `STRUCTURED_ATTESTATION` | A named accountable person answers a versioned, anchored instrument. | A simple free-text estimate. |
| Future: `DERIVED` | A deterministic rule calculates a value from accepted evidence and retains its inputs and rule version. | Independent evidence or a circular restatement of an existing score. |

This is not a universal linear ranking. Relevance, recency, scope and policy admissibility also matter. For example, a direct document statement can be stronger than an estimate for one fact, while a recent operational measure may be preferable for another. The important invariant is that a lower-strength answer is never silently upgraded to a higher-strength one.

### 5.1 Evidence strength versus policy admissibility

Recording evidence, presenting it to a customer, and allowing it to satisfy a decision gate are separate actions.

The current engine recognises `DOCUMENT_SUPPORTED`, `MODEL_INFERRED`, `HUMAN_SUPPLIED`, and `UNKNOWN`. It does not yet recognise an operator estimate, structured attestation, or measured operational result as a gate-satisfying origin. Any change to that rule requires a separately approved, versioned evidence policy.

The recommended future direction is a tiered policy: each gate and material field declares which evidence strengths it may accept. GRW can still record a lower-strength estimate even when it does not satisfy a current gate; the reassessment comparison must state that outcome plainly.

## 6. Proposed conceptual data model

These are conceptual contracts only, not implementation classes, database tables, schemas, or migrations.

| Concept | Purpose | Key content |
|---|---|---|
| `GapResolutionWorkspace` | Optional mutable container anchored to one immutable baseline package | baseline `package_id`, artefact ID/hash, owner, active items, status and active view preferences |
| `PrioritisedGap` | Customer-facing prioritisation of one retained internal gap | source `gap_id`, category, explanation, decision consequence, recommended evidence route |
| `CustomerQuestion` | Plain-language prompt generated or selected for a prioritised gap | question text, help text, allowed response types, why it matters, instrument/version if applicable |
| `CustomerResponse` | Verbatim customer answer or explicit “I do not know” | response text/range, responder role, timestamp, optional source reference; no inferred strength upgrade |
| `EvidenceRecord` | Immutable, source-specific record of what was supplied | evidence-strength label, source payload, content hash/locator when available, collector and validation state |
| `ResolutionAssertion` | Reviewed proposal for a criterion or accountability value | target field, proposed value or retained unknown, rationale, evidence IDs, mapping explanation and confidence where appropriate |
| `ResolutionReview` | Human decision on the evidence and proposed assertion | reviewer, accept/reject/unknown-retained decision, reasons, conflicts and accepted evidence IDs |
| `ResolutionApproval` | Explicit authorisation to use accepted assertions in one reassessment | approver, selected resolution IDs, baseline package and pinned policy/instrument references |
| `ReassessmentRequest` | Immutable instruction to derive a successor review and run the unchanged engine | baseline lineage, approved resolutions, policy fingerprint and request ID |
| `ReassessmentComparison` | Customer-readable and audit-readable baseline/successor comparison | new evidence, strength, changed criteria, gate changes, outcome changes, unresolved critical items |

Every GRW item retains the baseline package ID, integrated-assessment artefact, reviewed-process revision, step ID, and original gap ID. This prevents evidence from being moved between activities or packages without traceability.

## 7. Gap lifecycle

The lifecycle applies per `PrioritisedGap`. A workspace can contain items at different stages, and customers are free to leave any item unresolved.

```text
RETAINED_IN_PACKAGE
  → OFFERED_OPTIONALLY
  → SELECTED_BY_CUSTOMER
  → RESPONSE_DRAFT
  → SUBMITTED
  → REVIEWED
       ├─ ACCEPTED
       ├─ REJECTED
       └─ UNKNOWN_RETAINED
  → APPROVED_FOR_REASSESSMENT
  → REASSESSED
  → SUPERSEDED or CLOSED
```

- `RETAINED_IN_PACKAGE`: the gap is part of the original decision package; the customer has already received value.
- `OFFERED_OPTIONALLY`: GRW presents a prioritised question or route. No response is required.
- `SELECTED_BY_CUSTOMER`: the customer has chosen to strengthen this decision now.
- `RESPONSE_DRAFT`: the customer may edit an unsubmitted answer, range, document reference, or “I do not know” response.
- `SUBMITTED`: the exact response and evidence-strength claim are fixed for review.
- `REVIEWED`: a qualified reviewer has evaluated relevance, provenance and mapping.
- `ACCEPTED`, `REJECTED`, and `UNKNOWN_RETAINED`: all are explicit and preserved outcomes. Retaining unknown is valid.
- `APPROVED_FOR_REASSESSMENT`: an authorised human selects accepted assertions for one successor run.
- `REASSESSED`: a successor package and comparison exist.
- `SUPERSEDED` or `CLOSED`: a newer package or an explicit decision makes the item inactive; its history remains available.

No rejected or unknown-retained response may be overwritten. A later attempt is a new response/evidence revision linked by supersession.

## 8. Reassessment behaviour

Reassessment is optional and is always a new run; it is never a mutation or recalculation of the baseline package.

1. A customer or decision owner selects only the gaps they want to strengthen.
2. Customer responses and optional supporting evidence are captured with their explicit evidence strength.
3. A reviewer accepts, rejects, or retains each proposed assertion as unknown.
4. A decision owner explicitly authorises a selected set of accepted assertions for reassessment, pinned to a policy version.
5. The product derives a successor Phase 4 review snapshot, applying only approved assertions and retaining the baseline review unchanged elsewhere.
6. The existing Phase 4 approval validation, Phase 5 assessment, and Phase 6 package generation run against the successor artefacts.
7. A `ReassessmentComparison` explains what changed and what did not.

The comparison must state:

- new evidence supplied, including the customer's verbatim response where appropriate;
- evidence provenance and strength;
- each resulting criterion assertion or retained unknown;
- changed gate results, if any;
- why the recommendation changed or stayed unchanged; and
- remaining `DECISION_CRITICAL` gaps, if any.

Additional evidence does not exist to make a recommendation pass. A reassessment may remain `INVESTIGATE_FURTHER`, move to `AUGMENT`, move to `AUTOMATE`, or move to `DO_NOT_RECOMMEND`. All are valid and must be explained from the evidence and policy, not characterised as product success or failure.

## 9. Immutable and mutable state

| Immutable | Mutable while work is in progress |
|---|---|
| Baseline ingestion, extraction, review approval, assessment and decision package | Workspace ownership, customer selection, assignment, due dates and non-evidentiary notes |
| Every original package gap and rationale | Which optional gaps are shown, expanded or deferred in the active GRW view |
| Submitted customer responses, evidence records, reviews, approvals and reassessment requests | Unsubmitted customer-response drafts and requested evidence route |
| Dataset/source identities and content hashes | Active workspace filters and active-pointer selection |
| Policy, instrument and deterministic-rule versions used in an approval or reassessment | Lifecycle status before submission or approval |
| Successor review approval, assessment, package and comparison | Active-pointer selection among immutable revisions |

Mutability ends at submission for a customer response/evidence payload and at authorisation for reassessment scope. Corrections create new linked revisions rather than rewrite history.

This preserves the existing Phase 7 persistence principle: work in progress may be updated, while approval, assessment and package outputs are revisioned snapshots with separate active pointers.

## 10. Human approval points

Automation may validate structural completeness and generate a proposed mapping, but it must not approve evidence, decide that an estimate is measured, or authorise reassessment.

| Approval point | Required human role | Decision |
|---|---|---|
| Optional gap selection | Customer, process owner, or decision owner | Choose whether this gap is worth resolving now; no obligation to select all gaps. |
| Evidence and mapping review | Subject-matter validator or designated reviewer | Decide whether the response supports the proposed assertion; accept, reject, or retain unknown. |
| High-consequence evidence use | Appropriate risk, compliance, security, legal, or accountable business owner, when an approved policy requires it | Confirm evidence strength and intended use meet the relevant gate's admissibility rules. |
| Reassessment authorisation | Decision owner | Select accepted assertions, pin policy/instrument versions and authorise the successor run. |
| Post-reassessment action | Decision owner with relevant oversight roles | Continue investigation, develop a business case, stop, or explicitly hand off to AEL. |

The system must record the roles actually performed. It must not imply independent review when one person performed multiple roles in a local single-user context.

## 11. Ticketing example

This example is illustrative design behaviour. It is not a claim about the current policy or a present product result.

### 11.1 Initial process document and assessment

A customer uploads a service-desk ticket-routing procedure. The document describes agents reading incoming tickets, assigning a category, and transferring tickets between teams when the first assignment is wrong. It provides document-supported evidence that classification and routing are plausible AI capability signals.

The customer receives a Decision Package immediately. It responsibly concludes that routing assistance should be investigated, but returns `INVESTIGATE_FURTHER` because the document does not state the ticket volume, the cost or disruption of misrouting, or whether routing data is available to evaluate an AI-assisted approach.

The package is useful now: it names the candidate workflow, explains that human oversight remains appropriate, and shows why a deployment recommendation is not yet justified.

### 11.2 Optional GRW questions

GRW retains all internal gaps but presents these prioritised items:

| Priority | Plain-language question | Why it matters | Lightest route |
|---|---|---|---|
| `DECISION_CRITICAL` | “Do your ticket records show the original category, final team, and any transfers? A simple description is fine; you do not need to upload data now.” | Determines whether routing quality could later be evaluated and monitored. | Accountable answer first; supporting documentation or a small field-list export only if needed. |
| `DECISION_STRENGTHENING` | “About how many tickets does your team handle in a typical month? A range is okay.” | Helps estimate whether the routing opportunity is material. | Natural-language range. |
| `DECISION_STRENGTHENING` | “Roughly how often are tickets sent to the wrong team? An estimate is fine if you do not know the exact percentage.” | Helps explain the size of the current routing problem. | Natural-language estimate. |
| `EXECUTION_STAGE` | “If you later decide to pilot this, which ticketing system would it need to work with?” | Useful for a later pilot or implementation plan, not needed to assess the current opportunity. | Defer by default. |

### 11.3 Customer answers and evidence strength

The customer answers:

> “We normally receive around 18,000–22,000 tickets per month, with higher volumes around renewal periods.”

> “I don't know the exact percentage, but our support manager estimates that around 10–15% are transferred at least once.”

> “We use Zendesk. We believe it records the original category, final group and transfer history, but I have not checked the exact field names.”

GRW preserves these responses verbatim. It labels all three `OPERATOR_PROVIDED_ESTIMATE`; it does not call them measured data or document-supported facts. A proposed mapping might identify a high-volume repetition band and evidence relevant to business value, but the reviewer must confirm the mapping and may retain any field as unknown.

### 11.4 Reassessment and comparison

The reviewer accepts the volume and transfer-rate answers as useful estimates, but retains data readiness as unknown because the actual record fields have not been verified. The decision owner authorises reassessment of those accepted assertions under the applicable future policy.

The successor comparison shows:

| Comparison field | Baseline | Successor |
|---|---|---|
| New evidence | None beyond process document | Two operator-provided estimates, shown verbatim |
| Evidence strength | `UNKNOWN` for the relevant operational facts | `OPERATOR_PROVIDED_ESTIMATE`, not measured |
| Criterion impact | Repetition and business-value context incomplete | Some context strengthened; data readiness remains unknown |
| Gate impact | Evidence/data readiness blocks a stronger conclusion | Data-readiness condition remains unresolved |
| Recommendation | `INVESTIGATE_FURTHER` | `INVESTIGATE_FURTHER` |
| Explanation | Documentation alone cannot support the next decision | Estimates clarify scale, but verified routing-data availability is still decision-critical |

This is a successful GRW outcome: the customer received value before answering, supplied only lightweight information, and learned the minimum next trustworthy request rather than being asked to upload a full CSV. A later supporting document or measured field verification may create another optional revision; it might strengthen the recommendation, leave it unchanged, or identify a reason not to proceed.

## 12. Boundary with the future AEL

GRW owns: evidence strengthening, provenance, reassessment and comparisons of decision-package revisions.

The future AEL owns: initiatives, business cases, pilot plans, implementation, deployment decisions, controls, measured outcomes and learning across initiatives.

```text
Decision Package → optional GRW → reassessed Decision Package
                                        ↓ explicit human decision to proceed
                                      future AEL initiative
                                        ↓ measured outcomes
                              optional new GRW evidence revision
```

An AEL initiative may receive a selected immutable successor package and its reassessment comparison, but AEL must not edit assessment inputs or backfill earlier evidence. Likewise, an `EXECUTION_STAGE` GRW question may be relevant to a future pilot, but it must not block the customer's initial assessment unless it is genuinely decision-critical now.

## 13. First minimal implementation milestone

**M1: one optional, plain-language evidence-strengthening loop from an existing Decision Package to a successor comparison.**

M1 scope:

1. Open a local GRW from one existing Decision Package; the package remains visible and useful without any GRW response.
2. Show one selected `DECISION_CRITICAL` or `DECISION_STRENGTHENING` gap as a simple optional question, with “estimate or range is okay” and “I do not know” paths.
3. Preserve the internal gap, customer question, verbatim response, evidence-strength label and proposed assertion as separate records.
4. Allow human review to accept, reject, or retain unknown; do not silently map an estimate to a strong evidence class.
5. Require explicit reassessment authorisation and produce a successor approval, assessment, package and read-only comparison only where the approved policy permits the evidence to be consumed.
6. Preserve every baseline artefact unchanged. Create no AEL initiative, pilot, deployment record, API, migration, multi-user workflow, or mandatory dataset-upload flow.

M1 is complete if the optional flow, provenance, approval boundary and comparison are correct. It is complete even when the reassessment cannot consume the new estimate, remains `INVESTIGATE_FURTHER`, or returns `DO_NOT_RECOMMEND`.

## 14. Open decisions and architectural risks

1. **Evidence-policy admissibility:** Which evidence strengths can satisfy which gates and material criteria? This requires a new approved policy version; GRW must not create a hidden exception.
2. **Mapping natural language to an ordinal criterion:** A range or estimate must remain verbatim. The design needs a controlled, reviewable mapping process and a decision about when human confirmation is mandatory.
3. **Semantic evidence quality:** Existing document citations establish location, not necessarily that a cited sentence supports the asserted value. GRW needs proportionate reviewer controls, especially for high-consequence fields.
4. **Question prioritisation:** Categories are defined, but no thresholds are. The future design must avoid arbitrary counts, score-chasing, or optimisation for a desired recommendation.
5. **Customer burden and privacy:** Requests must remain minimal, data minimising, and suitable for the local single-user product. Measured-data intake needs a separate security, retention and access decision before implementation.
6. **Role separation:** A local single-user product may not provide independent review. The system must disclose who supplied, reviewed and approved each assertion rather than imply separation.
7. **AEL hand-off:** The trigger for turning a reassessed package into an AEL initiative must remain an explicit human business decision, not an automatic recommendation transition.

Until these are decided, GRW remains a design proposal only.
