# Phase 8 Primary Metrics v0.1

Identifier: `phase8-primary-metrics.v0.1`

## Extraction

- activity precision, recall, and F1;
- ordering agreement using Kendall's tau-b on one-to-one matched activities;
- micro attribute precision, recall, and F1 across the approved attribute set;
- evidence-supported assertion rate;
- inappropriate-certainty rate; and
- appropriate-unknown rate.

One-to-one substantive step alignments define true-positive activities;
unmatched system and reference steps define false positives and false
negatives. Split/merge relations are excluded from the primary match count and
reported separately. Attribute scores are micro-averaged over individual
adjudicated field-value assertions on matched steps. Evidence support is the
proportion of scored system assertions supported by their cited before span.
Inappropriate certainty is the proportion of system `known`/`inferred`
assertions whose certainty is adjudicated inappropriate. Appropriate unknown
is the proportion of reference-unknown assertions retained as unknown.

## Decision

- recommendation accuracy;
- macro-F1;
- confusion matrix;
- per-mode precision and recall;
- unsafe over-automation rate; and
- conventional-solution miss rate.

Unsafe over-automation means an `AUTOMATE` prediction where the adjudicated
reference marks automation unsafe or accepts only `AUGMENT` or
`DO_NOT_RECOMMEND`. A conventional-solution miss means the reference marks a
conventional solution preferable but the prediction recommends `AUTOMATE` or
`AUGMENT`.

Recommendation accuracy accepts any pre-adjudicated acceptable mode. The
confusion matrix, per-mode scores, and macro-F1 use the single primary reference
mode so that their denominators are unambiguous. Rates use all comparable
reference activities as their denominator; missing or extra predictions are a
failed/invalid output rather than silently omitted observations.

## Capability

- multilabel micro precision, recall, and F1.

Capability labels are scored as activity-capability pairs over the frozen
taxonomy.

## Prioritisation

- Kendall's tau-b on activities with an adjudicated comparable rank.

Ties are preserved. Fewer than two comparable ranked activities is reported as
not applicable, not zero.

## End to end

- completion rate;
- review time;
- correction, rejection, and addition counts;
- retained unknown count;
- recommendation changes caused by review; and
- final traceability completeness.

Review counts are event counts from the review log. Traceability completeness
is the fraction of required final material assertions and recommendations that
resolve to valid before-state evidence or an explicit retained-unknown record.

## Repeatability

- activity-set agreement;
- known/inferred/unknown agreement;
- evidence-selection agreement; and
- downstream recommendation agreement where applicable.

With three runs, agreement is the mean of the three pairwise comparisons.
Activity, evidence, and downstream recommendation agreement use Jaccard
agreement on canonical items. Knowledge-state agreement uses canonical
`field=state` items. Canonicalisation rules are fixed before confirmatory runs.

Report per-case values and simple aggregate descriptive statistics. Confidence
intervals may be added where appropriate. Advanced modelling is exploratory.
