# Four-Gate Evaluation Plan — Non-Technical Version v0.1

Status: **For review and approval — no build work has started**  
Date: **2026-09-06**  
Technical companion: `four-gate-evaluation-cohort-design-v0.1.md`

## What this is for

We have built the new four-gate decision route. Before we make it the normal route for the product, we need to test it carefully on new, controlled examples.

This plan explains how we will do that testing fairly and safely.

The goal is to check that the new route:

- follows its own rules consistently;
- keeps a clear record of why it reached each decision;
- handles missing information honestly;
- keeps human review and approval in the process; and
- does not damage or rewrite anything from the existing product.

This is **not** a plan to prove that the product will make money, work perfectly in every business, or be safe to deploy automatically. Those are later questions.

## What will stay untouched

The old evaluation work belongs to the current, older decision route. It will stay exactly as it is.

We will not:

- rewrite old results using the new four-gate system;
- change old scores, reports, files, databases, or conclusions;
- compare old and new outcome labels as though they mean the same thing;
- change the normal product settings while doing this study; or
- use information about what happened later when deciding what should have been recommended earlier.

The new study will have its own folders, records, names, and results.

## How each test case will work

For every new case, we will follow this order:

1. Save the original source document and lock down its identity.
2. Extract and review the process information as normal.
3. Have a human approve the reviewed information.
4. Freeze that approved “before” picture.
5. Run the new four-gate route using its exact saved version of rules.
6. Save the decision, the reasons, the evidence used, and the version details.
7. Freeze the final record so it cannot quietly change later.

For some cases, a separate person will also prepare an independent answer from the same source material. They will do this without seeing the system’s result. This lets us see where the system and a human reference agree or disagree.

## Two kinds of test cases

We will use two separate groups.

### Practice cases

These are made-up, controlled examples. They help us check that the testing process itself works.

They will not be used to make claims about how well the product performs in the real world.

### Governed real-world-style cases

These are new cases with clear source records and careful controls. They may tell us whether the new system followed its rules properly on a real source document.

Some will simply show what happened. Others will also have an independently prepared human reference so that agreement can be measured.

We will show the number of cases clearly. If there are too few cases for a meaningful summary, we will say “not enough information” instead of creating a misleading score.

## What we will check

For every case, we will check:

- Did the correct version of the new framework run?
- Was human approval completed before the assessment?
- Did the system show all four decision gates in the right order?
- Did it stop at the right point when important information was missing?
- Did it keep missing information marked as unknown rather than guessing?
- Can every important statement be traced back to supporting evidence?
- Did it produce a valid final outcome from its four separate gate decisions?
- If we run the exact same approved information again, does it produce the exact same result?
- Does the final decision package include all required sections?

For cases with an independent human reference, we can also check whether the system and the reference agree about:

- whether a change is justified;
- whether the activity is ready;
- the best type of intervention;
- how much autonomy is safe, when that question is actually reached; and
- the final decision and the evidence supporting it.

We will not treat a gate that was correctly skipped as a failure.

## Extra safety checks

We will look for warning signs, for example:

- recommending too much automation without enough support;
- missing a normal non-AI solution;
- saying process improvement is needed only because information is missing;
- treating background/context information as though it blocked a decision;
- presenting an AI safety veto incorrectly; or
- allowing a new process to write to an old or protected workspace.

At this stage, these are observations to learn from, not proof that the system is good or bad overall.

## Optional follow-up test

The product now supports one very narrow follow-up path: when a decision is waiting only for data-readiness information.

For a suitable case, we may test that path as a separate mini-study. A person must:

1. provide a plain-text supporting document;
2. review the evidence;
3. propose the data-readiness update;
4. request reassessment; and
5. explicitly approve it.

The original decision remains official and unchanged. The new result is a separate follow-up decision. We will not call it “better” or claim a business benefit simply because it changed.

## How results will be described

We can say:

- “The new four-gate system produced a clear, saved, evidence-linked result for this case.”
- “The system agreed or disagreed with the independent reference on this point.”
- “This measure does not apply because that part of the decision was not reached.”
- “This small study does not prove that the system works everywhere.”

We will not say:

- “The new system is better than the old system.”
- “The rules are proven correct.”
- “The reassessment improved the business.”
- “The recommendation is ready to deploy automatically.”

## What needs your approval

Before Codex builds the testing tools, please approve these points:

1. Make this a new, separate study for the four-gate system; do not change the old evaluation. **Recommended.**
2. Start with practice cases, then use carefully controlled new cases. Do not set a fixed number of cases yet. **Recommended.**
3. Only measure agreement with a human reference when that reference was prepared independently and without seeing the system’s result. **Recommended.**
4. Keep the data-readiness follow-up test optional and clearly separate from the main study. **Recommended.**
5. Do not make claims about business impact, return on investment, deployment safety, or universal accuracy from this study. **Recommended.**

Once approved, the technical companion will be used to give Codex a tightly limited build task.
