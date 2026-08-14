# Step-Alignment Procedure v0.1

Identifier: `phase8-step-alignment.v0.1`

## Purpose

Map extracted activities to reference activities before calculating activity,
attribute, ordering, or evidence metrics. Wording similarity alone is not a
substantive match.

## Procedure

1. Hide downstream recommendations and after evidence from the aligner.
2. Review activity meaning, actor, inputs/outputs, evidence span, and position.
3. Assign a one-to-one `matched` mapping where the extracted and reference
   activities represent substantially the same unit of work.
4. Mark unmatched extracted activities `spurious`.
5. Mark unmatched reference activities `missed`.
6. Record `split` when one reference activity is represented by multiple
   extracted activities.
7. Record `merge` when one extracted activity combines multiple reference
   activities.
8. Resolve ambiguous alignments through independent review and retain the
   rationale.

Primary activity precision/recall/F1 uses only one-to-one `matched` mappings.
Split, merge, missed, and spurious cases are reported separately in error
analysis. Ordering agreement uses the reference and extracted sequence of the
one-to-one matched activities and Kendall's tau-b.

