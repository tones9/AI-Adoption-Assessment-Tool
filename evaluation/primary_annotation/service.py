from __future__ import annotations

import copy
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evaluation.harness.common import load_json, sha256_file
from evaluation.primary_annotation.con001 import (
    ACTION_CUES,
    BEFORE_RELATIVE_PATH,
    BEFORE_SHA256,
    CASE_ID,
    EVIDENCE_CATALOG,
)


CURRENT_SCHEMA_ID = "phase8-primary-current-state-reference.v0.1"
DECISION_SCHEMA_ID = "phase8-primary-decision-reference.v0.1"
APPROVAL_SCHEMA_ID = "phase8-primary-annotation-approval.v0.1"
DRAFT_SCHEMA_ID = "phase8-primary-annotation-draft.v0.1"

KNOWLEDGE_STATES = ("known", "inferred", "unknown", "supported_empty")
CUE_DISPOSITIONS = ("include", "merge", "split", "context_only", "unclear")
ORDER_STATES = ("ordered", "parallel", "conditional", "unknown")
FIELD_TYPES = ("actor", "system", "input", "output", "other")
RECOMMENDATION_MODES = (
    "AUTOMATE",
    "AUGMENT",
    "INVESTIGATE_FURTHER",
    "DO_NOT_RECOMMEND",
)
CAPABILITIES = (
    "DOCUMENT_INFORMATION_EXTRACTION",
    "CLASSIFICATION",
    "PREDICTION_FORECASTING",
    "ANOMALY_PATTERN_DETECTION",
    "GENERATIVE_AI",
    "KNOWLEDGE_RETRIEVAL",
    "RECOMMENDATION",
    "DECISION_SUPPORT",
    "COMPUTER_VISION",
    "WORKFLOW_AUTOMATION",
)
TRISTATE = ("Yes", "No", "Unclear")
PROCESS_ASSERTION_FIELDS = ("description", "objective", "scope_start", "scope_end")
REQUIRED_ACTIVITY_FIELDS = ("actor", "system", "input", "output")


class AnnotationValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


class ImmutableRecordError(FileExistsError):
    pass


def empty_assertion(field: str) -> dict[str, Any]:
    return {
        "field": field,
        "value": "",
        "knowledge_state": "",
        "evidence_locators": [],
        "rationale": "",
        "supported_empty_confirmed": False,
    }


def new_draft() -> dict[str, Any]:
    return {
        "schema_id": DRAFT_SCHEMA_ID,
        "case_id": CASE_ID,
        "before_packet": {
            "path": BEFORE_RELATIVE_PATH.as_posix(),
            "sha256": BEFORE_SHA256,
        },
        "current_state": {
            "process_name": "",
            "process_assertions": {
                field: empty_assertion(field) for field in PROCESS_ASSERTION_FIELDS
            },
            "cue_reviews": [
                {
                    "cue_id": cue["cue_id"],
                    "cue_text": cue["text"],
                    "source_locators": list(cue["evidence_locators"]),
                    "disposition": "",
                    "final_activity_ids": [],
                    "rationale": "",
                }
                for cue in ACTION_CUES
            ],
            "activities": [],
            "assertions": [],
            "unresolved_ambiguities": [],
        },
        "decision_reference": {"decisions": []},
        "draft_metadata": {
            "annotator_id": "",
            "revision_reason": "",
            "supersedes_version": None,
        },
    }


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def preview_fingerprint(draft: dict[str, Any]) -> str:
    previewable = {
        "case_id": draft.get("case_id"),
        "before_packet": draft.get("before_packet"),
        "current_state": draft.get("current_state"),
        "decision_reference": draft.get("decision_reference"),
        "annotator_id": draft.get("draft_metadata", {}).get("annotator_id", ""),
        "revision_reason": draft.get("draft_metadata", {}).get("revision_reason", ""),
    }
    return hashlib.sha256(canonical_json(previewable)).hexdigest()


def _validate_assertion(
    assertion: dict[str, Any], valid_evidence: set[str], label: str
) -> list[str]:
    errors: list[str] = []
    state = assertion.get("knowledge_state", "")
    value = str(assertion.get("value", "")).strip()
    locators = assertion.get("evidence_locators") or []
    rationale = str(assertion.get("rationale", "")).strip()
    if state not in KNOWLEDGE_STATES:
        return [f"{label}: choose a knowledge state"]
    invalid = sorted(set(locators) - valid_evidence)
    if invalid:
        errors.append(f"{label}: invalid evidence locator(s): {', '.join(invalid)}")
    if state in {"known", "inferred"}:
        if not value:
            errors.append(f"{label}: {state} assertions require a value")
        if not locators:
            errors.append(f"{label}: {state} assertions require permitted evidence")
    if state == "inferred" and not rationale:
        errors.append(f"{label}: inferred assertions require an explicit rationale")
    if state == "unknown" and value:
        errors.append(f"{label}: unknown assertions must not contain an invented value")
    if state == "supported_empty":
        if value:
            errors.append(f"{label}: supported-empty assertions must have an empty value")
        if not locators:
            errors.append(f"{label}: supported-empty assertions require permitted evidence")
        if assertion.get("supported_empty_confirmed") is not True:
            errors.append(
                f"{label}: confirm that the cited evidence explicitly establishes absence"
            )
    return errors


def validate_current_state(draft: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if draft.get("case_id") != CASE_ID:
        errors.append("Only CON-001 is permitted")
    if draft.get("before_packet", {}).get("sha256") != BEFORE_SHA256:
        errors.append("The before-packet hash does not match frozen CON-001")
    current = draft.get("current_state", {})
    if not str(current.get("process_name", "")).strip():
        errors.append("Process name is required")
    valid_evidence = {item["evidence_id"] for item in EVIDENCE_CATALOG}
    process_assertions = current.get("process_assertions", {})
    for field in PROCESS_ASSERTION_FIELDS:
        if field not in process_assertions:
            errors.append(f"Process {field}: an explicit assertion or unknown is required")
        else:
            errors.extend(
                _validate_assertion(
                    process_assertions[field], valid_evidence, f"Process {field}"
                )
            )

    cue_reviews = current.get("cue_reviews", [])
    cue_ids = {item["cue_id"] for item in ACTION_CUES}
    if {item.get("cue_id") for item in cue_reviews} != cue_ids:
        errors.append("Every frozen evidence-derived cue must remain present")
    for cue in cue_reviews:
        label = f"Cue {cue.get('cue_id', '?')}"
        disposition = cue.get("disposition", "")
        if disposition not in CUE_DISPOSITIONS:
            errors.append(f"{label}: choose a disposition")
        if disposition in {"include", "merge", "split"} and not cue.get(
            "final_activity_ids"
        ):
            errors.append(f"{label}: identify the resulting activity ID(s)")
        if disposition in {"context_only", "unclear"} and not str(
            cue.get("rationale", "")
        ).strip():
            errors.append(f"{label}: explain why it is context-only or unclear")

    activities = current.get("activities", [])
    if not activities:
        errors.append("At least one final activity is required")
    activity_ids = [str(item.get("activity_id", "")).strip() for item in activities]
    if any(not item for item in activity_ids):
        errors.append("Every final activity requires an activity ID")
    if len(activity_ids) != len(set(activity_ids)):
        errors.append("Final activity IDs must be unique")
    known_ids = set(activity_ids)
    sequences: list[int] = []
    for index, activity in enumerate(activities, start=1):
        label = f"Activity {activity.get('activity_id') or index}"
        if not str(activity.get("name", "")).strip():
            errors.append(f"{label}: activity name is required")
        order_state = activity.get("order_state", "")
        if order_state not in ORDER_STATES:
            errors.append(f"{label}: choose an ordering/dependency state")
        sequence = activity.get("sequence")
        if order_state == "ordered":
            if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
                errors.append(f"{label}: ordered activities require a positive sequence")
            else:
                sequences.append(sequence)
        dependencies = activity.get("dependencies") or []
        invalid_dependencies = sorted(set(dependencies) - known_ids)
        if invalid_dependencies:
            errors.append(
                f"{label}: unknown dependency ID(s): {', '.join(invalid_dependencies)}"
            )
        if activity.get("activity_id") in dependencies:
            errors.append(f"{label}: an activity cannot depend on itself")
        boundary = {
            "value": activity.get("name", ""),
            "knowledge_state": activity.get("knowledge_state", ""),
            "evidence_locators": activity.get("evidence_locators") or [],
            "rationale": activity.get("boundary_rationale", ""),
            "supported_empty_confirmed": False,
        }
        errors.extend(_validate_assertion(boundary, valid_evidence, f"{label} boundary"))
    if sequences and len(sequences) != len(set(sequences)):
        errors.append("Ordered activities must not reuse a sequence number")

    assertions = current.get("assertions", [])
    fields_by_activity = {activity_id: set() for activity_id in known_ids}
    for index, assertion in enumerate(assertions, start=1):
        activity_id = str(assertion.get("activity_id", "")).strip()
        label = f"Assertion {index}"
        if activity_id not in known_ids:
            errors.append(f"{label}: choose a valid final activity ID")
            continue
        field = assertion.get("field", "")
        if field not in FIELD_TYPES:
            errors.append(f"{label}: choose a supported field type")
        else:
            fields_by_activity[activity_id].add(field)
        errors.extend(_validate_assertion(assertion, valid_evidence, label))
    for activity_id, fields in fields_by_activity.items():
        missing = set(REQUIRED_ACTIVITY_FIELDS) - fields
        if missing:
            errors.append(
                f"Activity {activity_id}: explicitly annotate or mark unknown for "
                f"{', '.join(sorted(missing))}"
            )
    return errors


def validate_decision_reference(draft: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    activities = draft.get("current_state", {}).get("activities", [])
    activity_ids = {str(item.get("activity_id", "")).strip() for item in activities}
    decisions = draft.get("decision_reference", {}).get("decisions", [])
    decision_ids = [str(item.get("activity_id", "")).strip() for item in decisions]
    if set(decision_ids) != activity_ids or len(decision_ids) != len(activity_ids):
        errors.append("Decision references must cover each final activity exactly once")
    for index, decision in enumerate(decisions, start=1):
        label = f"Decision {decision.get('activity_id') or index}"
        mode = decision.get("primary_mode", "")
        if mode not in RECOMMENDATION_MODES:
            errors.append(f"{label}: choose a primary recommendation mode")
        alternatives = decision.get("acceptable_alternative_modes") or []
        invalid_modes = sorted(set(alternatives) - set(RECOMMENDATION_MODES))
        if invalid_modes:
            errors.append(f"{label}: invalid alternative mode(s): {', '.join(invalid_modes)}")
        if mode in alternatives:
            errors.append(f"{label}: primary mode must not also be an alternative")
        invalid_capabilities = sorted(
            set(decision.get("capabilities") or []) - set(CAPABILITIES)
        )
        if invalid_capabilities:
            errors.append(
                f"{label}: invalid capability label(s): {', '.join(invalid_capabilities)}"
            )
        for field in ("human_oversight_required", "automation_unsafe", "conventional_solution_preferable"):
            if decision.get(field) not in TRISTATE:
                errors.append(f"{label}: choose Yes, No or Unclear for {field}")
        rank = decision.get("priority_rank")
        not_rankable = decision.get("not_rankable") is True
        if not_rankable and rank not in {None, ""}:
            errors.append(f"{label}: priority cannot have a rank and be not-rankable")
        if not not_rankable and (
            not isinstance(rank, int) or isinstance(rank, bool) or rank < 1
        ):
            errors.append(f"{label}: enter a positive priority rank or mark not-rankable")
        if not str(decision.get("rationale", "")).strip():
            errors.append(f"{label}: human rationale is required")
    return errors


def validate_draft(draft: dict[str, Any]) -> list[str]:
    return validate_current_state(draft) + validate_decision_reference(draft)


def _display_assertion(assertion: dict[str, Any]) -> str:
    value = assertion.get("value") or "—"
    evidence = ", ".join(assertion.get("evidence_locators") or []) or "none"
    rationale = assertion.get("rationale") or "—"
    return (
        f"**Value:** {value}  \n"
        f"**State:** {assertion.get('knowledge_state') or 'not set'}  \n"
        f"**Evidence:** {evidence}  \n"
        f"**Rationale:** {rationale}"
    )


def render_preview(draft: dict[str, Any], *, next_version: int | None = None) -> str:
    current = draft["current_state"]
    decision_by_id = {
        item["activity_id"]: item
        for item in draft.get("decision_reference", {}).get("decisions", [])
    }
    lines = [
        "# CON-001 primary annotation preview",
        "",
        f"**Proposed frozen version:** v{next_version:03d}" if next_version else "**Proposed frozen version:** assigned at approval",
        f"**Current-state record schema:** `{CURRENT_SCHEMA_ID}`",
        f"**Private decision record schema:** `{DECISION_SCHEMA_ID}`",
        f"**Before-packet SHA-256:** `{BEFORE_SHA256}`",
        f"**Primary annotator:** {draft.get('draft_metadata', {}).get('annotator_id') or 'not set'}",
        f"**Correction reason:** {draft.get('draft_metadata', {}).get('revision_reason') or 'not applicable for v1'}",
        "**Approval timestamp:** captured in UTC when explicit approval is submitted",
        "",
        "## Current-state reference",
        "",
        f"### Process: {current.get('process_name') or 'not set'}",
    ]
    for field in PROCESS_ASSERTION_FIELDS:
        lines.extend(["", f"#### {field.replace('_', ' ').title()}", _display_assertion(current["process_assertions"][field])])
    lines.extend(["", "### Evidence-derived cue decisions"])
    for cue in current.get("cue_reviews", []):
        lines.append(
            f"- **{cue['cue_id']} — {cue['cue_text']}**: "
            f"{cue.get('disposition') or 'not set'}; final IDs: "
            f"{', '.join(cue.get('final_activity_ids') or []) or 'none'}; "
            f"rationale: {cue.get('rationale') or '—'}"
        )
    lines.extend(["", "### Final activities"])
    assertions_by_activity: dict[str, list[dict[str, Any]]] = {}
    for assertion in current.get("assertions", []):
        assertions_by_activity.setdefault(assertion.get("activity_id", ""), []).append(assertion)
    for activity in current.get("activities", []):
        lines.extend(
            [
                "",
                f"#### {activity.get('activity_id')} — {activity.get('name')}",
                f"- Order state: {activity.get('order_state')}; sequence: {activity.get('sequence') or '—'}",
                f"- Dependencies: {', '.join(activity.get('dependencies') or []) or 'none'}",
                f"- Boundary knowledge state: {activity.get('knowledge_state')}",
                f"- Boundary evidence: {', '.join(activity.get('evidence_locators') or []) or 'none'}",
                f"- Boundary rationale: {activity.get('boundary_rationale') or '—'}",
            ]
        )
        for assertion in assertions_by_activity.get(activity.get("activity_id", ""), []):
            lines.append(
                f"- **{assertion.get('field')}** — {_display_assertion(assertion)}"
            )
    lines.extend(["", "### Unresolved ambiguities"])
    ambiguities = current.get("unresolved_ambiguities", [])
    if ambiguities:
        for ambiguity in ambiguities:
            lines.append(
                f"- **{ambiguity.get('scope') or 'Unspecified'}:** "
                f"{ambiguity.get('ambiguity') or '—'} — treatment: "
                f"{ambiguity.get('treatment') or '—'}"
            )
    else:
        lines.append("- None recorded")

    lines.extend(
        [
            "",
            "## Primary decision reference — never include in the independent-reviewer pack",
        ]
    )
    for activity in current.get("activities", []):
        decision = decision_by_id.get(activity.get("activity_id"), {})
        lines.extend(
            [
                "",
                f"### {activity.get('activity_id')} — {activity.get('name')}",
                f"- Primary mode: {decision.get('primary_mode') or 'not set'}",
                f"- Acceptable alternatives: {', '.join(decision.get('acceptable_alternative_modes') or []) or 'none'}",
                f"- Capabilities: {', '.join(decision.get('capabilities') or []) or 'none'}",
                f"- Human oversight required: {decision.get('human_oversight_required') or 'not set'}",
                f"- Automation unsafe: {decision.get('automation_unsafe') or 'not set'}",
                f"- Conventional solution preferable: {decision.get('conventional_solution_preferable') or 'not set'}",
                f"- Priority: {'not rankable' if decision.get('not_rankable') else decision.get('priority_rank') or 'not set'}",
                f"- Important missing information: {decision.get('important_missing_information') or '—'}",
                f"- Rationale: {decision.get('rationale') or '—'}",
            ]
        )
    return "\n".join(lines)


def build_reviewer_safe_current_state(frozen_current: dict[str, Any]) -> dict[str, Any]:
    """Return the only primary record eligible for a later reviewer pack."""
    if frozen_current.get("schema_id") != CURRENT_SCHEMA_ID:
        raise ValueError("Reviewer projection requires a frozen current-state record")
    allowed = {
        "schema_id",
        "case_id",
        "version",
        "before_packet",
        "annotator",
        "approved_at",
        "reference",
    }
    projected = {key: copy.deepcopy(value) for key, value in frozen_current.items() if key in allowed}
    def keys(value: Any) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {key for child in value.values() for key in keys(child)}
        if isinstance(value, list):
            return {key for child in value for key in keys(child)}
        return set()

    forbidden = {
        "decision_reference",
        "primary_mode",
        "acceptable_alternative_modes",
        "capabilities",
        "human_oversight_required",
        "automation_unsafe",
        "conventional_solution_preferable",
        "priority_rank",
    }
    if keys(projected) & forbidden:
        raise ValueError("Decision-reference content reached reviewer-safe projection")
    return projected


class AnnotationStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.draft_path = self.root / "draft" / "primary_annotation_draft.json"
        self.frozen_root = self.root / "frozen"

    def save_draft(self, draft: dict[str, Any]) -> Path:
        self.draft_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.draft_path.with_suffix(".tmp")
        temporary.write_bytes(canonical_json(draft) + b"\n")
        os.replace(temporary, self.draft_path)
        return self.draft_path

    def load_draft(self) -> dict[str, Any] | None:
        return load_json(self.draft_path) if self.draft_path.is_file() else None

    def frozen_versions(self) -> list[int]:
        if not self.frozen_root.is_dir():
            return []
        versions = []
        for path in self.frozen_root.glob("v[0-9][0-9][0-9]"):
            if path.is_dir():
                versions.append(int(path.name[1:]))
        return sorted(versions)

    def _latest_records(self) -> tuple[dict[str, Any], dict[str, Any], Path] | None:
        versions = self.frozen_versions()
        if not versions:
            return None
        directory = self.frozen_root / f"v{versions[-1]:03d}"
        return (
            load_json(directory / "primary_current_state_reference.v0.1.json"),
            load_json(directory / "primary_decision_reference.v0.1.json"),
            directory,
        )

    def approve(
        self,
        draft: dict[str, Any],
        *,
        explicit_approval: bool,
        preview_sha256: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if not explicit_approval:
            raise AnnotationValidationError(["Explicit human approval is required"])
        expected_preview = preview_fingerprint(draft)
        if preview_sha256 != expected_preview:
            raise AnnotationValidationError(
                ["The worksheet changed after preview; review the complete preview again"]
            )
        errors = validate_draft(draft)
        if errors:
            raise AnnotationValidationError(errors)
        annotator_id = str(draft.get("draft_metadata", {}).get("annotator_id", "")).strip()
        if not annotator_id:
            raise AnnotationValidationError(["Annotator identity or pseudonym is required"])

        latest = self._latest_records()
        version = self.frozen_versions()[-1] + 1 if latest else 1
        revision_reason = str(
            draft.get("draft_metadata", {}).get("revision_reason", "")
        ).strip()
        if version > 1 and not revision_reason:
            raise AnnotationValidationError(
                ["A recorded correction reason is required for a new frozen version"]
            )
        approved_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
        common = {
            "case_id": CASE_ID,
            "version": version,
            "before_packet": copy.deepcopy(draft["before_packet"]),
            "annotator": {"identity_or_pseudonym": annotator_id},
            "approved_at": approved_at,
            "revision_reason": revision_reason or None,
        }
        current_record = {
            "schema_id": CURRENT_SCHEMA_ID,
            **common,
            "reference": copy.deepcopy(draft["current_state"]),
        }
        decision_record = {
            "schema_id": DECISION_SCHEMA_ID,
            **common,
            "current_state_preview_sha256": expected_preview,
            "reference": copy.deepcopy(draft["decision_reference"]),
            "reviewer_pack_eligible": False,
        }
        if latest:
            previous_current, previous_decision, previous_dir = latest
            if (
                previous_current.get("reference") == current_record["reference"]
                and previous_decision.get("reference") == decision_record["reference"]
            ):
                raise AnnotationValidationError(
                    ["A correction version must change the current-state or decision reference"]
                )
            common_supersedes = {
                "version": version - 1,
                "approval_manifest_sha256": sha256_file(
                    previous_dir / "primary_annotation_approval.v0.1.json"
                ),
            }
            current_record["supersedes"] = common_supersedes
            decision_record["supersedes"] = common_supersedes

        version_dir = self.frozen_root / f"v{version:03d}"
        try:
            version_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            raise ImmutableRecordError(f"Frozen version already exists: v{version:03d}") from exc
        current_path = version_dir / "primary_current_state_reference.v0.1.json"
        decision_path = version_dir / "primary_decision_reference.v0.1.json"
        approval_path = version_dir / "primary_annotation_approval.v0.1.json"
        try:
            current_path.write_bytes(canonical_json(current_record) + b"\n")
            decision_path.write_bytes(canonical_json(decision_record) + b"\n")
            approval = {
                "schema_id": APPROVAL_SCHEMA_ID,
                **common,
                "explicit_approval": True,
                "preview_sha256": expected_preview,
                "records": [
                    {
                        "role": "current_state_reference",
                        "path": current_path.name,
                        "sha256": sha256_file(current_path),
                    },
                    {
                        "role": "primary_decision_reference_private",
                        "path": decision_path.name,
                        "sha256": sha256_file(decision_path),
                    },
                ],
            }
            approval_path.write_bytes(canonical_json(approval) + b"\n")
            for path in (current_path, decision_path, approval_path):
                path.chmod(0o444)
        except Exception:
            # Leave any created files in place as evidence; never overwrite a partial freeze.
            raise
        return {
            "version": version,
            "directory": version_dir,
            "current_state_sha256": sha256_file(current_path),
            "decision_reference_sha256": sha256_file(decision_path),
            "approval_manifest_sha256": sha256_file(approval_path),
        }

    def verify_frozen_version(self, version: int) -> None:
        directory = self.frozen_root / f"v{version:03d}"
        approval = load_json(directory / "primary_annotation_approval.v0.1.json")
        for record in approval["records"]:
            if sha256_file(directory / record["path"]) != record["sha256"]:
                raise ImmutableRecordError(
                    f"Frozen record hash mismatch: {record['path']}"
                )
