"""Phase 2 ingestion and explicit Phase 3 extraction screen."""

from pathlib import Path

import streamlit as st

from ai_adoption_engine.workspace.demo_extraction import demo_document_id, demo_text
from ai_adoption_engine.workspace.models import ExecutionMode
from ai_adoption_engine.models.document import IngestionStatus
from ai_adoption_engine.models.extraction import ExtractionStatus
from ai_adoption_engine.presentation.components.status import guard
from ai_adoption_engine.presentation.context import (
    hydrate_workspace,
    refresh_workspace,
    workspace_service,
)


def _safe_name(name: str) -> str:
    return Path(name).name


def render() -> None:
    snapshot = hydrate_workspace()
    if snapshot is None:
        guard("Create or open an assessment first.")
    st.title("Source & Extraction")
    st.write("Supply one text-native process document, inspect ingestion, then explicitly start extraction.")
    mode = snapshot.assessment.execution_mode
    current_ingestion = st.session_state.get("ingestion_result")

    with st.container(border=True):
        st.subheader("1. Document input")
        if mode is ExecutionMode.OFFLINE_DEMO:
            st.caption(
                "Use the approved bundled fixture for the complete offline journey. "
                "Arbitrary documents can be ingested, but scripted extraction will remain disabled."
            )
            input_kind = st.radio(
                "Input source",
                ["Bundled synthetic demo", "Upload PDF or text", "Paste text"],
                horizontal=True,
            )
        else:
            input_kind = st.radio(
                "Input source",
                ["Upload PDF or text", "Paste text"],
                horizontal=True,
            )
        uploaded = None
        pasted = None
        if input_kind == "Bundled synthetic demo":
            st.text_area("Synthetic document preview", demo_text(), height=220, disabled=True)
        elif input_kind == "Upload PDF or text":
            uploaded = st.file_uploader(
                "Current-state process document",
                type=["pdf", "txt"],
                accept_multiple_files=False,
            )
        else:
            pasted = st.text_area(
                "Paste current-state process text",
                height=220,
                placeholder="Paste the process documentation here…",
            )
        replace_confirmed = False
        if current_ingestion is not None:
            replace_confirmed = st.checkbox(
                "If this source differs, make the current candidate/review/assessment/package chain non-current. Historical milestone revisions will be retained."
            )
        if st.button("Ingest document", type="primary"):
            try:
                if input_kind == "Bundled synthetic demo":
                    result = workspace_service().ingest_upload(
                        snapshot.assessment.assessment_id,
                        raw_text=demo_text(),
                        replace_existing=replace_confirmed,
                        source_label="synthetic_complaint_process.txt",
                    )
                elif uploaded is not None:
                    result = workspace_service().ingest_upload(
                        snapshot.assessment.assessment_id,
                        payload=uploaded.getvalue(),
                        filename=_safe_name(uploaded.name),
                        replace_existing=replace_confirmed,
                    )
                elif pasted and pasted.strip():
                    result = workspace_service().ingest_upload(
                        snapshot.assessment.assessment_id,
                        raw_text=pasted,
                        replace_existing=replace_confirmed,
                        source_label="Pasted text",
                    )
                else:
                    st.error("Provide one document or pasted text.")
                    return
                refresh_workspace()
                if result.status is IngestionStatus.FAILED:
                    st.error("Document ingestion failed.")
                else:
                    st.success("Document ingestion completed.")
                st.rerun()
            except Exception as exc:
                st.error(f"Document ingestion could not complete: {type(exc).__name__}")

    current_ingestion = st.session_state.get("ingestion_result")
    if current_ingestion is None:
        return
    with st.container(border=True):
        st.subheader("2. Ingestion result")
        if current_ingestion.status is IngestionStatus.SUCCESS:
            st.success("Text extracted successfully.")
        elif current_ingestion.status is IngestionStatus.PARTIAL:
            st.warning("Text was extracted with warnings.")
        else:
            st.error("No usable document was produced.")
        for issue in current_ingestion.issues:
            message = issue.message
            if "extractable" in message.lower() or "ocr" in message.lower():
                message += " OCR is outside the MVP; provide a text-native PDF."
            (st.error if issue.severity.value == "error" else st.warning)(message)
        document = current_ingestion.document
        if document is None:
            return
        columns = st.columns(4)
        columns[0].metric("Input", document.source.input_type.value.replace("_", " ").title())
        columns[1].metric("Pages", document.metadata.page_count or "—")
        columns[2].metric("Text blocks", len(document.blocks))
        columns[3].metric("Size", f"{document.source.byte_size:,} bytes")
        with st.expander("Extracted-text preview"):
            st.code(document.canonical_text[:8000], language=None, wrap_lines=True)
            if len(document.canonical_text) > 8000:
                st.caption("Preview truncated at 8,000 characters.")

    with st.container(border=True):
        st.subheader("3. Candidate process extraction")
        if mode is ExecutionMode.OFFLINE_DEMO and document.document_id != demo_document_id():
            st.warning(
                "Scripted extraction is disabled: this is not the approved bundled demo document."
            )
            extraction_enabled = False
        else:
            extraction_enabled = True
        candidate_result = st.session_state.get("candidate_extraction_result")
        if candidate_result is None:
            if st.button(
                "Extract candidate process",
                type="primary",
                disabled=not extraction_enabled,
            ):
                try:
                    result = workspace_service().extract(snapshot.assessment.assessment_id)
                    refresh_workspace()
                    if result.status is ExtractionStatus.FAILED:
                        st.error("Candidate extraction failed.")
                    else:
                        st.success("Candidate extraction completed. Human review is required.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        else:
            st.warning("CANDIDATE / UNCONFIRMED PROCESS EXTRACTION")
            st.write(f"Status: {candidate_result.status.value}")
            for issue in candidate_result.issues:
                message = issue.message
                if issue.error_category:
                    message += f" Category: {issue.error_category.value}."
                if issue.http_status_code:
                    message += f" HTTP {issue.http_status_code}."
                st.warning(message)
            if candidate_result.candidate:
                st.write(
                    f"Candidate process: {candidate_result.candidate.process_name.value or 'Unknown'} · "
                    f"{len(candidate_result.candidate.steps)} activities"
                )
                if st.button("Start human review", type="primary"):
                    workspace_service().start_review(snapshot.assessment.assessment_id)
                    refresh_workspace()
                    st.success("Review session created. Open Process Review.")
                    st.rerun()
