from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import streamlit as st

from evaluation.primary_annotation.con001 import (
    ACTION_CUES,
    BEFORE_RELATIVE_PATH,
    BEFORE_SHA256,
    CASE_ID,
    CASE_TITLE,
    EVIDENCE_CATALOG,
    PROJECT_ROOT,
    load_frozen_before,
)
from evaluation.primary_annotation.service import (
    CAPABILITIES,
    CUE_DISPOSITIONS,
    FIELD_TYPES,
    KNOWLEDGE_STATES,
    ORDER_STATES,
    PROCESS_ASSERTION_FIELDS,
    RECOMMENDATION_MODES,
    TRISTATE,
    AnnotationStore,
    AnnotationValidationError,
    new_draft,
    preview_fingerprint,
    render_preview,
    validate_current_state,
    validate_decision_reference,
)


STORE_ROOT = PROJECT_ROOT / "evaluation" / "artifacts" / "primary_annotations" / "con-001"
store = AnnotationStore(STORE_ROOT)
before_text = load_frozen_before()

st.set_page_config(
    page_title="CON-001 primary annotation",
    page_icon=":material/fact_check:",
    layout="wide",
)

st.session_state.setdefault("pa_draft", store.load_draft() or new_draft())
st.session_state.setdefault("pa_preview_sha256", None)
st.session_state.setdefault("pa_notice", None)
draft: dict[str, Any] = st.session_state.pa_draft


def _clear_widget_state() -> None:
    for key in list(st.session_state):
        if str(key).startswith("pa_widget_"):
            del st.session_state[key]


def _records(value: Any) -> list[dict[str, Any]]:
    records = value.to_dict("records") if hasattr(value, "to_dict") else list(value)
    cleaned: list[dict[str, Any]] = []
    for record in records:
        item: dict[str, Any] = {}
        for key, cell in record.items():
            if isinstance(cell, float) and math.isnan(cell):
                cell = None
            if isinstance(cell, tuple):
                cell = list(cell)
            item[key] = cell
        cleaned.append(item)
    return cleaned


def _csv_ids(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _knowledge_index(value: str) -> int:
    options = ["Choose…", *KNOWLEDGE_STATES]
    return options.index(value) if value in options else 0


def _evidence_panel() -> None:
    with st.container(border=True):
        st.subheader("Frozen before-state evidence")
        st.caption(
            f"Read-only source: `{BEFORE_RELATIVE_PATH.as_posix()}` · SHA-256 `{BEFORE_SHA256}`"
        )
        st.code(before_text, language=None)
        st.markdown("**Permitted evidence locators**")
        for item in EVIDENCE_CATALOG:
            st.markdown(
                f"**{item['evidence_id']}** · `{item['locator']}`  \n{item['text']}"
            )


def _save_current_draft() -> None:
    draft["draft_metadata"]["annotator_id"] = st.session_state.get(
        "pa_widget_annotator", ""
    ).strip()
    draft["draft_metadata"]["revision_reason"] = st.session_state.get(
        "pa_widget_revision_reason", ""
    ).strip()
    path = store.save_draft(draft)
    st.session_state.pa_notice = f"Working draft saved to {path.relative_to(PROJECT_ROOT)}"


st.title("CON-001 primary annotation")
st.caption("Offline Phase 8 worksheet · human-owned reference construction")
st.warning(
    "This worksheet contains only the frozen before-state packet. Evidence-derived action "
    "phrases are unconfirmed cues—not reference activities or recommendations."
)

with st.sidebar:
    st.subheader("Worksheet status")
    st.write(f"**Case:** {CASE_ID}")
    st.write(f"**Neutral title:** {CASE_TITLE}")
    st.code(BEFORE_SHA256, language=None)
    st.caption("No provider, engine, baseline, external research or after-state access.")
    st.text_input(
        "Primary annotator identity or pseudonym",
        value=draft.get("draft_metadata", {}).get("annotator_id", ""),
        key="pa_widget_annotator",
    )
    if store.frozen_versions():
        st.text_area(
            "Correction reason for a new frozen version",
            value=draft.get("draft_metadata", {}).get("revision_reason", ""),
            key="pa_widget_revision_reason",
            help="Required after v1. Existing frozen records are never overwritten.",
        )
    else:
        st.session_state.setdefault("pa_widget_revision_reason", "")
    if st.button("Save working draft", icon=":material/save:", width="stretch"):
        _save_current_draft()
        st.rerun()
    st.caption("Section buttons save immediately; this button also captures identity metadata.")
    if store.load_draft() is not None and st.button(
        "Reload saved draft", icon=":material/refresh:", width="stretch"
    ):
        st.session_state.pa_draft = store.load_draft()
        st.session_state.pa_preview_sha256 = None
        _clear_widget_state()
        st.rerun()
    versions = store.frozen_versions()
    st.write(f"**Frozen versions:** {', '.join(f'v{item:03d}' for item in versions) or 'none'}")

if st.session_state.pa_notice:
    st.success(st.session_state.pa_notice)
    st.session_state.pa_notice = None

section = st.segmented_control(
    "Worksheet section",
    ["Evidence", "Process", "Activities", "Assertions", "Decisions", "Preview & freeze"],
    default="Evidence",
    key="pa_widget_section",
    persist_state="session",
    width="stretch",
)

if section == "Evidence":
    _evidence_panel()
    with st.container(border=True):
        st.subheader("Unconfirmed action cues")
        st.info(
            "These phrases were copied from the frozen evidence only to help you consider "
            "activity boundaries. You must include, merge, split, reject or mark each unclear."
        )
        st.table(
            [
                {
                    "Cue": cue["cue_id"],
                    "Evidence-derived phrase": cue["text"],
                    "Locator": ", ".join(cue["evidence_locators"]),
                    "Status": "UNCONFIRMED",
                }
                for cue in ACTION_CUES
            ]
        )

elif section == "Process":
    _evidence_panel()
    st.header("Define the process")
    st.write(
        "Enter your own proposed process framing. For each field, make an explicit "
        "knowledge-state judgement."
    )
    with st.form("pa_process_form"):
        process_name = st.text_input(
            "Proposed process name",
            value=draft["current_state"].get("process_name", ""),
        )
        entered: dict[str, dict[str, Any]] = {}
        for field in PROCESS_ASSERTION_FIELDS:
            existing = draft["current_state"]["process_assertions"][field]
            with st.container(border=True):
                st.subheader(field.replace("_", " ").capitalize())
                value = st.text_area(
                    "Your proposed value",
                    value=existing.get("value", ""),
                    key=f"pa_widget_process_{field}_value",
                )
                state = st.selectbox(
                    "Knowledge state",
                    ["Choose…", *KNOWLEDGE_STATES],
                    index=_knowledge_index(existing.get("knowledge_state", "")),
                    key=f"pa_widget_process_{field}_state",
                )
                locators = st.multiselect(
                    "Supporting evidence locators",
                    [item["evidence_id"] for item in EVIDENCE_CATALOG],
                    default=existing.get("evidence_locators", []),
                    key=f"pa_widget_process_{field}_evidence",
                )
                rationale = st.text_area(
                    "Inference, uncertainty or boundary rationale",
                    value=existing.get("rationale", ""),
                    key=f"pa_widget_process_{field}_rationale",
                )
                confirmed = st.checkbox(
                    "If using supported empty: I confirm the cited evidence explicitly establishes absence",
                    value=existing.get("supported_empty_confirmed", False),
                    key=f"pa_widget_process_{field}_empty",
                )
                entered[field] = {
                    "field": field,
                    "value": value.strip(),
                    "knowledge_state": "" if state == "Choose…" else state,
                    "evidence_locators": locators,
                    "rationale": rationale.strip(),
                    "supported_empty_confirmed": confirmed,
                }
        if st.form_submit_button("Save process section", icon=":material/save:"):
            draft["current_state"]["process_name"] = process_name.strip()
            draft["current_state"]["process_assertions"] = entered
            st.session_state.pa_preview_sha256 = None
            store.save_draft(draft)
            st.success("Process section saved to the persistent working draft.")

elif section == "Activities":
    _evidence_panel()
    st.header("Construct activity boundaries and order")
    st.info(
        "Every cue is unconfirmed. Your disposition and final activities are substantive "
        "primary-annotator decisions. Use comma-separated final IDs for split or merge mappings."
    )
    cue_rows = [
        {
            **item,
            "source_locators": ", ".join(item.get("source_locators", [])),
            "final_activity_ids": ", ".join(item.get("final_activity_ids", [])),
        }
        for item in draft["current_state"]["cue_reviews"]
    ]
    edited_cues = st.data_editor(
        cue_rows,
        key="pa_widget_cues",
        hide_index=True,
        num_rows="fixed",
        disabled=["cue_id", "cue_text", "source_locators"],
        column_config={
            "cue_id": "Cue",
            "cue_text": "Unconfirmed evidence-derived phrase",
            "source_locators": "Source",
            "disposition": st.column_config.SelectboxColumn(
                "Your disposition", options=list(CUE_DISPOSITIONS), required=False
            ),
            "final_activity_ids": "Resulting activity ID(s)",
            "rationale": "Your rationale",
        },
    )

    activity_rows = draft["current_state"].get("activities") or [
        {
            "activity_id": "",
            "name": "",
            "order_state": "",
            "sequence": None,
            "dependencies": [],
            "knowledge_state": "",
            "evidence_locators": [],
            "boundary_rationale": "",
        }
    ]
    activity_ids = [item.get("activity_id", "") for item in activity_rows if item.get("activity_id")]
    st.subheader("Your final activities")
    edited_activities = st.data_editor(
        activity_rows,
        key="pa_widget_activities",
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "activity_id": "Activity ID",
            "name": "Your activity name",
            "order_state": st.column_config.SelectboxColumn(
                "Order/dependency state", options=list(ORDER_STATES), required=False
            ),
            "sequence": st.column_config.NumberColumn("Sequence", min_value=1, step=1),
            "dependencies": st.column_config.MultiselectColumn(
                "Dependencies", options=activity_ids
            ),
            "knowledge_state": st.column_config.SelectboxColumn(
                "Boundary knowledge state", options=list(KNOWLEDGE_STATES), required=False
            ),
            "evidence_locators": st.column_config.MultiselectColumn(
                "Boundary evidence", options=[item["evidence_id"] for item in EVIDENCE_CATALOG]
            ),
            "boundary_rationale": "Your boundary/order rationale",
        },
    )
    if st.button("Save activity section", icon=":material/save:"):
        cue_values = _records(edited_cues)
        for item in cue_values:
            item["source_locators"] = _csv_ids(item.get("source_locators"))
            item["final_activity_ids"] = _csv_ids(item.get("final_activity_ids"))
        activities = []
        for item in _records(edited_activities):
            if not str(item.get("activity_id") or "").strip() and not str(item.get("name") or "").strip():
                continue
            sequence = item.get("sequence")
            item["sequence"] = int(sequence) if isinstance(sequence, (int, float)) and sequence else None
            item["dependencies"] = _csv_ids(item.get("dependencies"))
            item["evidence_locators"] = _csv_ids(item.get("evidence_locators"))
            activities.append(item)
        draft["current_state"]["cue_reviews"] = cue_values
        draft["current_state"]["activities"] = activities
        retained_ids = {item["activity_id"] for item in activities}
        draft["current_state"]["assertions"] = [
            item
            for item in draft["current_state"].get("assertions", [])
            if item.get("activity_id") in retained_ids
        ]
        draft["decision_reference"]["decisions"] = [
            item
            for item in draft["decision_reference"].get("decisions", [])
            if item.get("activity_id") in retained_ids
        ]
        st.session_state.pa_preview_sha256 = None
        store.save_draft(draft)
        st.success("Activity section saved to the persistent working draft.")

elif section == "Assertions":
    _evidence_panel()
    st.header("Annotate activity attributes and assertions")
    activities = draft["current_state"].get("activities", [])
    if not activities:
        st.info("Save at least one final activity before completing assertions.")
    else:
        existing = draft["current_state"].get("assertions", [])
        existing_keys = {(item.get("activity_id"), item.get("field")) for item in existing}
        assertion_rows = list(existing)
        for activity in activities:
            for field in ("actor", "system", "input", "output"):
                if (activity["activity_id"], field) not in existing_keys:
                    assertion_rows.append(
                        {
                            "activity_id": activity["activity_id"],
                            "field": field,
                            "value": "",
                            "knowledge_state": "",
                            "evidence_locators": [],
                            "rationale": "",
                            "supported_empty_confirmed": False,
                        }
                    )
        edited_assertions = st.data_editor(
            assertion_rows,
            key="pa_widget_assertions",
            hide_index=True,
            num_rows="dynamic",
            column_config={
                "activity_id": st.column_config.SelectboxColumn(
                    "Activity", options=[item["activity_id"] for item in activities], required=True
                ),
                "field": st.column_config.SelectboxColumn(
                    "Field", options=list(FIELD_TYPES), required=True
                ),
                "value": "Your value (leave blank for unknown/supported empty)",
                "knowledge_state": st.column_config.SelectboxColumn(
                    "Knowledge state", options=list(KNOWLEDGE_STATES), required=False
                ),
                "evidence_locators": st.column_config.MultiselectColumn(
                    "Evidence", options=[item["evidence_id"] for item in EVIDENCE_CATALOG]
                ),
                "rationale": "Inference/uncertainty rationale",
                "supported_empty_confirmed": st.column_config.CheckboxColumn(
                    "Evidence explicitly establishes absence"
                ),
            },
        )
        st.caption(
            "Use an additional ‘other’ row for any material assertion not covered by actor, "
            "system, input or output. Unknown values remain blank."
        )
        ambiguity_rows = draft["current_state"].get("unresolved_ambiguities") or [
            {"scope": "", "ambiguity": "", "why_it_matters": "", "treatment": ""}
        ]
        st.subheader("Unresolved ambiguity")
        edited_ambiguities = st.data_editor(
            ambiguity_rows,
            key="pa_widget_ambiguities",
            hide_index=True,
            num_rows="dynamic",
            column_config={
                "scope": "Activity ID or process scope",
                "ambiguity": "Ambiguity or missing information",
                "why_it_matters": "Why it matters",
                "treatment": st.column_config.SelectboxColumn(
                    "Treatment",
                    options=["unknown", "dual_label", "not_rankable", "blocks_completion"],
                ),
            },
        )
        if st.button("Save assertion section", icon=":material/save:"):
            assertions = _records(edited_assertions)
            for item in assertions:
                item["evidence_locators"] = _csv_ids(item.get("evidence_locators"))
            ambiguities = [
                item
                for item in _records(edited_ambiguities)
                if any(str(value or "").strip() for value in item.values())
            ]
            draft["current_state"]["assertions"] = assertions
            draft["current_state"]["unresolved_ambiguities"] = ambiguities
            st.session_state.pa_preview_sha256 = None
            store.save_draft(draft)
            st.success("Assertion section saved to the persistent working draft.")

elif section == "Decisions":
    st.header("Record your independent primary decision reference")
    st.error(
        "Private primary-annotator section. These answers are stored separately and must "
        "never be included in the independent-reviewer pack."
    )
    activities = draft["current_state"].get("activities", [])
    if not activities:
        st.info("Save the final activity list before entering decision judgements.")
    else:
        existing_by_id = {
            item.get("activity_id"): item
            for item in draft["decision_reference"].get("decisions", [])
        }
        decision_rows = []
        for activity in activities:
            row = existing_by_id.get(activity["activity_id"], {})
            decision_rows.append(
                {
                    "activity_id": activity["activity_id"],
                    "activity_name": activity["name"],
                    "primary_mode": row.get("primary_mode", ""),
                    "acceptable_alternative_modes": row.get("acceptable_alternative_modes", []),
                    "capabilities": row.get("capabilities", []),
                    "human_oversight_required": row.get("human_oversight_required", ""),
                    "automation_unsafe": row.get("automation_unsafe", ""),
                    "conventional_solution_preferable": row.get("conventional_solution_preferable", ""),
                    "priority_rank": row.get("priority_rank"),
                    "not_rankable": row.get("not_rankable", False),
                    "important_missing_information": row.get("important_missing_information", ""),
                    "rationale": row.get("rationale", ""),
                }
            )
        edited_decisions = st.data_editor(
            decision_rows,
            key="pa_widget_decisions",
            hide_index=True,
            num_rows="fixed",
            disabled=["activity_id", "activity_name"],
            column_config={
                "activity_id": "Activity ID",
                "activity_name": "Your final activity",
                "primary_mode": st.column_config.SelectboxColumn(
                    "Your primary mode", options=list(RECOMMENDATION_MODES), required=False
                ),
                "acceptable_alternative_modes": st.column_config.MultiselectColumn(
                    "Acceptable alternatives", options=list(RECOMMENDATION_MODES)
                ),
                "capabilities": st.column_config.MultiselectColumn(
                    "Applicable capabilities", options=list(CAPABILITIES)
                ),
                "human_oversight_required": st.column_config.SelectboxColumn(
                    "Human oversight", options=list(TRISTATE), required=False
                ),
                "automation_unsafe": st.column_config.SelectboxColumn(
                    "Automation unsafe", options=list(TRISTATE), required=False
                ),
                "conventional_solution_preferable": st.column_config.SelectboxColumn(
                    "Conventional solution preferable", options=list(TRISTATE), required=False
                ),
                "priority_rank": st.column_config.NumberColumn(
                    "Priority rank", min_value=1, step=1
                ),
                "not_rankable": st.column_config.CheckboxColumn("Not rankable"),
                "important_missing_information": "Important missing information",
                "rationale": "Your rationale",
            },
        )
        with st.expander("Neutral mode and capability definitions"):
            st.markdown(
                "- **AUTOMATE:** AI could perform the activity or a substantial operational part.\n"
                "- **AUGMENT:** AI could assist while a human remains actively involved.\n"
                "- **INVESTIGATE_FURTHER:** evidence is insufficient for a responsible recommendation.\n"
                "- **DO_NOT_RECOMMEND:** AI is not an appropriate response to the documented activity."
            )
            for capability in CAPABILITIES:
                st.markdown(f"- `{capability}`")
        if st.button("Save decision section", icon=":material/save:"):
            decisions = _records(edited_decisions)
            for item in decisions:
                item.pop("activity_name", None)
                item["acceptable_alternative_modes"] = _csv_ids(
                    item.get("acceptable_alternative_modes")
                )
                item["capabilities"] = _csv_ids(item.get("capabilities"))
                rank = item.get("priority_rank")
                item["priority_rank"] = int(rank) if isinstance(rank, (int, float)) and rank else None
            draft["decision_reference"]["decisions"] = decisions
            st.session_state.pa_preview_sha256 = None
            store.save_draft(draft)
            st.success("Private decision section saved to the persistent working draft.")

elif section == "Preview & freeze":
    st.header("Preview and explicit approval")
    draft["draft_metadata"]["annotator_id"] = st.session_state.get(
        "pa_widget_annotator", ""
    ).strip()
    draft["draft_metadata"]["revision_reason"] = st.session_state.get(
        "pa_widget_revision_reason", ""
    ).strip()
    current_errors = validate_current_state(draft)
    decision_errors = validate_decision_reference(draft)
    if current_errors or decision_errors:
        st.error("The worksheet is not ready to freeze.")
        for error in current_errors + decision_errors:
            st.markdown(f"- {error}")
    else:
        versions = store.frozen_versions()
        next_version = versions[-1] + 1 if versions else 1
        preview = render_preview(draft, next_version=next_version)
        with st.container(border=True):
            st.markdown(preview)
        current_fingerprint = preview_fingerprint(draft)
        st.code(f"Preview SHA-256: {current_fingerprint}", language=None)
        if st.button("I have reviewed this complete preview", icon=":material/preview:"):
            st.session_state.pa_preview_sha256 = current_fingerprint
            st.success("Preview acknowledged. Any worksheet change will require a new preview.")
        preview_current = st.session_state.pa_preview_sha256 == current_fingerprint
        if not preview_current:
            st.warning("Review and acknowledge the complete current preview before approval.")
        explicit = st.checkbox(
            "I am the primary annotator and explicitly approve exactly this preview for immutable freezing.",
            disabled=not preview_current,
            key="pa_widget_explicit_approval",
        )
        if st.button(
            "Freeze approved primary annotation",
            type="primary",
            icon=":material/lock:",
            disabled=not (preview_current and explicit),
        ):
            try:
                result = store.approve(
                    draft,
                    explicit_approval=explicit,
                    preview_sha256=current_fingerprint,
                )
            except AnnotationValidationError as exc:
                for error in exc.errors:
                    st.error(error)
            else:
                st.session_state.pa_notice = (
                    f"Frozen v{result['version']:03d}. Current-state and private decision "
                    "records were stored separately."
                )
                st.session_state.pa_preview_sha256 = None
                st.rerun()
