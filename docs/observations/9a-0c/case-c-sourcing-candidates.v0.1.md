# Phase 9A-0c — Case C candidate sourcing memo

Version: v0.1
Date: 2026-08-17
Status: **RECOMMENDATION ONLY — NO DOCUMENT ACCEPTED, NOTHING INGESTED**

**Scope of this file.** This is pre-ingestion sourcing material for Case C under
`docs/phase9a-0c-observation-plan-v0.1.md` §3.1/§3.2 (plan committed at `29bda11`).
It is **not** one of the §9 outputs (`prediction.v0.1.json`, `observation.v0.1.json`,
`findings.v0.1.md`, `hashes.sha256`) and carries **no observational result**. If the
operator prefers the §9 output set to stand alone, move this file outside
`docs/observations/9a-0c/`.

**What was not done.** No product code, prompt, schema, policy, taxonomy or threshold was
read for selection purposes or modified. No observation-design change is proposed. No
document was ingested, no provider call was made, and no criterion value was determined.
The capability taxonomy was deliberately **not** consulted, so that no candidate could be
chosen for its likelihood of mapping to a capability (`gates.py:175`).

---

## 1. Sourcing strategy, declared before candidates were seen

Pre-declared so the candidate pool is not shaped by what the pool turned out to contain.

| Item | Declaration |
|---|---|
| Document class | Published SOP, work instruction, runbook or process narrative describing a **current-state operational process** |
| Source pool | Public bodies, public universities, national health bodies, regulators — organisations that publish operational procedure documents as a matter of course |
| Why public sources | Satisfies C9 by construction: no confidential or commercially sensitive internal material is transmitted to a third-party API |
| Domains sought | Deliberately spread. Excluded by prior use: claims-document intake (PORT-001), call routing (PORT-002), meeting documentation and follow-up (PORT-003), complaint handling (Case A fixture) |
| Stopping rule | Stop at six candidates, assess all six, rank all six. Do not keep drawing candidates until a preferred one appears |
| Screening basis | C1–C10 only |
| Explicitly excluded from screening | Whether the document states values for `ai_capability_fit`, `data_readiness`, `business_value`, `human_judgement_requirement`, `risk_consequence`, `residual_risk_with_human_oversight`, or `human_accountability` |

All six candidates drawn are assessed and reported below, including the three rejected.
No candidate was discarded silently.

---

## 2. Ranked candidates

### Rank 1 — Cornell University, DFS Transaction Cycle Narrative: Procurement / Invoice Processing

Source: <https://finance.cornell.edu/sites/default/files/invoice-processing-narrative.pdf>
Created 24 October 2023. Text-native PDF. Domain: procure-to-pay. New domain for the portfolio.

| # | Result | Evidence |
|---|---|---|
| C1 | PASS | "Process Documented in Chronological Order" enumerates ≥7 discrete activities: unit identifies need and initiates the IWD; SSC P2P reviews business purpose and determines payment method; supplier submits invoice to Accounts Payable; AP reviews invoice against the purchase order and creates the KFS payment request; fiscal officer confirms receipt and approves; KFS routes to Contracts & Grants / Tax / Disbursement Manager; freight-bill handling |
| C2 | PASS | Dedicated "Process Owner(s) / Key Parties / Contacts / Responsibilities" section naming Unit, Shared Service Center, Vendor, Accounts Payable, fiscal officer/delegate, P2P team |
| C3 | PASS | Inputs: invoice, purchase order, IWD/IWNT document, supporting documentation. Outputs: KFS payment request (PREQ), disbursement voucher, payment, attached scanned invoice |
| C4 | PASS | Multiple branches: over/under the \$5,000 receipt-confirmation threshold; electronic invoice auto-matched to PO versus email/mail manual entry; PO route versus non-PO disbursement-voucher route; payment-hold path; freight-bill exception |
| C5 | PASS | "Frequency: Daily"; the 15-day federal freight-payment requirement with stated consequence; the \$5,000 receiving-confirmation threshold; the \$25,000 formal bid limit |
| C6 | PASS | Documents the cycle as operated. Its "Process Inefficiencies To Be Addressed" section describes current shortcomings, not a replacement process |
| C7 | PASS | Text-native. Extraction is clean — correct casing, no substitution artefacts, no OCR noise |
| C8 | PASS (provisional) | ≈12k characters, well inside the 40,000 limit. Bullet density puts non-empty blocks above 30, so it will be knowingly chunked at ~4 slices under `chunking.py` (`max_characters=40_000`, `max_non_empty_blocks=30`). Confirm exact counts at ingestion |
| C9 | PASS | Published on a public university finance site. No named individuals; two role mailboxes only; no personal or commercially sensitive data |
| C10 | Not required | Optionally mask the two role mailboxes. Not necessary for C9 |

**Caveat the operator should weigh (§3.2 fair-test judgement, not a checklist item).** This is
a *control narrative* rather than a step-list work instruction. Its house format includes
standing sections for risks, controls and metrics. That makes it a richer-than-typical member
of the SOP class, so it may be an *optimistic* representative of the document class the
product targets. That cuts against picking it if Case C is meant to be a typical document.
See §4 — this is also where the exposure disclosure applies.

### Rank 2 — Gloucestershire Hospitals NHS Foundation Trust, SOP 01: Preparation, Review and Approval of SOPs for Research (v6.0)

Source: <https://www.gloshospitals.nhs.uk/documents/18074/SOP_01_-_Preparation_of_SOPs_v6.0.pdf>
Approved 27 June 2024, implemented 1 August 2024, review due 1 August 2027. Text-native PDF.
Domain: document control and governance. New domain for the portfolio.

| # | Result | Evidence |
|---|---|---|
| C1 | PASS | ≥8 discrete activities: draft using the template; review at the Governance and Oversight Group; assign version number and record in the SOP index; e-sign; save to the controlled drive; publish to the trust site; announce via the research bulletin; record training on EDGE; archive, suspend or withdraw |
| C2 | PASS | R&I QA Manager, Head of Professional Services, GOG (membership listed), Trust Senior Responsible Officer, SOP author, Communications Team |
| C3 | PASS | Inputs: draft on the Appendix 2 template, change-request email to the R&I mailbox. Outputs: signed SOP, SOP index entry, version history log entry, EDGE training record |
| C4 | PASS | Substantial versus non-substantial change branch, with different routes and version-numbering rules; approved versus amendments-required at GOG; the §7 "more than one SOP" conflict path; the no-changes-at-review path |
| C5 | PASS | 14 days to decide whether an early review is needed; quarterly formal review cycle; three-year review period; a 5-week approval-to-implementation window (1 week to publish, 4 weeks for training); training compliance checked at annual appraisal |
| C6 | PASS | Current controlled version, in force since 1 August 2024 |
| C7 | PASS | Text-native, clean extraction |
| C8 | PASS (provisional) | ≈19k characters, inside the 40,000 limit; knowingly chunked on block count. **Noise risk:** Appendix 2 is a blank SOP template and Appendix 1 is a flowchart rendered as loose text; both consume blocks while carrying little process content, which may affect which blocks the extraction resolves. Worth recording before ingestion because it bears directly on the `STATED_BUT_UNCITABLE` measurement |
| C9 | PASS | Public NHS trust publication. Two named staff (author, approving SRO), one role mailbox, one internal drive path — all already public |
| C10 | Conditional | Consider masking the two personal names and the internal drive path. Low sensitivity, since already published |

**Why this is the strongest choice if the operator wants the least-contaminated selection.**
No section heading pertaining to any gate-material criterion was observed while verifying
C1–C5. This is *not* a claim that the document evidences nothing — that question was not
asked and must not be asked before acceptance. It means the selection of this candidate is
harder to attribute to criterion content than the selection of Rank 1.

### Rank 3 — Salisbury NHS Foundation Trust, Lorenzo SOP: Clinical Documentation (v1.1)

Source: <https://www.salisbury.nhs.uk/FOIdocs/FOI_4817/QuestionNo7/Document%2011%20-%20Lorenzo%20SOP%20(Clinical%20Documentation).pdf>
v1.1 dated 4 May 2018, disclosed under FOI. Text-native PDF.

| # | Result | Evidence |
|---|---|---|
| C1 | PASS | Dictate correspondence; create the letter; authorise the letter; upload or scan documents; search completed documentation; record clinical information in charts |
| C2 | PASS | An explicit `Role:` line heads each activity (Nurse/Clinician/AHP, Secretary/Audio Typist, Booking coordinators, Receptionists) |
| C3 | PASS | Inputs: Big Hand dictation, Lorenzo letter templates, incoming paper/email/fax. Outputs: letter in the EPR, scanned document associated to an episode of care, clinical chart entry |
| C4 | PASS | Paper versus electronic authorisation; "Complete – accept and print" versus "Complete – return to author"; a dedicated "Exceptions" section; a business-continuity fallback to manual recording |
| C5 | PASS | Trust naming conventions mandatory; the Word source copy "MUST be deleted"; authorised text cannot be deleted once marked complete; strike-through-with-reason correction control |
| C6 | **WEAK — mandatory item at risk** | Mixes current state with planned state. "Clinical charts will be used in clinical areas as they become 'paperlite'", "There will be a continual roll out across the hospital", several document types marked "Not in use yet", and "Post Holder Responsible for SOP: TBC". A reviewer could reasonably rule this fails C6 |
| C7 | PASS | Text-native, clean extraction |
| C8 | RISK | Appendix A is a ~150-row abbreviation table. Table rows will dominate the non-empty block count while carrying no process content, which would materially skew a `STATED_BUT_UNCITABLE` finding |
| C9 | PASS | Public FOI disclosure; three named authors; no patient data |
| C10 | Conditional | Consider masking the three personal names |

Also note: eight years old, and its subject matter (clinical documentation and correspondence)
sits close to PORT-003's client-meeting documentation, reducing the diversity value of the case.
Ranked third on the C6 and C8 concerns, not on that proximity.

---

## 3. Rejected candidates, with causes

Recorded per §3.2 so the rejection trail is auditable.

| Candidate | Cause of rejection | Item |
|---|---|---|
| EPA Region 1 OEME, *Sample Login, Tracking and Sample Disposition* SOP (2002) — <https://ndep.nv.gov/uploads/env-brownfields-qaplans-docs/SOP_Sample_Login,_Tracking_and_Sample_Disposition_R1.pdf> | **Scanned then OCR'd.** The text layer shows characteristic substitution damage: `S0P` for `SOP`, `1nve~ti~atib-n` for `Investigation`, `aqree` for `agree`, `~ate/~ime` for `Date/Time`. Phase 2 does not support scanned documents | **C7 FAIL (mandatory)** |
| | Secondary concerns, not the reason for rejection: dated 2002 with "changes due to new facility", so currency is doubtful (C6); and it names individual custodians alongside room numbers and physical key-custody arrangements, which would require C10 redaction | C6, C9/C10 |
| Vanuatu Public Service Commission, *Records & Information Management SOP* — <https://psc.gov.vu/images/2026/Records%20%20Information%20Management%20SOP.pdf> | Fetch returned no extractable text, consistent with an image-only PDF. C7 cannot be verified, and C1–C6 cannot be assessed at all | **C7 unverifiable** |
| University of Edinburgh, *Freedom of information procedures* — <https://information-compliance.ed.ac.uk/guidance/requests/procedures> | Not a single document. The hub page carries only section abstracts; the procedure content lives across five child pages (receiving, local handling, quality assurance, writing the response, practitioner support). Ingesting it means the operator choosing which pages to concatenate — an operator-constructed document boundary with no single provenance, which weakens the Case C provenance record | Unit-of-document, not a numbered item |

The Edinburgh candidate is **deferred, not disqualified**. It becomes viable if the operator
first records a fixed page set and capture date as the document definition. That is a
sourcing decision for the operator, not a checklist judgement.

---

## 4. Disclosed exposure — read before accepting a candidate

**The plan's §3.2 sequencing cannot be fully achieved by any assessor, including this one.**
C1–C5 require reading the process description end to end. Anything the document says about
volume, frequency, controls, error consequence or judgement is in that same text. So
assessing C1–C5 necessarily creates incidental exposure to material that bears on the
gate-material criteria. This is a property of the checklist, not a failure to follow it.

Concretely, for **Rank 1 (Cornell)**: while verifying C1–C5 I observed that the document's
house format includes standing sections headed "Key Risks", "Key Controls", "Metrics", and a
header field "Criticality: High / Frequency: Daily". I did not read them to determine whether
any criterion is satisfied, and no criterion value has been determined for any candidate. But
the operator should know that the top-ranked candidate is one where criterion-bearing section
*headings* were visible during screening, because that is exactly the channel through which
selection bias would operate.

Three honest options, for the operator to decide:

1. **Accept Rank 1 and record the exposure**, using the same treatment §3.3/Case B already
   applies to the analyst's PORT-003 AFTER exposure: tolerable because C1–C10 are mechanical,
   disclosed and recorded with the result. This is consistent with existing precedent in the plan.
2. **Accept Rank 2 (Gloucestershire) instead.** It passes every mandatory item, and no
   criterion-bearing section headings were observed during screening, so the selection is
   harder to attribute to expected favourability. The cost is the Appendix-2 boilerplate
   noise recorded under C8.
3. **Have a second person accept a candidate from this shortlist** without reading §4, so
   that the accepting party is not the exposed party.

Option 1 is defensible; option 2 is the more conservative reading of §3.2; option 3 is the
strongest, if a second person is available.

**What would invalidate the observation** and is therefore not on the list: rejecting these
candidates and drawing more until one looks likely to score well. All six candidates drawn
are reported here, and the three rejections are on stated mandatory grounds.

---

## 5. Recommended next steps, in order

None of these are actions taken by this memo.

1. Decide between the three options in §4 and record the decision and its reason **before**
   any ingestion, per §3.2.
2. Capture the accepted document to a fixed local file, record its SHA-256 and the capture
   date, so Case C has the same provenance discipline as the PORT cases.
3. Recompute C8 exactly against `chunking.py` (`max_characters=40_000`,
   `max_non_empty_blocks=30`) on that captured file, and record the resulting slice count.
   The C8 results above are provisional estimates from fetched text, not from Phase 2's
   own extraction.
4. Complete and record the C9/C10 review on the captured file.
5. Commit the accepted-document record and the §5 prediction **before** the live provider
   call, and obtain the separate approval Case C requires under §3 and §10.3.
6. Re-verify the production fingerprint as `3c5c86bd…` immediately before the run, per §2.

---

## 6. Verified facts, assumptions, limitations

**Verified.** Plan text and checklist read from `docs/phase9a-0c-observation-plan-v0.1.md`
at `29bda11`, on branch `main` with a clean tree apart from untracked `.agents/` and
`.claude/`. Chunking limits read directly from
`src/ai_adoption_engine/extraction/chunking.py` lines 12–13. All C1–C7 and C9 results above
are quoted from the fetched document text. Prior-case domains read from
`evaluation/portfolio/register.v0.1.json`.

**Assumptions.** That "public and already published" satisfies C9's intent; the plan frames
C9 around internal documents, and a public document is a strictly weaker case. That fetched
text is a fair proxy for what Phase 2 would extract — sound for detecting OCR damage, only
approximate for character and block counts.

**Limitations.** C8 is provisional for all candidates (step 3 above). C6 for Rank 3 is a
judgement call that a reviewer could decide either way; it is flagged rather than resolved.
The exposure in §4 is real and is disclosed rather than mitigated away. Two of six candidates
were rejected on document-format grounds rather than process content, so the effective pool
that reached content assessment was four, which is thin; drawing more candidates is available
but must be done on the §1 stopping rule, not after seeing these results.
