# Phase 9A-0c — Case C candidate sourcing memo

Version: v0.2 (supersedes v0.1: pool topped up from 6 to 8 candidates, top 5 ranked)
Date: 2026-08-17
Status: **RECOMMENDATION ONLY — NO DOCUMENT ACCEPTED, NOTHING INGESTED, NO CRITERION SCORED**

**Scope.** Pre-ingestion sourcing material for Case C under
`docs/phase9a-0c-observation-plan-v0.1.md` §3.1/§3.2 (plan committed at `29bda11`). Not one of
the §9 outputs; carries no observational result.

**What was not done.** No product code, prompt, schema, policy, taxonomy or threshold read for
selection purposes or modified. No observation-design change proposed. Nothing ingested, no
provider call, no criterion value determined for any candidate. The capability taxonomy was
deliberately **not** consulted, so no candidate could be picked for its likelihood of mapping to
a capability (`gates.py:175`). No candidate was screened on the six gate-material criteria.

---

## 1. Sourcing strategy

Declared in v0.1 before any candidate was seen, and unchanged:

| Item | Declaration |
|---|---|
| Document class | Published SOP, work instruction, runbook or process narrative describing a **current-state operational process** |
| Source pool | Public bodies, public universities, national health bodies, regulators — organisations that publish operational procedures as a matter of course. Blogs, vendor marketing and consulting summaries excluded by construction |
| Why public | Satisfies C9 by construction — no confidential or commercially sensitive internal material is sent to a third-party API |
| Domains sought | Deliberately spread. Excluded by prior use: claims-document intake (PORT-001), call routing (PORT-002), meeting documentation (PORT-003), complaint handling (Case A fixture) |
| Screening basis | C1–C10 only |
| Excluded from screening | Whether the document states values for `ai_capability_fit`, `data_readiness`, `business_value`, `human_judgement_requirement`, `risk_consequence`, `residual_risk_with_human_oversight`, `human_accountability` |

### 1.1 Pool top-up — disclosed deviation from the v0.1 stopping rule

v0.1 declared a stopping rule of six candidates. Eight were ultimately drawn. **The reason is
recorded here because topping up a pool after seeing results is the exact mechanism by which
selection bias operates.**

Cause: of the first six, three never reached content assessment at all — two failed on document
format (OCR'd text layer; no text layer) and one on unit-of-document. Only four were assessable,
which v0.1 §6 itself recorded as too thin. The top-up repaired pool size, not pool outcome. The
two additional candidates were drawn from new domains by format-neutral queries, and both are
reported below regardless of how they scored.

This is a deviation from a pre-registered rule. It is disclosed rather than quietly absorbed.
If the operator judges it material, the correct remedy is to discard the top-up and select from
the original four, not to leave it unrecorded.

---

## 2. Top 5 ranked candidates

### Rank 1 — Standard Operating Procedure: Recruitment and Selection

| Field | Value |
|---|---|
| **1. Title** | Standard Operating Procedure Recruitment and Selection |
| **2. Organisation** | New River Community and Technical College (public, West Virginia) |
| **3. URL** | <https://www.newriver.edu/wp-content/uploads/2025/09/SOP-HR-Recruitment-and-Selection-Procedures-Final.pdf> |
| **4. Type** | Numbered-step SOP. Effective 1 March 2024, revised 8 September 2025 |
| **5. Length** | ≈7,600 characters, 4 pages. Est. 2 chunks |
| **8. Text-native** | Yes. No OCR needed. Shows word-space loss (`isreceived`, `HumanResources`, `willselect`) — kerning/tracking extraction artefacts, **not** OCR substitution damage. Recorded as a tokenisation risk, not a C7 failure |
| **9. Rank** | **1** |

**6. Why it satisfies the checklist**

- **C1 PASS** — five numbered steps, each with named sub-activities: request to fill (ERF); identify hiring manager and committee; candidate approval; offer of employment; onboarding. Well over four discrete activities.
- **C2 PASS** — Hiring Manager, Divisional VP, HR Director, Controller, CFO/VP Finance-Administration, Director of Grants, President or designee, hiring committee.
- **C3 PASS** — inputs: Employment Request Form, Additional Advertisement Request Form, application materials, interview score sheets. Outputs: requisition and job posting, offer letter, candidate disposition emails, onboarding plan.
- **C4 PASS** — several genuine branches: the DocuSign signing order with an explicit denial-and-resubmit path if funding is wrong; President's approval/denial; candidate not approved or withdraws → reconsider others or repost; Extra Help, Adjunct and Work Study exempt from the committee step; DVP may add an interview or accept the recommendation.
- **C5 PASS** — ERFs valid 90 days then re-evaluated; postings open a minimum of 10 days; at least three voting committee members; 6-month introductory period with an HR check two weeks before it ends.
- **C6 PASS** — current, revised September 2025, marked Final.
- **C7 PASS**, **C8 PASS (provisional)** — comfortably inside 40,000 characters; block count puts it over 30, so knowingly chunked.
- **C9 PASS** — public college publication, role titles only, no named individuals, no personal or commercially sensitive data. **C10** not required.

**7. Obvious disqualifier** — none found. Weakest point is the word-space loss under C7, which
degrades tokenisation slightly but does not engage the no-OCR prohibition.

**Why first.** It is the most squarely *in-class* document in the pool. §3 asks for "a genuine
SOP, work instruction or runbook"; this is titled as an SOP, structured as numbered steps with
owners, and is currently in force. It passes all ten items with no mandatory item in doubt. The
basis for ranking it above Rank 2 is document-class membership, not content — see §4.

---

### Rank 2 — DFS Transaction Cycle Narrative: Procurement — Invoice Processing

| Field | Value |
|---|---|
| **1. Title** | DFS Transaction Cycle Narrative — Procurement / Purchase Order, sub-category Invoice Processing |
| **2. Organisation** | Cornell University, Division of Financial Services |
| **3. URL** | <https://finance.cornell.edu/sites/default/files/invoice-processing-narrative.pdf> |
| **4. Type** | Process narrative / internal-control transaction-cycle document. Created 24 October 2023 |
| **5. Length** | ≈11,800 characters, 6 pages. Est. 4 chunks |
| **8. Text-native** | Yes, clean extraction. No OCR needed |
| **9. Rank** | **2** |

**6. Why it satisfies the checklist**

- **C1 PASS** — "Process Documented in Chronological Order" enumerates ≥7 activities: unit identifies need and initiates the IWD; SSC P2P reviews purpose and determines payment method; supplier submits invoice to AP; AP matches invoice to PO and creates the KFS payment request; fiscal officer confirms receipt and approves; KFS routes to Contracts & Grants / Tax / Disbursement Manager; freight-bill handling.
- **C2 PASS** — dedicated responsibilities section: Unit, Shared Service Center, Vendor, Accounts Payable, fiscal officer/delegate, P2P team.
- **C3 PASS** — inputs: invoice, purchase order, IWD/IWNT, supporting documentation. Outputs: KFS payment request (PREQ), disbursement voucher, payment, attached scanned invoice.
- **C4 PASS** — over/under the \$5,000 receipt-confirmation threshold; electronic invoice auto-matched versus email/mail manual entry; PO route versus non-PO disbursement voucher; payment-hold path; freight-bill exception.
- **C5 PASS** — "Frequency: Daily"; the 15-day federal freight-payment rule with a stated consequence; the \$5,000 and \$25,000 thresholds.
- **C6 PASS** — documents the cycle as operated. Its "Process Inefficiencies To Be Addressed" section describes current shortcomings, not a replacement process.
- **C7 PASS**, **C8 PASS (provisional)**, **C9 PASS** — public finance site, no named individuals, two role mailboxes only. **C10** not required; optionally mask the mailboxes.

**7. Obvious disqualifier** — none on the checklist. Two non-disqualifying concerns the operator
should weigh: (a) it is a *control narrative* rather than a step-list work instruction, so it is
a richer-than-typical member of the class and arguably an optimistic representative of it;
(b) it carries the disclosed screening exposure in §4.

---

### Rank 3 — SOP 01: Preparation, Review and Approval of Standard Operating Procedures for Research (v6.0)

| Field | Value |
|---|---|
| **1. Title** | SOP 01: Preparation, Review and Approval of Standard Operating Procedures for Research, v6.0 |
| **2. Organisation** | Gloucestershire Hospitals NHS Foundation Trust |
| **3. URL** | <https://www.gloshospitals.nhs.uk/documents/18074/SOP_01_-_Preparation_of_SOPs_v6.0.pdf> |
| **4. Type** | Controlled SOP. Approved 27 June 2024, in force 1 August 2024, review due 1 August 2027 |
| **5. Length** | ≈19,000 characters, 19 pages including a blank-template appendix. Est. 6–8 chunks |
| **8. Text-native** | Yes, clean extraction. No OCR needed |
| **9. Rank** | **3** |

**6. Why it satisfies the checklist**

- **C1 PASS** — ≥8 activities: draft on the template; review at the Governance and Oversight Group; assign version and record in the SOP index; e-sign; save to the controlled drive; publish to the trust site; announce via the research bulletin; record training on EDGE; archive, suspend or withdraw.
- **C2 PASS** — R&I QA Manager, Head of Professional Services, GOG (membership listed), Trust Senior Responsible Officer, author, Communications Team.
- **C3 PASS** — inputs: draft on the Appendix 2 template, change-request email. Outputs: signed SOP, index entry, version-history entry, EDGE training record.
- **C4 PASS** — substantial versus non-substantial change branch with different routes and version-numbering rules; approved versus amendments-required at GOG; the §7 conflicting-SOP path; the no-changes-at-review path.
- **C5 PASS** — 14 days to decide on an early review; quarterly review cycle; three-year review period; a 5-week approval-to-implementation window (1 week to publish, 4 weeks for training); training compliance checked at annual appraisal.
- **C6 PASS** — current controlled version. **C7 PASS**. **C9 PASS** — public NHS publication; two named staff and one internal drive path, all already public.
- **C8 PASS with a recorded risk** — inside 40,000 characters, but Appendix 2 is a *blank SOP template* and Appendix 1 is a flowchart flattened to loose text. Both consume non-empty blocks while carrying little process content, which can change which blocks the extraction resolves. That bears directly on the `STATED_BUT_UNCITABLE` measurement and must be recorded before ingestion.

**7. Obvious disqualifier** — none. Ranked below 1 and 2 on the C8 boilerplate-noise risk.
**C10** conditional: consider masking the two personal names and the internal drive path.

---

### Rank 4 — Standard Operating Procedures: Clinical Documentation (Lorenzo), v1.1

| Field | Value |
|---|---|
| **1. Title** | Standard Operating Procedures — SOP Title: Clinical Documentation, v1.1 |
| **2. Organisation** | Salisbury NHS Foundation Trust (disclosed under FOI ref FOI_4817) |
| **3. URL** | <https://www.salisbury.nhs.uk/FOIdocs/FOI_4817/QuestionNo7/Document%2011%20-%20Lorenzo%20SOP%20(Clinical%20Documentation).pdf> |
| **4. Type** | Controlled SOP, system work instruction. v1.1 dated 4 May 2018 |
| **5. Length** | ≈28,000 characters, ~19 pages including a large abbreviation appendix. Est. 10+ chunks |
| **8. Text-native** | Yes, clean extraction. No OCR needed |
| **9. Rank** | **4** |

**6. Why it satisfies the checklist**

- **C1 PASS** — dictate correspondence; create the letter; authorise it; upload or scan documents; search completed documentation; record clinical information in charts.
- **C2 PASS** — an explicit `Role:` line heads each activity (Nurse/Clinician/AHP, Secretary/Audio Typist, Booking coordinators, Receptionists).
- **C3 PASS** — inputs: Big Hand dictation, Lorenzo templates, incoming paper/email/fax. Outputs: letter in the EPR, scanned document associated to an episode of care, clinical chart entry.
- **C4 PASS** — paper versus electronic authorisation; "Complete – accept and print" versus "Complete – return to author"; a dedicated Exceptions section; a business-continuity fallback to manual recording.
- **C5 PASS** — naming conventions mandatory; the Word source copy "MUST be deleted"; authorised text cannot be deleted once marked complete; strike-through-with-reason correction control.
- **C9 PASS** — public FOI disclosure, three named authors, no patient data. **C10** conditional: consider masking the three names.

**7. Obvious disqualifier — two live risks, one on a mandatory item**

- **C6 WEAK, mandatory.** Mixes current with planned state: "Clinical charts *will be* used in clinical areas as they become 'paperlite'", "There will be a continual roll out across the hospital", several document types marked "Not in use yet", and "Post Holder Responsible for SOP: TBC". A reviewer could reasonably rule this fails C6. It is flagged, not resolved.
- **C8 RISK.** Appendix A is a ~150-row abbreviation table. Table rows would dominate the non-empty block count while carrying no process content, materially skewing a `STATED_BUT_UNCITABLE` finding.

Also eight years old, and its subject matter sits close to PORT-003's client-meeting
documentation, reducing the diversity value of the case. Ranked fourth on C6 and C8, not on
that proximity.

---

### Rank 5 — Operating Procedure 5006: New Hire Onboarding

| Field | Value |
|---|---|
| **1. Title** | ASUN Operating Procedure 5006 — New Hire Onboarding |
| **2. Organisation** | Arkansas State University Newport (public) |
| **3. URL** | <https://files.asun.edu/sops/5000/5006_New_Hire_Onboarding.pdf> |
| **4. Type** | Operating procedure, structured as a phased responsibility checklist. Approved 4/2018, last reviewed 7/2022 |
| **5. Length** | ≈5,200 characters, 3 pages. Est. 2 chunks |
| **8. Text-native** | Yes. No OCR needed, but see the layout risk below |
| **9. Rank** | **5** |

**6. Why it satisfies the checklist**

- **C1 PASS** — many discrete activities grouped by phase: Pre-Arrival, 1st Day, Department Onboarding, 1st Week, 1st Month, First 120 Days.
- **C2 PASS** — an explicit "Who Initiates" column: Human Resources, Hiring Manager, Employee, Information Technology Services, Director of Procurement, Director of Process Innovation.
- **C3 PASS (thin)** — inputs and outputs are identifiable for *some* activities (offer letter, onboarding guide, I-9 verification, network userid, business cards), which is what C3 asks for, but the document is a checklist rather than a flow so they are sparse.
- **C5 PASS** — benefits enrolment within the first 31 days; onboarding "continues for at least six months"; 9:00 a.m. orientation slot; a first-120-days phase.
- **C6 PASS** — current operating procedure, though not reviewed since July 2022. **C9 PASS** — public, role titles and one department phone number, no named individuals.

**7. Obvious disqualifier — C4 is the weak point, and C4 is mandatory**

The document has almost no decision points, branches or exception paths. The nearest things are
"some items that are not applicable to internal transfers and part-time hires may be omitted"
and scattered "(if applicable)" markers. There is an offer-approval workflow but no stated
branch on its outcome. **A reviewer could reasonably rule this fails C4**, which would make it
unsuitable. Ranked fifth for that reason.

Secondary risk: the body is a two-column table (activity | owner). Flattened extraction may
interleave activity text with the owner column, which is a Phase 2 block-resolution hazard
distinct from OCR.

---

## 3. Drawn but rejected — not in the top 5

Recorded per §3.2 so the rejection trail is auditable. All candidates drawn are reported.

| Candidate | Cause | Item |
|---|---|---|
| EPA Region 1 OEME, *Sample Login, Tracking and Sample Disposition* SOP (2002) — <https://ndep.nv.gov/uploads/env-brownfields-qaplans-docs/SOP_Sample_Login,_Tracking_and_Sample_Disposition_R1.pdf> | **Scanned then OCR'd.** Text layer shows substitution damage: `S0P` for `SOP`, `1nve~ti~atib-n` for `Investigation`, `aqree` for `agree`, `~ate/~ime` for `Date/Time`. Phase 2 does not support scanned documents | **C7 FAIL (mandatory)** |
| | Not the reason for rejection, but noted: dated 2002 with "changes due to new facility", so currency is doubtful; and it names individual custodians alongside room numbers and physical key-custody arrangements | C6, C9/C10 |
| Vanuatu Public Service Commission, *Records & Information Management SOP* — <https://psc.gov.vu/images/2026/Records%20%20Information%20Management%20SOP.pdf> | Fetch returned no extractable text, consistent with an image-only PDF. C7 unverifiable and C1–C6 unassessable | **C7 unverifiable** |
| University of Edinburgh, *Freedom of information procedures* — <https://information-compliance.ed.ac.uk/guidance/requests/procedures> | Not a single document. The hub page carries only section abstracts; procedure content lives across five child pages. Ingesting it means the operator choosing which pages to concatenate — an operator-constructed boundary with no single provenance | Unit-of-document |

Edinburgh is **deferred, not disqualified**: viable if the operator first records a fixed page
set and capture date as the document definition. That is a sourcing decision, not a checklist
judgement.

---

## 4. Disclosed exposure, and the bias direction the operator should know about

**§3.2's sequencing cannot be fully achieved by any assessor, including this one.** C1–C5
require reading the process description end to end, and whatever the document says about volume,
frequency, controls, error consequence or judgement sits in that same text. Incidental exposure
is a property of the checklist, not a failure to follow it. No criterion has been scored for any
candidate and no criterion value has been determined.

Concretely, for **Rank 2 (Cornell)**: while verifying C1–C5 I observed that its house format
carries standing sections headed "Key Risks", "Key Controls", "Metrics", and a header field
"Criticality: High / Frequency: Daily". I did not read them to determine whether any criterion
is satisfied. The operator should nonetheless know this, because it is the channel through which
selection bias would operate.

**The non-obvious part.** The instinctive fix — prefer candidates where no criterion-bearing
sections were observed — is *also* biased, in the opposite direction. Preferring content-rich
documents biases toward criteria being evidenceable; preferring content-sparse ones biases
toward `NOT_STATED`, which pushes the §7 threshold decision toward attestation and a contract
change. **Neither direction is neutral, and §7's 60% thresholds are sensitive to exactly this.**

So the ranking above deliberately does *not* use observed criterion-bearing content in either
direction. Rank 1 is placed first on **document-class membership** — it is titled and structured
as an SOP, which is what §3 asks for, whereas Rank 2 is an internal-control narrative adjacent
to the class. That basis is auditable and content-independent.

Options for the operator:

1. **Accept Rank 1.** All ten items pass, it is the most in-class document, and its selection
   rests on a content-independent ground. This is the recommended path.
2. **Accept Rank 2 and record the exposure**, using the treatment §3 already applies to Case B's
   disclosed PORT-003 AFTER exposure: tolerable because C1–C10 are mechanical and the exposure
   is recorded with the result.
3. **Have a second person accept from this shortlist without reading §4**, so the accepting
   party is not the exposed party. Strongest control if someone is available.
4. **Discard the §1.1 top-up** and select from the original four, if the deviation from the
   pre-registered stopping rule is judged material.

**Not on the list, because it would invalidate the observation:** drawing further candidates
because these do not look likely to score well. All eight drawn are reported here.

---

## 5. Recommended next steps

None of these are actions taken by this memo.

1. Decide among the §4 options and record the decision and its reason **before** any ingestion, per §3.2.
2. Capture the accepted document to a fixed local file; record its SHA-256 and capture date, giving Case C the same provenance discipline as the PORT cases.
3. Recompute C8 exactly against `chunking.py` (`max_characters=40_000`, `max_non_empty_blocks=30`) on that captured file and record the slice count. All C8 results above are provisional estimates from fetched text, not from Phase 2's own extraction.
4. Complete and record the C9/C10 review on the captured file.
5. Commit the accepted-document record and the §5 prediction **before** the live provider call, and obtain the separate approval Case C requires under §3 and §10.3.
6. Re-verify the production fingerprint as `3c5c86bd…` immediately before the run, per §2.

---

## 6. Verified facts, assumptions, limitations

**Verified.** Checklist read from `docs/phase9a-0c-observation-plan-v0.1.md` at `29bda11`, on
`main` with a clean tree apart from untracked `.agents/`, `.claude/` and this new
`docs/observations/` path. Chunking limits read directly from
`src/ai_adoption_engine/extraction/chunking.py` lines 12–13. Prior-case domains read from
`evaluation/portfolio/register.v0.1.json`. All C1–C7 and C9 results are quoted from fetched
document text.

**Assumptions.** That "public and already published" satisfies C9's intent — the plan frames C9
around internal documents, and a public document is a strictly weaker case. That fetched text is
a fair proxy for Phase 2's extraction: sound for detecting OCR damage, only approximate for
character and block counts.

**Limitations.**

- C8 is provisional for every candidate; step 3 above resolves it.
- C6 for Rank 4 and C4 for Rank 5 are judgement calls a reviewer could decide either way. They are flagged, not resolved, because resolving them is the accepting party's job.
- The §4 exposure is real and disclosed rather than mitigated away.
- The §1.1 top-up deviates from a pre-registered stopping rule.
- Three of eight candidates were rejected on document format or unit-of-document grounds rather than process content, so only five reached full content assessment. The pool is adequate but not deep.
- Ranks 1 and 5 are both HR-domain documents from US community colleges, so the top 5 is less domain-diverse than it appears.
