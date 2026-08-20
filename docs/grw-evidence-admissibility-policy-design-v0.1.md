# GRW evidence-admissibility policy — design proposal

Status: **DESIGN ONLY — NOT APPROVED, NOT IMPLEMENTED**  
Version: v0.1  
Date: 2026-08-20  
Scope: a future evidence-admissibility mechanism for the optional Gap Resolution
Workspace (GRW). This document changes no production model, policy, gate,
schema, prompt, taxonomy, migration, evaluation artefact, or portfolio summary.

## 1. Decision to be made

The evidence contract answers what a customer supplied and how it was produced.
This policy answers a separate question:

> For this criterion, for this gate use, what minimum reviewed evidence may
> support the Engine treating the criterion as sufficiently supported?

No source becomes gate-admissible merely because it was supplied, looks precise,
uses a stronger-sounding label, or is newer. The future policy must make its
permitted use explicit before reassessment and preserve that policy version with
the result.

The initial Decision Package remains useful without GRW evidence. GRW is
optional evidence strengthening, not a route to make an assessment pass.

## 2. Verified current boundary

| Current construct | Verified behaviour | Consequence |
|---|---|---|
| KnowledgeState | An assessed value is KNOWN, INFERRED, or UNKNOWN. Unknown requires a null value and is never imputed. | It describes an assessment value's state, not evidence provenance or policy permission. |
| CriterionInput / BooleanCriterionInput | Current inputs contain value, knowledge state, rationale, evidence IDs and optional inferred confidence. | A future strength/admissibility record must be carried separately; an ID alone cannot communicate permission. |
| Phase 4 InformationOrigin | DOCUMENT_SUPPORTED, MODEL_INFERRED, HUMAN_SUPPLIED, and UNKNOWN have established semantics. HUMAN_SUPPLIED cannot carry document evidence and projects with no evidence IDs. | GRW must not silently redefine HUMAN_SUPPLIED or DOCUMENT_SUPPORTED. |
| Current EvidenceReference | It is document-oriented: source ID, locator and exact supporting snippet. | It cannot honestly represent a customer answer, dataset, calculation or attestation without a future contract change. |
| Decision policy v0.2 | Gate-material inputs require an acceptable value/state and non-empty evidence IDs. It has no provenance-tier rule. | Current policy cannot decide whether an estimate, attestation or measurement is admissible for a gate. |
| Gate order | evidence sufficiency → technical fit → business value → risk and autonomy. The first blocking gate ends evaluation. | Admissibility must apply to the material inputs of the gate actually reached; later gates may remain not evaluated. |
| Phase 5 traceability | Assessment lineage pins source document, review approval, validated-process fingerprint and decision-policy fingerprint. | A successor needs equivalent lineage plus GRW evidence, review/approval decisions and an admissibility-policy fingerprint. |
| Phase 6 InformationGap | A gap retains step, field, knowledge state, materiality flags and evidence/review/assessment paths. | A gap is a traceable reason to consider a question, not a customer prompt, admissibility decision or proof that one answer resolves it. |

Phase 9A correctly identifies the current boundary: document-supported criterion
evidence can reach the engine, while a human-supplied correction cannot satisfy
the material-evidence requirement. It also warns that a valid document locator
does not itself prove that the cited text semantically supports the criterion.
GRW must not bypass either control.

## 3. Evidence classes and policy roles

The following are future GRW concepts, not new production enums and not
replacements for InformationOrigin.

| Evidence class | What it records | Baseline policy posture |
|---|---|---|
| UNKNOWN | No justified answer, including an explicit “I do not know.” | Never resolves a criterion or satisfies a gate. It is an honest outcome. |
| OPERATOR_PROVIDED_ESTIMATE | A verbatim approximate answer, range, best judgement or qualitative frequency. | Always recordable and useful contextual evidence; never presumed to establish a measured fact or clear a material gate. |
| OPERATOR_PROVIDED_FACT | A concrete natural-language assertion made by a person, optionally with their role and source hint. | Recordable and reviewable. It is not independently verified merely because it is precise. |
| STRUCTURED_ATTESTATION | A named accountable person answers a versioned, anchored question; question, answer, scope and time are retained. | Candidate for criterion resolution only where a policy row permits it and required review occurs. It is not measurement. |
| DATASET_SUPPLIED | An identified file or export has been supplied. | A source-handling state only. It does not resolve a criterion or satisfy a gate by itself. |
| DOCUMENT_SUPPORTED | A reviewed document passage supports the particular assertion. | Candidate for criterion and gate use only where source, scope, recency and semantic support are reviewed. |
| MEASURED | A reproducible operational result from a verifiable source, method and scope. | Candidate for criterion and gate use only where the measured definition actually matches the policy claim. |
| DERIVED | A deterministic calculation or mapping over accepted inputs, retaining inputs and rule version. | May be used only to the extent its upstream evidence and approved rule permit. It cannot upgrade weak inputs or hide subjective mapping. |

OPERATOR_PROVIDED_FACT differs from an estimate only in the claim type; it is
not automatically stronger. STRUCTURED_ATTESTATION is different because an
anchored question, accountable role, scope and time are retained. It remains
distinct from document evidence and a reproducible operational measure.

## 4. Admissibility levels

Every future policy row should assess reviewed evidence at one of these
permission levels. They are not a numerical evidence score.

| Level | Meaning | Assessment effect |
|---|---|---|
| RECORDED_ONLY | Retain for audit, discussion or a later request. | No criterion, gate, priority or ROI input changes. |
| PRELIMINARY_UNDERSTANDING | Improve explanatory context, question routing or the next evidence request. | May change GRW guidance and rationale only; cannot resolve an assessment input. |
| CRITERION_RESOLUTION | Support a reviewed criterion or accountability assertion under a named instrument/mapping and required review. | May create a successor assessment input, but is not automatically gate-admissible. |
| GATE_ADMISSIBLE_WITH_APPROVAL | Satisfy a named material criterion for a specified gate when provenance, scope, instrument and role conditions are met. | Allows that gate to evaluate. It does not guarantee a passing gate or favourable recommendation. |
| INSUFFICIENT_FOR_THIS_USE | Useful or valid evidence that is inadequate for the intended claim. | Preserve it, state the lightest stronger route, and retain the affected criterion/gate as insufficient. |

The same item can have different levels for different uses. A monthly-volume
estimate may be PRELIMINARY_UNDERSTANDING for business discussion while being
INSUFFICIENT_FOR_THIS_USE for an ROI claim or material business-value gate.

## 5. Proposed criterion-by-criterion matrix

This is a proposed future-policy default, not a change to decision policy v0.2.
“Document or measured” means reviewed evidence applicable to the same activity,
population and relevant period. “Approval” is explicit and recorded; it is
never inferred from a submission.

| Criterion / present use | Record or preliminary understanding | Candidate criterion resolution | Gate-material conclusion / special condition |
|---|---|---|---|
| repetition — priority only | Estimate, fact, attestation, document or measured volume may explain scale. | Structured attestation, document evidence or a measurement may map through an approved frequency instrument. An estimate remains labelled estimate unless a future instrument permits a reviewed preliminary band. | Not gate material in v0.2. It cannot alter priority until the recommendation is otherwise eligible for scoring. Estimate alone never produces ROI. |
| predictability — conditional risk/autonomy, priority | Operator descriptions of variants or exceptions are useful context. | Document-supported procedure plus subject-matter review, or representative measured variation analysis, may support mapping. | Automation eligibility should require measured variation evidence or a future equivalently rigorous pre-approved method with accountable review. An estimate cannot qualify autonomous operation. |
| data_readiness — technical fit, priority | A statement about fields or systems can guide the next question. | Structured data-owner attestation, reviewed field/data-governance document, or validated profile may support mapping. | Require document-supported field/control evidence or measured profile evidence, plus accountable data-owner approval. “Our manager says all tickets have fields” is not enough. |
| ai_capability_fit — technical fit, priority | Customer workflow descriptions clarify work but cannot manufacture a capability. | Document-supported process requirement and mapped capability evidence, with reviewer rationale; future derived fit only from a non-circular, versioned rule. | Require document-supported direct-fit evidence, a mapped capability and reviewer approval. Volume or outcome estimates/facts cannot clear this gate. Derived fit cannot merely restate a capability signal. |
| human_judgement_requirement — risk/autonomy | Operator examples of judgement calls are relevant context. | Structured attestation from an accountable subject-matter owner and/or documented procedure may support mapping. | Require accountable subject-matter review; consequential decisions require corroborating document or measured case evidence as policy specifies. An estimate cannot reduce judgement requirement for automation. |
| business_value — business-value gate, priority | Volume, handling-time and reassignment estimates can strengthen opportunity narrative and identify what to measure. | Structured business-owner attestation using a versioned input instrument, reviewed cost/benefit document, or reproducible operational measure may support mapping. | Default to document-supported or measured inputs with business-owner approval. A future policy could permit bounded attestation only with disclosed inputs, assumptions and limitations. A bare estimate is not gate-admissible and never proves ROI. |
| risk_consequence — risk/autonomy, priority | Possible harm or incident reports identify a risk question. | Documented risk/control material, accountable risk attestation, or relevant measured incident evidence may support mapping. | Require risk/compliance/legal approval where relevant and corroborating document or measured evidence for high-consequence conclusions. Weak evidence must not clear safeguards; it may justify retaining investigation. |
| residual_risk_with_human_oversight — risk/autonomy | A description of a proposed human check is design context. | Documented controls plus risk-owner attestation may support preliminary mapping; measured control performance may strengthen it. | Require risk-owner approval and evidence that oversight is feasible for this process. “A human will check it” cannot establish low residual risk or qualify for automation. |
| implementation_complexity — priority only | Estimates and factual statements about integrations and change needs are useful planning context. | Structured technical-owner attestation, architecture/integration documentation, or measured implementation evidence may support mapping. | Not a v0.2 gate input. If used in priority, it remains visibly provenance-labelled; an estimate is not an implementation commitment. |
| conventional_solution_fit — conditional technical fit | Descriptions of current rules or software guide investigation. | Documented process/system analysis plus technical-owner attestation may support mapping. | A high value can yield DO_NOT_RECOMMEND, so require technical-owner approval and document-supported rationale. A future measured comparison may strengthen but need not be the only evidence path. Estimate alone cannot rule out AI. |
| human_accountability_required — risk/autonomy boolean | Customer description of approval/accountability practice is useful context. | Documented governance/procedure plus accountable owner attestation may resolve the boolean. | Require explicit accountable owner and appropriate governance/risk review. An estimate cannot conclude accountability is unnecessary. |

### 5.1 Cross-cutting rules

1. UNKNOWN and DATASET_SUPPLIED are never criterion- or gate-admissible alone.
2. An estimate cannot become MEASURED, DOCUMENT_SUPPORTED or
   STRUCTURED_ATTESTATION without the independent record required for that class.
3. DERIVED is admissible only when inputs meet the policy row and the
   calculation/mapping is pre-versioned, reproducible and non-circular. It
   cannot be stronger than the least sufficient upstream input for that use.
4. Admissibility can be asymmetric: enough evidence to retain a cautious
   INVESTIGATE_FURTHER state is not enough to lower a safety control or support
   AUTOMATE.
5. Criterion resolution is not permission to evaluate a gate. Present gates use
   both gate-material and conditional criteria, while priority scoring follows
   only AUTOMATE or AUGMENT.

## 6. Gate sensitivity

One global “minimum evidence strength” would be wrong.

| Gate | Current role | Future admissibility posture |
|---|---|---|
| evidence sufficiency | Confirms the assessed activity has source evidence. | Continue requiring source-backed activity evidence. A customer estimate, dataset or attestation must not retrospectively establish that the activity existed in the original process. A relevant reviewed document can extend evidence only in a successor lineage. |
| technical fit | Requires ai capability fit, conditionally conventional solution fit, then data readiness; also requires mapped capabilities. | Estimates can explain conditions but cannot clear fit/readiness. Direct fit needs documentary process evidence and mapped capabilities; data readiness needs data-owner evidence with source/control or measured-profile support. |
| business value | Requires material business value before risk evaluation. | Estimates are useful for sizing and question selection. Gate use needs transparent inputs, bounded scope, business-owner approval, and the source types the policy permits. It must not be rendered as proven ROI. |
| risk and autonomy | Requires judgement, consequence, residual risk and accountability; predictability then matters for automation. | Apply the strongest scrutiny and role controls. Weak/incomplete evidence can support caution but cannot clear autonomy safeguards. Automation needs particularly strong evidence of predictability, oversight and residual risk. |

The relevant question is not “which source is strongest?” but “which reviewed
source can support this claim at this decision point?”

## 7. Exact rules for estimates

Consider:

> “Approximately 18,000–22,000 tickets per month.”

Retain the response verbatim with its range, unit, period, qualifier, responder
role if known, process scope and submission time. It is
OPERATOR_PROVIDED_ESTIMATE unless an independent record establishes another
class.

| Possible effect | Rule for a plain-language estimate |
|---|---|
| Record the answer | Yes. Preserve an immutable response; “I do not know” is equally valid. |
| Improve explanatory context | Yes, after relevance review. It can describe apparent scale, seasonality and why further investigation matters. |
| Resolve an unknown factual observation | Not automatically. It can support a reviewed estimated observation only if the future contract represents that distinction without implying current KNOWN semantics. |
| Map to a 0–5 criterion | Never automatically. A human may propose mapping only through a versioned criterion instrument that retains raw range, anchors, scope and policy decision. |
| Clear a material gate | No by default. A bare estimate cannot be direct evidence for technical-fit or risk/autonomy gates. |
| Influence priority | It may inform a provenance-labelled preliminary priority input only after a recommendation is otherwise eligible for scoring. It cannot create priority while gate evidence is missing. |
| Support ROI | No. It can inform a clearly labelled exploratory scenario, never ROI, realised benefit, savings or a validated business case. |

“I estimate 10–15% of tickets are reassigned” can identify a plausible routing
problem and guide measurement. It cannot become a verified error rate, be
averaged into 12.5%, or prove performance improvement.

## 8. Operator facts and attestation

The following are materially different:

> “I estimate 10–15% of tickets are reassigned.”

> “Our service manager confirms that all tickets contain category, queue and
> product fields.”

The second begins as OPERATOR_PROVIDED_FACT, not automatic attestation or
data-readiness gate evidence. To become STRUCTURED_ATTESTATION it requires:

- a versioned question defining “all,” “ticket,” “contains,” and relevant scope;
- the exact response, named accountable responder/role, date and stated basis;
- system and relevant field identifiers, known limits and timeframe;
- an explicit declaration that the responder is authorised to attest; and
- human review that it actually addresses the intended criterion.

Even then, gate use depends on the policy row. For data readiness, the proposed
default requires reviewed field/control documentation or a validated data profile
in addition to data-owner approval.

## 9. Measured evidence and data-export requirements

A file upload is DATASET_SUPPLIED. It can become MEASURED only after a
reviewable measurement record establishes all applicable items.

| Requirement | Minimum record |
|---|---|
| Dataset identity | Immutable dataset/export ID, content hash, source system, collector and access/ownership declaration. |
| Applicability | Linked process and step, population, organisation scope, dates/timezone and intended metric. |
| Fields and definitions | Fields used, semantic meaning, units, identifiers, denominator and any joins. |
| Extraction/filtering | Query or documented export method, inclusion/exclusion filters, deduplication and sampling rules. |
| Calculation | Formula or executable/query reference, calculation version, aggregation and rounding rules. |
| Data-quality treatment | Missing, invalid, delayed, duplicated or unavailable values; treatment and effect. |
| Result expression | Value/range, units, timeframe, population/denominator and limitations. |
| Reproducibility | Another authorised reviewer can locate the same source and reproduce the result, or explain why a snapshot cannot be rerun. |
| Human review | Qualified reviewer confirms that calculation and scope support the claim; accountable owner approves higher-consequence gate use where required. |

A measured operational fact proves only its recorded metric and scope. It does
not itself establish AI capability fit, data governance, reduced human judgement,
residual safety risk, causal savings or ROI.

## 10. Natural-language mapping boundary

The product must preserve this boundary:

~~~text
customer’s verbatim answer
        ↓ deterministic parsing, if possible
candidate meaning with qualifiers, units, range and ambiguity markers
        ↓ human relevance, scope and provenance review
reviewed observation or retained UNKNOWN
        ↓ only if policy and instrument permit
reviewed criterion assertion with explicit mapping rationale
~~~

Parsing may recognise number, range, unit, period, percentage and qualifier. It
may flag a missing denominator, population, timeframe or process scope. It must
not select a criterion score, invent a midpoint, generalise to another activity
or decide admissibility.

“Usually 10–15%” remains a range with a usual qualifier until a reviewer
establishes the relevant population and denominator. “Rarely” and “around five
minutes” remain qualitative or approximate observations; they do not acquire
numeric precision through parsing. Mapping needs a visible, versioned instrument
and the approval required by the policy row.

## 11. Conflict handling and scope validity

There is no universal provenance hierarchy. A seemingly stronger source can be
stale, off-scope, based on another denominator, or answer another question.

### 11.1 Required process

1. Preserve every submitted/reviewed evidence record; never overwrite an older
   claim with a newer one.
2. Compare claim, criterion, process step, population, timeframe, unit,
   denominator, method and authority before calling two records conflicting.
3. Classify the relationship as CONSISTENT, PARTIALLY_OVERLAPPING,
   CONTRADICTORY, DIFFERENT_SCOPE, STALE_OR_SUPERSEDED, or UNRESOLVED.
4. A qualified reviewer records reconciliation rationale, further question and
   resulting admissibility decision. High-risk conflicts require the accountable
   owner defined by policy.
5. If unresolved conflict is material to the reached gate, retain the
   criterion/gate as insufficient rather than choose the favourable
   interpretation. A separately well-supported risk finding may still justify
   caution under its own rule.

| Situation | Required behaviour |
|---|---|
| Operator estimate conflicts with a document | Check whether the document is current and covers the same team/timeframe. Keep both. The reviewer may accept the document for historical scope and the estimate as current context, or retain unknown. |
| Measured result conflicts with operator statement | Validate population, filtering, dates and metric first. The measure may be off-scope or incomplete. Keep both and record which claim, if any, is admissible for this gate. |
| Two documents disagree | Record authority, version, date and scope. Newer is not automatically decisive if it is a draft or covers another workflow. |
| New evidence contradicts older evidence | Treat recency as a review factor, not a winning rule. A process change can make both statements true for their respective periods. |
| Valid evidence applies to another scope | Mark DIFFERENT_SCOPE. It cannot resolve the target gap until a reviewer establishes an approved transfer rationale. |

An accepted resolution is a new immutable decision linked to all evidence
considered. It does not erase rejected, outdated or off-scope material.

## 12. Versioning, fingerprinting and lineage

Evidence provenance and admissibility policy must version independently.

| Future artefact | Immutable content |
|---|---|
| EvidenceRecord | Original source/response, hash or locator, class, scope/time metadata and validation state. |
| EvidenceReview | Decision on relevance, source class, scope, conflicts and mapping suitability. |
| EvidenceAdmissibilityPolicy | Policy ID/version/status/content fingerprint; per criterion and gate-use rows, accepted classes, required fields/roles, instrument references, permitted effect and escalation route. |
| AdmissibilityDecision | Evidence IDs considered, criterion/gate use, policy fingerprint, permission level, reviewer/approver, rationale and unresolved limitations. |
| ResolutionAssertion | Criterion/accountability assertion or explicit unknown, mapping/instrument version and upstream evidence/admissibility IDs. |
| ReassessmentRequest | Baseline package/review/assessment IDs and hashes, selected assertions, decision-policy and admissibility-policy fingerprints, authoriser and time. |

A successor Phase 5 assessment retains existing source-review-policy lineage and
adds an extension trace from each changed input to GRW evidence, review,
admissibility decision and policy/instrument versions. The successor package and
comparison expose the chain in customer-readable and audit-readable form.

Changing an admissibility rule never rewrites historical evidence, reviews,
assessments or packages. Reconsidering old evidence under a later rule requires
new review/approval and a successor assessment, showing both policy versions and
why the later one permits a different use.

Any future implementation changes the production fingerprint. Frozen PORT
artefacts, their hashes and historical fingerprint cohorts remain untouched and
must not be described as exercising GRW.

## 13. Reassessment effect

Only evidence reviewed and marked admissible for the specified criterion/gate
use may become input to a successor review.

~~~text
immutable baseline package and assessment
        ↓ optional GRW evidence record
review + admissibility decision
        ↓ explicit decision-owner approval of selected assertions
immutable successor approved review
        ↓ assessment using pinned decision and admissibility policies
successor package + baseline-to-successor comparison
~~~

The comparison must retain:

- baseline and successor package, review, assessment and policy fingerprints;
- introduced evidence and original customer wording;
- class, scope/time limitations and review decision;
- admissibility-policy version and exact row permitting or rejecting use;
- changed or retained-unknown criterion/assertion;
- changed gates, newly evaluated gates and gates still not evaluated;
- recommendation/priority result and why it changed or did not; and
- remaining material conflicts and DECISION_CRITICAL gaps.

Approval authorises evaluation under pinned rules; it never means “make the
recommendation pass.” AUTOMATE, AUGMENT, INVESTIGATE_FURTHER and
DO_NOT_RECOMMEND all remain valid outcomes.

## 14. M1 decision and recommended final M1

### 14.1 Safety decision

The previous M1—one DECISION_STRENGTHENING question, natural-language range
estimate, human review, reassessment approval and successor assessment/package
comparison—is **not methodologically safe as a decision-changing reassessment**.

The estimate strengthens explanatory context, but current product semantics have
no approved strength contract, criterion instrument or admissibility-policy row
that could honestly let it resolve a gate-material criterion. Allowing it to do
so would silently weaken document-evidence discipline and present an approximate
business statement as a sufficiently evidenced assessment input.

### 14.2 Recommended final M1: non-decision evidence lifecycle

The first implementation should prove GRW plumbing without changing an engine
input or running a decision merely to create apparent movement:

1. Start from an immutable Decision Package and one linked
   DECISION_STRENGTHENING gap.
2. Ask one optional normal-English volume question; accept a range estimate or
   explicit “I do not know.”
3. Preserve raw answer; parse only candidate range/unit/period; human-review it
   as OPERATOR_PROVIDED_ESTIMATE.
4. Create an immutable PRELIMINARY_UNDERSTANDING or RECORDED_ONLY admissibility
   decision. State that it is not an assessment input and name the lightest
   escalation route.
5. Produce an evidence-strengthening comparison against the baseline showing
   new context, no changed criterion, no changed gate, no changed
   recommendation, and byte-identical baseline artefacts.

This is a complete proof of optional intake, provenance, natural-language
handling, review, immutability and transparent non-admissibility. It does not
call a no-op engine run a reassessment.

The first decision-affecting reassessment is a later, separately approved
milestone. It needs one narrow approved criterion/gate row, a versioned
instrument where mapping is required, required human roles and evidence meeting
that row—for example semantically reviewed relevant documentation or a
reproducible measured result. It may still remain INVESTIGATE_FURTHER or become
less favourable.

## 15. Unresolved methodology questions

1. Which criterion/gate rows, if any, may accept STRUCTURED_ATTESTATION without
   corroborating document or measured evidence?
2. Does a future assessment contract need a distinct state for a
   provenance-labelled estimated criterion, or can current KNOWN semantics
   remain clear when strength is carried separately? M1 avoids deciding it.
3. Which reviewers and accountable approvals are required by consequence level,
   especially for risk/autonomy and data governance?
4. What semantic quality checks must supplement current document-locator
   validation before a document supports a criterion?
5. What data protection, retention, access and secure-processing design is
   required before operational exports are accepted?
6. Which criterion instruments are sufficiently transparent and non-circular?
   AI capability fit requires special care because capability mapping alone
   cannot prove direct fit.
7. How should future policies distinguish a preliminary economic scenario from
   a business case, realised benefit or ROI claim?

Until these are resolved through separately approved policy and implementation
work, this document remains methodology only.

