# Findings on AI Adoption in Business Processes

We identified several real-world cases where companies documented a business process (“before”), then introduced AI, and later reported results (“after”).  Key candidate examples include:

| Company (Industry)                  | Process                       | Before source (URL)                                         | AI adoption source (URL)                                       | After source (URL)                                         | Date before | Date after | AI tech                        | What changed                                                                      | Evidence quality              | Suitable for evaluation?            |
|------------------------------------|-------------------------------|--------------------------------------------------------------|----------------------------------------------------------------|------------------------------------------------------------|-------------|------------|-------------------------------|-----------------------------------------------------------------------------------|------------------------------|------------------------------------|
| **E‑commerce retailer** (Retail)   | **Invoice Processing (AP)**    | Auxis AP case study (private retailer): manual email- and inbox-based invoice entry. | Auxis AP case study (UiPath Document Understanding deployed) | Auxis AP case study (95% touchless processing, 40% capacity up) | ~2023      | 2024       | RPA + AI (UiPath Document Understanding) | Replaced laborious manual invoice entry with automated OCR and validation. | Vendor case study, moderate detail | **Yes** (complete before/after documented) |
| **Nordic insurance firm** (Insurance) | **Claims Processing**          | EY Denmark case study: manual claims review (spreadsheets, PDFs). | EY case study (EY Fabric Document Intelligence) | EY case study (70% of docs auto‐extracted; major efficiency gains) | ~2022      | 2024       | AI Document Intelligence       | Deployed an AI document-intelligence pipeline, automating extraction from claim forms; 70% of claims handled without human data entry. | Consulting case (EY), credible  | **Yes** (process before and improvements documented) |
| **Global bank** (Financial)        | **Check Fraud Detection**      | Cognizant case study: manual verification of handwritten checks. | Cognizant case study (AI fraud-detection model)    | Cognizant case study (50% fraud cut; $20M savings) | ~2020      | ~2022      | ML/AI fraud detection model    | Introduced an AI model to flag suspicious checks; cut fraud by ~50% and saved ~$20M. | Vendor case study (anonymized bank) | **Yes** (basic process change documented, though “before” is narrative) |
| **BMW Group** (Automotive)         | **Assembly Conveyor Maintenance** | BMW press release: conveyor faults halted lines (manual fixes after breakdowns). | BMW press release (in-house ML on conveyor data) | BMW press release (500 min downtime avoided annually) | ~2017?     | 2023       | In-house ML (predictive maintenance) | Deployed AI on existing sensor data to predict conveyor faults, preventing stoppages (≈500 min downtime saved/year). | Official press release (high)    | **Yes** (before/after implicitly given in press release) |
| **Natural gas producer** (Energy)  | **Vendor Invoice Processing**  | Smartbridge case study: one-person manual invoice reconciliation (risk of delays). | Smartbridge case study (Power Automate + AI Builder model) | Smartbridge case study (automated data entry, always meets net-10 terms) | ~2022      | 2025       | Microsoft Power Automate + AI | Replaced single-employee processing with automated invoice extraction (Azure AI) and routing; now invoices hit discounts on time without manual effort. | Vendor case study (energy sector) | **Yes** (clear before narrative and after outcomes) |
| **Elisa (Finland)** (Telecom)      | **Customer Service (Chatbot)** | MindTitan case study: ~500 agents handling ~100K monthly contacts (all human-driven). | MindTitan case study (Annika chatbot launched 2017) | MindTitan case study (Annika handles 70% of contacts; resolves 34% end-to-end) | 2017 (launch) | 2022       | AI Chatbot (NLP-based assistant) | Introduced “Annika” AI chatbot for support queries. Now it handles ~70% of contacts (34% fully resolved), significantly reducing human workload. | Industry case study (vendor blog) | **Yes** (well-documented before/after metrics) |

Each row above links to sources. For example, the Auxis case study describes how a high-growth e-commerce retailer went from tedious manual invoice entry to 95% touchless processing with UiPath IDP. Similarly, the EY/Deloitte case for a Nordic insurer spells out the pre-AI manual claims workflow and post-AI efficiencies. In all these cases we have (A) documentation of the original process (even if informal), (B) evidence of an AI implementation, and (C) reports of the outcome. 

 *Figure: Automation workflow for invoice processing at the Texas energy firm (Smartbridge case). Incoming emails trigger a cloud flow that uses an AI model to extract invoice metadata into a database; a desktop bot then uploads and validates invoices in the approval system.* 

## Evidence and Evaluation Feasibility  

Our findings suggest it **is feasible** to collect before/after AI evidence from public sources, though examples are scattered and often vendor-authored. Key points:

- **Quality of evidence varies:** Government or corporate press releases (BMW) and large consultancy case studies (EY) are high-quality. Vendor blogs (Auxis, Smartbridge, MindTitan, Cognizant) provide useful detail but with marketing tone. We have to treat them critically. 
- **Comparability:** In most cases, a concise description of the “before” process exists (in words) and an AI-driven “after” outcome is reported. For example, the Auxis/AP case clearly states the old steps and the new automated steps. BMW’s press release explicitly contrasts old breakdowns vs new predictive avoidance. Thus the engine could be evaluated by feeding it the “before” description and checking if it suggests the real AI solution. 
- **Candidate ranking:** The 6 cases above are our top candidates. Highest evidence quality: BMW (official press) and EY (major consultancy). Mid-tier: Auxis, Smartbridge, Elisa (vendor case studies). All show a clear Before→After scenario. 
- **Notable partial cases:** The **Ada AI apprenticeship examples** are instructive (manual inventory tracking, feedback analysis) but lack an “after” (they are opportunities identified by apprentices, not real implementations). They are examples of “before” processes, so we note them as concept leads but not as full evaluation cases.

## Existing AI Adoption Methodologies and Tools  

We found **no existing tool** that exactly matches the proposed engine (i.e. one that ingests a process document and outputs prioritized AI opportunities). However, related frameworks and studies exist:

- **Task/Process Suitability Criteria:**  Prior research outlines criteria similar to our scoring. For instance, Agaton & Swedberg (Chalmers Univ.) review many RPA selection methods and propose an RPA Suitability Framework. Key attributes include how routine/cognitive a process is.  Similarly, an academic “AI Readiness Task Assessment” (AIRTA) for finance tasks uses questions on data availability, repetitiveness, etc.. Our criteria (task volume, structure of data, predictability, risk, etc.) align closely with these prior models. 
- **Government & Industry Guides:** The Australian National AI Centre publishes guidelines that mirror our reasoning. It proposes scoring “pain points” on volume, repetitiveness, data richness, error tolerance and cost.  A high AI-fit score plus high business impact implies prioritization. These match our thinking (e.g. Table 1 has exactly “Volume, Repetitive, Data availability, Error tolerance, Cost” as scoring criteria). 
- **Process Mining & Discovery:** Some platforms (e.g. Celonis, IBM Blueworks, specialized vendors) perform process discovery and might flag bottlenecks, but they do not automatically propose AI solutions. The **Ada College apprenticeship** case studies (UK) show how analyzing a simple Excel-based workflow (inventory tracking) or large feedback forms can reveal AI opportunities, but these are manual analyses, not automated tools. 
- **Consulting frameworks:** Consultancies (McKinsey, Deloitte, etc.) offer “AI use case catalogs” and transformation frameworks (e.g. McKinsey’s Aviva case, Deloitte’s industry AI guides). These are more strategic and broad, not engines.

In summary, while parts of our idea (suitability criteria, scoring, structured extraction) appear in the literature, **no one has built a dedicated AI-use-case engine** that takes a process description and transparently recommends AI actions. Our project would be novel in synthesizing process-mining ideas with AI-readiness criteria into an automated decision-support tool.

## Evaluation Methodology  

Given these cases, a feasible evaluation is:

1. **Ground-truth selection:** Use the “before” descriptions (from cases above) as input to the engine.
2. **Engine output:** The engine will output a list of AI-relevant opportunities with scores/justifications.
3. **Comparison to reality:** Compare the engine’s recommendations to the documented “after” AI interventions. For example, if the real case introduced OCR+automation for invoices, check if the engine also ranks OCR+automation highly.
4. **Metrics:** One can measure *coverage* (how many of the actual implemented AI solutions did the engine identify? – akin to recall) and *precision* (how many recommended solutions were actually implemented or realistic?). Because the sample is small and domain-specific, quantitative metrics (precision/recall, F1) can be illustrative but should be interpreted cautiously.  
5. **Expert judgment:** Have domain experts review the engine’s outputs vs the real outcome. Some suggestions (false positives) might still be valid improvements even if the company did not implement them. Conversely, false negatives would indicate missed opportunities. Qualitative scoring (e.g. agreement level) and case-by-case analysis are important. 
6. **Case study analysis:** For each candidate, prepare a report comparing the engine’s suggestions with the real changes, discussing why matches/mismatches occurred. This mirrors related academic work (e.g. validating process-suitability frameworks against real scenarios).

This evaluation is academically sound: it treats real documented transformations as a “ground truth” to test the engine’s reasoning. Precision/recall gives a rough quantitative sense, but narrative explanation of results (and errors) is crucial given the novelty of the approach.

## Feasibility Conclusion

It **is realistic** to proceed. We found enough examples (5–6 strong candidates) that document a process before AI, then after AI implementation. These cases provide both input material (“before process”) and expected outcomes (“AI solution and benefit”) to test the engine. The criteria and methodology for AI suitability are supported by literature and official guidelines. 

The main limitations are: public cases are often described at a high level (not formal SOP documents), and outcomes may be summarized by marketing language. However, our core research question (can an AI-driven tool *predict/prioritize* the same kinds of opportunities real companies made?) is answerable with this data. 

We should proceed by refining the research question (e.g. focus on a specific domain or type of process), and begin designing the engine architecture and reasoning framework. The first concrete step is to develop prototypes for **process extraction** (e.g. NLP to parse “before” text into structured steps/actors/data) and **suitability scoring** (based on our criteria). 

## Next Steps

- **Formalize objectives:** Confirm the research question (perhaps emphasize “to what extent can our engine’s suggestions match actual AI adoptions?”).  
- **Develop prototype:** Build a minimal system that takes a text description of a process and identifies key elements (steps, actors, data, decisions). This could leverage LLMs for semantic extraction.  
- **Implement criteria:** Encode the identified criteria (volume, repetition, data type, etc.) as a scoring rubric or rule-based system. Possibly combine with LLM judgment for explanation.  
- **Create test harness:** For an initial case (e.g. the e-commerce AP example), manually input the “before” description and refine the engine until it produces the known solution (e.g. “automated invoice extraction”). Use this as a proof-of-concept.  
- **Iterate with experts:** Engage domain experts (e.g. finance managers, process analysts) to evaluate and critique the engine’s recommendations on one or two cases.  
- **Prepare ethical review:** Since the project involves recommending AI in business settings, consider ethical implications (bias, job impact, GDPR) in design and reporting, satisfying LO6. 

This structured approach (focusing on evidence and method before coding) ensures a solid foundation. Only after confirming that the literature and data support our approach should we build the full Decision-Support Engine. 

**Sources:** We relied on multiple case studies and reports (citations above) and reviewed relevant academic and industry publications on AI adoption and task suitability to ground our analysis. These are cited inline for transparency.