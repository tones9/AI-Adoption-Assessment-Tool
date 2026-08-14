# Phase 8 Reference Annotation Guide v0.1

Identifier: `phase8-reference-annotation.v0.1`

## Roles

A primary annotator prepares the complete before-state reference. An
independent qualified reviewer checks every activity boundary, sequence,
material evidence span, decision-mode reference, capability reference,
conventional-solution judgement, unsafe-automation judgement, and ambiguous
item. The reviewer also checks a systematic sample of non-material attributes.

Controlled development fixtures may use known-answer verification and must be
labelled as not independently human-reviewed when no second reviewer is
available. Confirmatory cases require a primary annotation plus an independent
qualified review of every activity boundary, sequence, material assertion,
decision reference, safety judgement, and conventional-solution judgement.
The reviewer identity is assigned before annotation begins; no particular
number of formal annotators is assumed. Disagreements are resolved by recorded
consensus. Unresolved disagreement remains dual-labelled or unknown.

## Before-state rule

Annotators may open only the frozen before packet and source manifest. They may
not open the sealed after packet, search for the later implementation, inspect
engine or baseline recommendations, or infer an answer from a vendor/product
name outside the supplied text.

## Activity unit

An activity is a meaningful unit of work performed by an actor or system that
has an action and an operational object or outcome. Do not split wording-only
details into separate activities. Split when responsibility, decision point,
input/output, or operational outcome materially changes.

Record contiguous sequence numbers and exact supporting source text. Preserve
branches and dependencies separately rather than forcing them into a linear
activity when the source does not establish linear order.

## Assertion states

- `known`: directly stated and supported by an exact source span;
- `inferred`: a reasonable interpretation supported by source evidence and
  explicitly marked as inference;
- `unknown`: not responsibly recoverable from the before material; and
- `supported_empty`: the source explicitly establishes absence or an empty
  collection.

Do not replace missing information with common business practice.

## Decision reference

Decision references are independent judgements, not reverse-engineered policy
outputs. Annotators receive only the four mode definitions and approved
capability taxonomy. They do not receive thresholds, gates, weights, scores,
engine output, baseline output, or after evidence.

Where more than one mode is defensible, record the primary mode plus all
acceptable modes and explain the ambiguity. Explicitly record whether
automation would be unsafe and whether a conventional solution is preferable.

## Adjudication record

Retain annotator identifier or pseudonym, reviewer identifier or pseudonym,
timestamps, initial values, reviewed values, disagreement reasons, consensus
outcomes, and any unresolved ambiguity. Do not silently overwrite annotations.
