"""Customer-facing supporting-evidence workflow for the Process Journey page."""

from __future__ import annotations

from datetime import UTC, datetime

import streamlit as st

from ai_adoption_engine.models.enums import CriterionName, KnowledgeState
from ai_adoption_engine.models.formal_evidence import (
    AttemptStatus,
    CoveredPeriod,
    DocumentCategory,
    EvidenceClassification,
    FormalTargetKind,
    MAX_SUPPORTING_FILE_BYTES,
    ReadinessStatus,
    ReviewAction,
    ReviewerDeclaration,
    REVIEWER_DECLARATION_SCHEMA,
    FORMAL_EVIDENCE_FAMILY,
)
from ai_adoption_engine.models.four_gate_assessment import CapabilitySignalName
from ai_adoption_engine.supporting_evidence.composition import (
    DEFAULT_SUPPORTING_EVIDENCE_CONFIGURATION,
)
from ai_adoption_engine.supporting_evidence.conversion import MappingQueueStatus
from ai_adoption_engine.supporting_evidence.errors import (
    SupportingEvidenceIncompletePreparationError,
    SupportingEvidenceInterruptedError,
    SupportingEvidenceServiceError,
)
from ai_adoption_engine.supporting_evidence.extraction import (
    SUPPORTING_EVIDENCE_PROVIDER_DISCLOSURE,
)
from ai_adoption_engine.supporting_evidence.openai import (
    load_supporting_evidence_openai_configuration,
)
from ai_adoption_engine.supporting_evidence.review import ReviewQueueStatus
from ai_adoption_engine.presentation.supporting_evidence_ui import (
    clear_supporting_action_token,
    supporting_action_token,
    supporting_evidence_services,
)


_DECLARATION_LABEL = (
    "I declare that this name and organisational role are accurate for this review; "
    "my identity and authority are recorded locally and are not authenticated."
)
_STATUS_LABELS = {
    AttemptStatus.STARTED: "Running",
    AttemptStatus.SUCCEEDED: "Complete",
    AttemptStatus.PARTIAL: "Partial",
    AttemptStatus.FAILED: "Failed",
    AttemptStatus.INTERRUPTED: "Interrupted",
    AttemptStatus.ABANDONED: "Abandoned",
}


def _friendly(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").strip().title()


def _declaration(prefix: str) -> ReviewerDeclaration | None:
    name = st.text_input("Name", key=f"{prefix}-reviewer-name")
    role = st.text_input("Organisational role", key=f"{prefix}-reviewer-role")
    declared = st.checkbox(_DECLARATION_LABEL, key=f"{prefix}-reviewer-declaration")
    if not name.strip() or not role.strip() or not declared:
        return None
    return ReviewerDeclaration(
        schema_version=REVIEWER_DECLARATION_SCHEMA,
        contract_family=FORMAL_EVIDENCE_FAMILY,
        reviewer_display_name=name.strip(),
        declared_organisational_role=role.strip(),
        identity_and_authority_locally_declared_not_authenticated=True,
        declared_at=datetime.now(UTC),
    )


def _safe_error(message: str) -> None:
    st.error(message)


def _document_metadata(repository, lifecycle_id: str, document_id: str):
    revisions = repository.metadata_revisions_for_document(lifecycle_id, document_id)
    return revisions[-1] if revisions else None


def _progress(bundle, lifecycle_id: str) -> None:
    documents = bundle.repository.current_documents(lifecycle_id)
    extracted = 0
    for document in documents:
        attempt = bundle.repository.latest_extraction_attempt(
            formal_lifecycle_id=lifecycle_id,
            document_id=document.document_id,
        )
        if attempt is not None and attempt.status in {
            AttemptStatus.SUCCEEDED,
            AttemptStatus.PARTIAL,
        }:
            extracted += 1
    review = bundle.reviews.get_review_queue(lifecycle_id).progress
    mapping = bundle.formal_inputs.get_mapping_queue(lifecycle_id)
    mapped = sum(
        item.status in {MappingQueueStatus.MAPPED, MappingQueueStatus.CONTEXT_ONLY}
        for item in mapping.items
    )
    columns = st.columns(4)
    columns[0].metric("Documents", len(documents))
    columns[1].metric("Extracted", f"{extracted}/{len(documents)}")
    columns[2].metric(
        "Reviewed",
        f"{review.total_current_proposals - review.unreviewed_proposals}/{review.total_current_proposals}",
    )
    eligible = sum(
        item.status
        in {
            MappingQueueStatus.AWAITING_MAPPING,
            MappingQueueStatus.MAPPED,
            MappingQueueStatus.CONTEXT_ONLY,
        }
        for item in mapping.items
    )
    columns[3].metric("Mapped or context only", f"{mapped}/{eligible}")


def _render_upload(bundle, lineage) -> None:
    st.subheader("1. Add documents")
    st.write(
        "Add organisational evidence such as volumes, systems, data quality, controls, "
        "ownership, constraints, cost, effort, service levels, or performance information."
    )
    st.info(
        "These documents supplement the approved process. They do not replace it, and "
        "the original source process must not be uploaded again."
    )
    st.caption(
        f"Accepted formats: text-native PDF and plain text. Maximum file size: "
        f"{MAX_SUPPORTING_FILE_BYTES // (1024 * 1024)} MiB."
    )
    uploaded = st.file_uploader(
        "Supporting document",
        type=("pdf", "txt"),
        key="supporting-document-upload",
    )
    description = st.text_area("Document description", key="supporting-description")
    categories = tuple(DocumentCategory)
    primary = st.selectbox(
        "Primary evidence category",
        categories,
        format_func=lambda item: item.value.capitalize(),
        key="supporting-primary-category",
    )
    additional = st.multiselect(
        "Additional evidence categories (optional)",
        tuple(item for item in categories if item is not primary),
        format_func=lambda item: item.value.capitalize(),
        key="supporting-additional-categories",
    )
    owner = st.text_input(
        "Source organisation or owner (optional)", key="supporting-source-owner"
    )
    has_period = st.checkbox(
        "This document covers a specific period", key="supporting-has-period"
    )
    covered = None
    if has_period:
        start = st.date_input("Period starts", key="supporting-period-start")
        end = st.date_input("Period ends", key="supporting-period-end")
        try:
            covered = CoveredPeriod(starts_on=start, ends_on=end)
        except Exception:
            st.warning("The covered period end must be on or after its start.")
    submitter = _declaration("supporting-upload")
    if st.button("Add supporting document", type="primary"):
        if uploaded is None:
            _safe_error("Choose a PDF or plain-text supporting document first.")
            return
        if not description.strip() or submitter is None or (has_period and covered is None):
            _safe_error("Complete the description and reviewer declaration before adding the document.")
            return
        key = f"intake:{lineage.formal_lifecycle_id}:{uploaded.name}"
        try:
            result = bundle.intake.accept(
                lineage=lineage,
                request_token=supporting_action_token(key),
                filename=uploaded.name,
                raw_bytes=uploaded.getvalue(),
                description=description.strip(),
                primary_category=primary,
                additional_categories=tuple(additional),
                source_organisation_or_owner=owner.strip() or None,
                covered_period=covered,
                submitter=submitter,
            )
            ingest_key = f"ingest:{result.document.document_id}"
            bundle.ingestion.ingest(
                lineage=lineage,
                document_id=result.document.document_id,
                request_token=supporting_action_token(ingest_key),
            )
        except SupportingEvidenceServiceError:
            _safe_error(
                "The document could not be added safely. Check that it is a supported, "
                "text-readable file and is not the original process document."
            )
            return
        clear_supporting_action_token(key)
        clear_supporting_action_token(ingest_key)
        st.success("Supporting document added and checked locally.")
        st.rerun()


def _render_documents(bundle, lineage) -> tuple:
    current = bundle.repository.current_documents(lineage.formal_lifecycle_id)
    if not current:
        st.caption("No supporting documents have been added yet.")
        return current
    st.markdown("**Current documents**")
    for document in current:
        metadata = _document_metadata(
            bundle.repository, lineage.formal_lifecycle_id, document.document_id
        )
        ingestion = bundle.repository.latest_ingestion_attempt(
            formal_lifecycle_id=lineage.formal_lifecycle_id,
            document_id=document.document_id,
        )
        extraction = bundle.repository.latest_extraction_attempt(
            formal_lifecycle_id=lineage.formal_lifecycle_id,
            document_id=document.document_id,
        )
        with st.container(border=True):
            st.markdown(f"**{document.original_filename}**")
            if metadata is not None:
                st.caption(metadata.primary_category.value.capitalize())
            st.write("Upload: Stored locally")
            st.write(
                "Ingestion: "
                + ("Not started" if ingestion is None else _STATUS_LABELS[ingestion.status])
            )
            st.write(
                "Extraction: "
                + ("Not started" if extraction is None else _STATUS_LABELS[extraction.status])
            )
    all_documents = bundle.repository.documents_for_lifecycle(
        lineage.formal_lifecycle_id
    )
    historical = tuple(item for item in all_documents if item not in current)
    with st.expander("History and audit details", expanded=False):
        if not historical:
            st.caption("No superseded supporting documents.")
        for document in historical:
            st.write(f"{document.original_filename} · Superseded")
            st.caption(document.created_at.isoformat())
    return current


def _provider_summary() -> tuple[str, str] | None:
    try:
        config = load_supporting_evidence_openai_configuration(
            DEFAULT_SUPPORTING_EVIDENCE_CONFIGURATION
        )
    except Exception:
        return None
    return config.provider.title(), config.model


def _render_extraction(bundle, lineage, documents: tuple) -> None:
    st.subheader("2. Extract evidence")
    st.write(
        "Extraction creates proposals only. Every proposal must be reviewed by a person "
        "before it can contribute to formal inputs."
    )
    provider = _provider_summary()
    for document in documents:
        ingestion = bundle.repository.latest_ingestion_attempt(
            formal_lifecycle_id=lineage.formal_lifecycle_id,
            document_id=document.document_id,
        )
        latest = bundle.repository.latest_extraction_attempt(
            formal_lifecycle_id=lineage.formal_lifecycle_id,
            document_id=document.document_id,
        )
        with st.expander(document.original_filename, expanded=latest is None):
            if ingestion is None or ingestion.status is not AttemptStatus.SUCCEEDED:
                st.warning("This document did not complete local ingestion.")
                continue
            if latest is not None:
                st.write(f"Current extraction state: **{_STATUS_LABELS[latest.status]}**")
            st.markdown("**External provider disclosure**")
            st.write(SUPPORTING_EVIDENCE_PROVIDER_DISCLOSURE)
            if provider is None:
                st.warning(
                    "External extraction is not configured. Stored documents and history "
                    "remain available, but no document can be transmitted."
                )
            else:
                st.caption(f"Configured provider: {provider[0]} · {provider[1]}")
                st.caption(
                    "Only this supporting document is sent for candidate-evidence extraction."
                )
            declarant = st.text_input(
                "Consent declarant name",
                key=f"consent-name-{document.document_id}",
            )
            consent = st.checkbox(
                "I consent to sending this supporting document to the provider shown above",
                key=f"consent-choice-{document.document_id}",
            )
            consent_col, decline_col = st.columns(2)
            if consent_col.button(
                "Save consent",
                key=f"save-consent-{document.document_id}",
                disabled=provider is None or not consent or not declarant.strip(),
            ):
                try:
                    extraction_service = bundle.extraction()
                    extraction_service.record_provider_consent(
                        lineage=lineage,
                        document_id=document.document_id,
                        request_token=supporting_action_token(
                            f"consent:yes:{document.document_id}"
                        ),
                        explicit_consent=True,
                        declarant_name=declarant.strip(),
                    )
                except Exception:
                    _safe_error("Consent could not be recorded safely. No document was sent.")
                    continue
                clear_supporting_action_token(f"consent:yes:{document.document_id}")
                st.success("Consent recorded. The document has not been sent yet.")
            if decline_col.button(
                "Keep document local",
                key=f"decline-consent-{document.document_id}",
                disabled=provider is None or not declarant.strip(),
            ):
                try:
                    bundle.extraction().record_provider_consent(
                        lineage=lineage,
                        document_id=document.document_id,
                        request_token=supporting_action_token(
                            f"consent:no:{document.document_id}"
                        ),
                        explicit_consent=False,
                        declarant_name=declarant.strip(),
                    )
                except Exception:
                    _safe_error("The local-only choice could not be recorded safely.")
                    continue
                clear_supporting_action_token(f"consent:no:{document.document_id}")
                st.info("The document remains stored locally and was not sent.")
            can_extract = latest is None or latest.status in {
                AttemptStatus.FAILED,
                AttemptStatus.INTERRUPTED,
                AttemptStatus.ABANDONED,
            }
            if can_extract and st.button(
                "Retry candidate extraction" if latest is not None else "Extract candidate evidence",
                type="primary",
                key=f"extract-{document.document_id}",
                disabled=provider is None,
            ):
                operation = f"extract:{document.document_id}:{latest.attempt_id if latest else 'first'}"
                try:
                    result = bundle.extraction().extract(
                        lineage=lineage,
                        document_id=document.document_id,
                        ingestion_attempt_id=ingestion.attempt_id,
                        request_token=supporting_action_token(operation),
                        predecessor_attempt_id=(
                            latest.attempt_id if latest is not None else None
                        ),
                    )
                except SupportingEvidenceInterruptedError as exc:
                    st.session_state[f"pending-extraction-{document.document_id}"] = exc.pending
                    _safe_error(
                        "Extraction was interrupted. Review the status before explicitly abandoning it."
                    )
                    continue
                except SupportingEvidenceServiceError:
                    _safe_error(
                        "Candidate extraction could not complete safely. No unverified output was accepted."
                    )
                    st.rerun()
                except Exception:
                    _safe_error(
                        "External extraction is not configured correctly. No document was transmitted."
                    )
                    continue
                clear_supporting_action_token(operation)
                st.success(
                    f"Extraction complete: {len(result.proposals)} proposal(s) await human review."
                )
                st.rerun()
            pending_key = f"pending-extraction-{document.document_id}"
            pending = st.session_state.get(pending_key)
            if pending is not None:
                confirmed = st.checkbox(
                    "I know this extraction has stopped and should be marked abandoned",
                    key=f"confirm-abandon-extraction-{document.document_id}",
                )
                if st.button(
                    "Mark extraction abandoned",
                    key=f"abandon-extraction-{document.document_id}",
                    disabled=not confirmed,
                ):
                    try:
                        bundle.extraction().abandon(
                            pending,
                            abandonment_token=supporting_action_token(
                                f"abandon-extraction:{pending.attempt_id}"
                            ),
                        )
                    except Exception:
                        _safe_error("The interrupted extraction could not be finalized safely.")
                        continue
                    st.session_state.pop(pending_key, None)
                    st.rerun()
            with st.expander("Extraction history", expanded=False):
                attempts = bundle.repository.extraction_attempts_for_document(
                    formal_lifecycle_id=lineage.formal_lifecycle_id,
                    document_id=document.document_id,
                )
                if not attempts:
                    st.caption("No extraction attempts yet.")
                for attempt in attempts:
                    st.write(
                        f"Attempt {attempt.attempt_number}: {_STATUS_LABELS[attempt.status]}"
                    )
                    st.caption(attempt.started_at.isoformat())


def _review_reference_options(queue, classification: EvidenceClassification):
    return tuple(
        item
        for item in queue.items
        if item.current_revision is not None
        and item.current_revision.approved_classification is classification
        and item.current_revision.action in {ReviewAction.ACCEPT, ReviewAction.CORRECT}
    )


def _reference_label(item) -> str:
    revision = item.current_revision
    claim = revision.approved_claim if revision is not None else item.proposal.proposed_claim
    return f"{item.document.original_filename}: {claim}"


def _render_review(bundle, lifecycle_id: str) -> None:
    st.subheader("3. Review evidence")
    queue = bundle.reviews.get_review_queue(lifecycle_id)
    if not queue.items:
        st.caption("No extracted evidence proposals are awaiting review.")
        return
    st.caption(
        "Fact means directly stated in the document. Inference means a reviewer-supported "
        "interpretation linked to documented facts. Unknown means not established. Conflict "
        "means current evidence disagrees. Rejected items remain in audit history."
    )
    facts = _review_reference_options(queue, EvidenceClassification.DOCUMENTED_FACT)
    referenceable = tuple(
        item
        for item in queue.items
        if item.current_revision is not None
        and item.current_revision.action in {ReviewAction.ACCEPT, ReviewAction.CORRECT}
    )
    actions = (
        "Accept as documented fact",
        "Accept as reasonable inference",
        "Correct",
        "Mark as unknown",
        "Mark as conflicting evidence",
        "Reject",
    )
    for item in queue.items:
        proposal = item.proposal
        with st.expander(
            f"{item.document.original_filename}: {proposal.proposed_claim}",
            expanded=item.review_status is ReviewQueueStatus.UNREVIEWED,
        ):
            st.write(proposal.proposed_claim)
            st.code(proposal.primary_source_span.exact_excerpt, language=None, wrap_lines=True)
            st.caption(proposal.primary_source_span.locator)
            st.caption(f"Suggested category: {proposal.proposed_category.value}")
            st.write(f"Current review state: **{_friendly(item.review_status.value)}**")
            action_label = st.selectbox(
                "Review action", actions, key=f"review-action-{proposal.proposal_id}"
            )
            category = st.selectbox(
                "Evidence category",
                tuple(DocumentCategory),
                index=tuple(DocumentCategory).index(proposal.proposed_category),
                format_func=lambda value: value.value.capitalize(),
                key=f"review-category-{proposal.proposal_id}",
            )
            approved_claim = proposal.proposed_claim
            classification = None
            direct = None
            confidence = None
            fact_ids: tuple[str, ...] = ()
            competing_ids: tuple[str, ...] = ()
            if action_label == "Accept as documented fact":
                action = ReviewAction.ACCEPT
                classification = EvidenceClassification.DOCUMENTED_FACT
                direct = st.checkbox(
                    "I confirm the claim is directly supported by the source excerpt",
                    key=f"direct-{proposal.proposal_id}",
                )
            elif action_label == "Accept as reasonable inference":
                action = ReviewAction.ACCEPT
                classification = EvidenceClassification.REVIEWED_INFERENCE
                direct = False
                confidence = st.slider(
                    "Inference confidence", 0.0, 1.0, 0.5, 0.05,
                    key=f"confidence-{proposal.proposal_id}",
                )
                selected = st.multiselect(
                    "Supporting documented facts",
                    facts,
                    format_func=_reference_label,
                    key=f"facts-{proposal.proposal_id}",
                )
                fact_ids = tuple(entry.current_revision.revision_id for entry in selected)
            elif action_label == "Correct":
                action = ReviewAction.CORRECT
                approved_claim = st.text_area(
                    "Corrected claim", key=f"corrected-{proposal.proposal_id}"
                )
                classification = st.radio(
                    "Classification",
                    (EvidenceClassification.DOCUMENTED_FACT, EvidenceClassification.REVIEWED_INFERENCE),
                    format_func=lambda value: _friendly(value.value),
                    key=f"correct-classification-{proposal.proposal_id}",
                )
                if classification is EvidenceClassification.DOCUMENTED_FACT:
                    direct = st.checkbox(
                        "I confirm the corrected claim is directly supported by the source excerpt",
                        key=f"correct-direct-{proposal.proposal_id}",
                    )
                else:
                    direct = False
                    confidence = st.slider(
                        "Inference confidence", 0.0, 1.0, 0.5, 0.05,
                        key=f"correct-confidence-{proposal.proposal_id}",
                    )
                    selected = st.multiselect(
                        "Supporting documented facts", facts,
                        format_func=_reference_label,
                        key=f"correct-facts-{proposal.proposal_id}",
                    )
                    fact_ids = tuple(entry.current_revision.revision_id for entry in selected)
            elif action_label == "Mark as unknown":
                action = ReviewAction.MARK_UNRESOLVED
                classification = EvidenceClassification.UNKNOWN
                approved_claim = st.text_area(
                    "What remains unknown?",
                    value=proposal.proposed_claim,
                    key=f"unknown-{proposal.proposal_id}",
                )
            elif action_label == "Mark as conflicting evidence":
                action = ReviewAction.MARK_UNRESOLVED
                classification = EvidenceClassification.CONFLICT
                approved_claim = st.text_area(
                    "Describe the conflict",
                    value=proposal.proposed_claim,
                    key=f"conflict-{proposal.proposal_id}",
                )
                choices = tuple(entry for entry in referenceable if entry is not item)
                selected = st.multiselect(
                    "Competing reviewed evidence (choose at least two)", choices,
                    format_func=_reference_label,
                    key=f"competing-{proposal.proposal_id}",
                )
                competing_ids = tuple(entry.current_revision.revision_id for entry in selected)
            else:
                action = ReviewAction.REJECT
                approved_claim = None
                category = None
            rationale = st.text_area("Review rationale", key=f"review-rationale-{proposal.proposal_id}")
            reviewer = _declaration(f"review-{proposal.proposal_id}")
            if st.button(
                "Save review",
                type="primary",
                key=f"save-review-{proposal.proposal_id}",
            ):
                if reviewer is None or not rationale.strip():
                    _safe_error("Complete the reviewer declaration and rationale.")
                    continue
                operation = f"review:{proposal.proposal_id}:{item.current_revision.revision_id if item.current_revision else 'first'}"
                try:
                    bundle.reviews.review_proposal(
                        lifecycle_id,
                        proposal.proposal_id,
                        request_token=supporting_action_token(operation),
                        expected_prior_revision_id=(
                            None if item.current_revision is None else item.current_revision.revision_id
                        ),
                        action=action,
                        reviewer=reviewer,
                        approved_claim=approved_claim,
                        selected_category=category,
                        approved_classification=classification,
                        claim_directly_supported_by_excerpt=direct,
                        inference_confidence=confidence,
                        documented_fact_review_ids=fact_ids,
                        competing_review_ids=competing_ids,
                        rationale=rationale.strip(),
                    )
                except SupportingEvidenceServiceError:
                    _safe_error(
                        "This review is incomplete or no longer current. Check the required fields and references."
                    )
                    continue
                clear_supporting_action_token(operation)
                st.rerun()
    with st.expander("Review history and audit details", expanded=False):
        if not queue.audit_history:
            st.caption("No stale or historical proposals.")
        for item in queue.audit_history:
            st.write(f"{item.document.original_filename}: {item.proposal.proposed_claim}")
            st.caption(_friendly(item.scope.value))


def _target_form(proposal_id: str):
    target_label = st.selectbox(
        "Formal target",
        ("Criterion", "Human accountability required", "Capability signal", "Activity evidence"),
        key=f"target-kind-{proposal_id}",
    )
    value = None
    if target_label == "Criterion":
        criterion = st.selectbox(
            "Criterion", tuple(CriterionName),
            format_func=lambda item: _friendly(item.value),
            key=f"criterion-{proposal_id}",
        )
        value_label = st.selectbox(
            "Value", ("Unknown", "0", "1", "2", "3", "4", "5"),
            key=f"criterion-value-{proposal_id}",
        )
        value = None if value_label == "Unknown" else int(value_label)
        target = {"kind": FormalTargetKind.CRITERION, "criterion": criterion}
    elif target_label == "Human accountability required":
        value_label = st.selectbox(
            "Value", ("Unknown", "Yes", "No"), key=f"accountability-value-{proposal_id}"
        )
        value = None if value_label == "Unknown" else value_label == "Yes"
        target = {"kind": FormalTargetKind.HUMAN_ACCOUNTABILITY_REQUIRED}
    elif target_label == "Capability signal":
        capability = st.selectbox(
            "Capability", tuple(CapabilitySignalName),
            format_func=lambda item: _friendly(item.value),
            key=f"capability-{proposal_id}",
        )
        value_label = st.selectbox(
            "Value", ("Unknown", "Yes", "No"), key=f"capability-value-{proposal_id}"
        )
        value = None if value_label == "Unknown" else value_label == "Yes"
        target = {
            "kind": FormalTargetKind.CAPABILITY_SIGNAL,
            "capability_signal": capability,
        }
    else:
        target = {"kind": FormalTargetKind.ACTIVITY_EVIDENCE}
    return target, value


def _render_mapping(bundle, lifecycle_id: str) -> None:
    st.subheader("4. Map formal inputs")
    review_queue = bundle.reviews.get_review_queue(lifecycle_id)
    if not review_queue.progress.review_complete:
        st.caption("Complete every current evidence review before mapping formal inputs.")
        return
    queue = bundle.formal_inputs.get_mapping_queue(lifecycle_id)
    activities = bundle.repository.approved_activity_catalog(queue.lineage)
    activity_by_name = {name: activity_id for activity_id, name in activities}
    facts = tuple(
        item
        for item in queue.items
        if item.review_revision is not None
        and item.review_revision.approved_classification is EvidenceClassification.DOCUMENTED_FACT
        and item.review_revision.action in {ReviewAction.ACCEPT, ReviewAction.CORRECT}
    )
    eligible = tuple(
        item
        for item in queue.items
        if item.status
        in {MappingQueueStatus.AWAITING_MAPPING, MappingQueueStatus.MAPPED, MappingQueueStatus.CONTEXT_ONLY}
    )
    if not eligible:
        st.caption("No accepted facts or inferences are available for formal mapping.")
    for item in eligible:
        revision = item.review_revision
        assert revision is not None
        proposal_id = item.review_item.proposal.proposal_id
        with st.expander(
            f"{item.review_item.document.original_filename}: {revision.approved_claim}",
            expanded=item.status is MappingQueueStatus.AWAITING_MAPPING,
        ):
            st.write(f"Current state: **{_friendly(item.status.value)}**")
            disposition = st.radio(
                "Use this reviewed item as",
                ("Formal input", "Context only"),
                key=f"mapping-disposition-{proposal_id}",
            )
            activity_name = st.selectbox(
                "Approved process activity",
                tuple(activity_by_name),
                key=f"mapping-activity-{proposal_id}",
            )
            target = value = None
            if disposition == "Formal input":
                target, value = _target_form(proposal_id)
                approved_classification = st.selectbox(
                    "Evidence classification",
                    (revision.approved_classification,),
                    format_func=lambda selected: _friendly(selected.value),
                    key=f"mapping-classification-{proposal_id}",
                )
                approved_knowledge_state = st.selectbox(
                    "Knowledge state",
                    (
                        KnowledgeState.KNOWN
                        if revision.approved_classification is EvidenceClassification.DOCUMENTED_FACT
                        else KnowledgeState.INFERRED,
                    ),
                    format_func=lambda selected: selected.value.capitalize(),
                    key=f"mapping-knowledge-{proposal_id}",
                )
                mapping_confidence = None
                mapping_fact_ids: tuple[str, ...] = ()
                if revision.approved_classification is EvidenceClassification.REVIEWED_INFERENCE:
                    mapping_confidence = st.slider(
                        "Approved inference confidence",
                        0.0,
                        1.0,
                        float(revision.inference_confidence or 0.0),
                        0.05,
                        key=f"mapping-confidence-{proposal_id}",
                    )
                    default_fact_ids = {
                        reference.review_revision_id
                        for reference in revision.inference_documented_facts
                    }
                    selected_facts = st.multiselect(
                        "Supporting documented facts",
                        facts,
                        default=tuple(
                            fact
                            for fact in facts
                            if fact.review_revision is not None
                            and fact.review_revision.revision_id in default_fact_ids
                        ),
                        format_func=lambda fact: (
                            f"{fact.review_item.document.original_filename}: "
                            f"{fact.review_revision.approved_claim}"
                        ),
                        key=f"mapping-facts-{proposal_id}",
                    )
                    mapping_fact_ids = tuple(
                        fact.review_revision.revision_id for fact in selected_facts
                    )
            rationale = st.text_area("Mapping rationale", key=f"mapping-rationale-{proposal_id}")
            reviewer = _declaration(f"mapping-{proposal_id}")
            if st.button("Save mapping choice", type="primary", key=f"save-mapping-{proposal_id}"):
                if reviewer is None or not rationale.strip():
                    _safe_error("Complete the reviewer declaration and mapping rationale.")
                    continue
                operation = f"mapping:{revision.revision_id}:{item.current_mapping.mapping_id if item.current_mapping else 'first'}"
                try:
                    common = dict(
                        formal_lifecycle_id=lifecycle_id,
                        review_revision_id=revision.revision_id,
                        request_token=supporting_action_token(operation),
                        expected_prior_mapping_id=(
                            None if item.current_mapping is None else item.current_mapping.mapping_id
                        ),
                        activity_id=activity_by_name[activity_name],
                        reviewer=reviewer,
                        rationale=rationale.strip(),
                    )
                    if disposition == "Context only":
                        bundle.formal_inputs.mark_reviewed_evidence_context_only(**common)
                    else:
                        bundle.formal_inputs.map_reviewed_evidence(
                            **common,
                            target=target,
                            value=value,
                            knowledge_state=approved_knowledge_state,
                            approved_evidence_classification=approved_classification,
                            inference_confidence=mapping_confidence,
                            supporting_documented_fact_review_ids=mapping_fact_ids,
                        )
                except SupportingEvidenceServiceError:
                    _safe_error(
                        "The mapping does not satisfy the formal-input contract or is no longer current."
                    )
                    continue
                clear_supporting_action_token(operation)
                st.rerun()
    with st.expander("Mapping history and audit details", expanded=False):
        if not queue.audit_history:
            st.caption("No stale or historical mappings.")
        for item in queue.audit_history:
            st.write(item.review_item.proposal.proposed_claim)
            st.caption(_friendly(item.status.value))


def _plain_blocker(blocker: str, document_names: dict[str, str]) -> str:
    code, _, identifier = blocker.partition(":")
    name = document_names.get(identifier, "A supporting item")
    messages = {
        "CANDIDATE_SET_NOT_PREPARED": "Assessment inputs have not been prepared yet.",
        "CANDIDATE_SET_STALE": "Supporting evidence changed after the last preparation.",
        "DOCUMENT_NOT_TERMINALLY_PROCESSED": f"{name} still needs successful extraction or explicit exclusion.",
        "PROPOSAL_UNREVIEWED": "An extracted evidence proposal still needs human review.",
        "REVIEW_AWAITING_MAPPING": "An accepted evidence item still needs a formal mapping or context-only choice.",
        "REVIEW_REFERENCES_STALE": "A reviewed item refers to evidence that is no longer current.",
        "MISSING_DOCUMENT_METADATA": f"{name} is missing current metadata.",
    }
    return messages.get(code, "Supporting evidence is incomplete or no longer current.")


def _render_preparation(bundle, lineage, documents: tuple) -> None:
    st.subheader("5. Prepare assessment inputs")
    st.write(
        "Prepare one immutable snapshot of the current reviewed and mapped evidence, then "
        "calculate whether a formal assessment can be attempted."
    )
    excluded: list[str] = []
    for document in documents:
        if st.checkbox(
            f"Explicitly exclude {document.original_filename} from this preparation",
            key=f"exclude-document-{document.document_id}",
        ):
            excluded.append(document.document_id)
    if excluded:
        confirmed = st.checkbox(
            "I confirm these documents are deliberately excluded and will remain in history",
            key="confirm-document-exclusions",
        )
    else:
        confirmed = True
    state = bundle.formal_inputs.get_current_preparation_state(
        lineage.formal_lifecycle_id
    )
    document_names = {item.document_id: item.original_filename for item in documents}
    prospective_blockers: list[str] = []
    excluded_set = set(excluded)
    for document in documents:
        if document.document_id in excluded_set:
            continue
        extraction = bundle.repository.latest_extraction_attempt(
            formal_lifecycle_id=lineage.formal_lifecycle_id,
            document_id=document.document_id,
        )
        if extraction is None or extraction.status not in {
            AttemptStatus.SUCCEEDED,
            AttemptStatus.PARTIAL,
        }:
            prospective_blockers.append(
                f"DOCUMENT_NOT_TERMINALLY_PROCESSED:{document.document_id}"
            )
    review_queue = bundle.reviews.get_review_queue(lineage.formal_lifecycle_id)
    prospective_blockers.extend(
        "PROPOSAL_UNREVIEWED" for item in review_queue.items
        if item.review_status is ReviewQueueStatus.UNREVIEWED
    )
    mapping_queue = bundle.formal_inputs.get_mapping_queue(
        lineage.formal_lifecycle_id
    )
    prospective_blockers.extend(
        "REVIEW_AWAITING_MAPPING" for item in mapping_queue.items
        if item.status is MappingQueueStatus.AWAITING_MAPPING
    )
    visible_blockers = tuple(dict.fromkeys((*state.blockers, *prospective_blockers)))
    if visible_blockers:
        st.markdown("**Before preparation**")
        for blocker in visible_blockers:
            st.write(f"- {_plain_blocker(blocker, document_names)}")
    readiness = state.latest_readiness if state.candidate_set_current else None
    if readiness is not None and readiness.status is ReadinessStatus.READY_TO_ATTEMPT:
        st.success("Ready to attempt an organisational assessment")
        st.write(
            "This means the formal assessment has enough reviewed input to be attempted. "
            "It does not mean the evidence is sufficient, any gate has passed, the process "
            "is approved, or implementation is authorised."
        )
        if readiness.uncovered_document_categories:
            st.warning(
                "Some evidence categories are not represented: "
                + ", ".join(item.value for item in readiness.uncovered_document_categories)
            )
        return
    if readiness is not None:
        st.warning("More formal inputs are needed")
        for reason in readiness.reasons:
            st.write(f"- {_plain_blocker(reason, document_names)}")
        for category in readiness.uncovered_document_categories:
            st.caption(f"Missing category warning: {category.value}")
        return
    if st.button(
        "Prepare organisational assessment inputs",
        type="primary",
        disabled=not confirmed,
    ):
        candidate_operation = f"prepare:{lineage.formal_lifecycle_id}"
        try:
            if state.current_candidate_set is not None and state.candidate_set_current:
                candidate = state.current_candidate_set
            else:
                result = bundle.formal_inputs.prepare_candidate_set(
                    lineage.formal_lifecycle_id,
                    request_token=supporting_action_token(candidate_operation),
                    explicitly_excluded_document_ids=tuple(excluded),
                )
                candidate = result.candidate_set
            readiness_operation = f"readiness:{candidate.candidate_set_id}"
            bundle.formal_inputs.evaluate_and_persist_readiness(
                lineage.formal_lifecycle_id,
                candidate.candidate_set_id,
                request_token=supporting_action_token(readiness_operation),
            )
        except SupportingEvidenceIncompletePreparationError as exc:
            st.warning("More formal inputs are needed")
            for blocker in exc.blockers:
                st.write(f"- {_plain_blocker(blocker, document_names)}")
            return
        except SupportingEvidenceServiceError:
            _safe_error(
                "Preparation could not complete safely. Review the current evidence state and try again."
            )
            return
        clear_supporting_action_token(candidate_operation)
        clear_supporting_action_token(readiness_operation)
        st.rerun()


def render_supporting_evidence_workflow(formal_lifecycle_id: str) -> None:
    """Render one opt-in workflow for an already-created formal lifecycle."""

    try:
        bundle = supporting_evidence_services()
        lineage = bundle.repository.load_active_lineage(formal_lifecycle_id)
        _progress(bundle, formal_lifecycle_id)
        _render_upload(bundle, lineage)
        documents = _render_documents(bundle, lineage)
        _render_extraction(bundle, lineage, documents)
        _render_review(bundle, formal_lifecycle_id)
        _render_mapping(bundle, formal_lifecycle_id)
        _render_preparation(bundle, lineage, documents)
    except SupportingEvidenceServiceError:
        _safe_error(
            "Supporting-evidence history could not be validated safely. No data was changed."
        )
    except Exception:
        _safe_error(
            "The supporting-evidence workflow is unavailable because its configuration or stored history is invalid."
        )
