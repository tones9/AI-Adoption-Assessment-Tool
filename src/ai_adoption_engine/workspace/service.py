"""Phase 7 guarded application orchestration over the approved backend services."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from ai_adoption_engine.application.assessment import IntegratedAssessmentService
from ai_adoption_engine.workspace.models import (
    ArtifactReference,
    ArtifactType,
    ExecutionMode,
    OperationKind,
    OperationStatus,
    WorkflowStage,
)
from ai_adoption_engine.decision_support.service import DecisionSupportPackageService
from ai_adoption_engine.extraction.service import ProcessExtractionService
from ai_adoption_engine.ingestion.pdf import ingest_pdf_bytes
from ai_adoption_engine.ingestion.text import ingest_raw_text, ingest_text_bytes
from ai_adoption_engine.models.decision_support import DecisionPackageSuccess
from ai_adoption_engine.models.document import IngestionResult, IngestionStatus
from ai_adoption_engine.models.extraction import CandidateExtractionResult, ExtractionStatus
from ai_adoption_engine.models.integrated_assessment import IntegratedAssessmentSuccess
from ai_adoption_engine.models.review import (
    ApprovalResult,
    ExplicitApproval,
    ProcessReviewSession,
)
from ai_adoption_engine.persistence.base import AssessmentRepository
from ai_adoption_engine.review.approval import approve_review
from ai_adoption_engine.review.service import ProcessReviewService


class WorkflowGuardError(ValueError):
    """A user action was attempted before its prerequisite boundary."""


class AssessmentWorkspaceService:
    def __init__(
        self,
        repository: AssessmentRepository,
        *,
        extraction_service_factory,
        assessment_service: IntegratedAssessmentService | None = None,
        package_service: DecisionSupportPackageService | None = None,
        review_service: ProcessReviewService | None = None,
    ) -> None:
        self.repository = repository
        self.extraction_service_factory = extraction_service_factory
        self.assessment_service = assessment_service or IntegratedAssessmentService()
        self.package_service = package_service or DecisionSupportPackageService()
        self.review_service = review_service or ProcessReviewService()

    def ingest_upload(
        self,
        assessment_id: str,
        *,
        payload: bytes | None = None,
        filename: str | None = None,
        raw_text: str | None = None,
        replace_existing: bool = False,
        source_label: str | None = None,
    ) -> IngestionResult:
        if (raw_text is None) == (payload is None):
            raise WorkflowGuardError("Provide exactly one uploaded file or pasted text")
        if raw_text is not None:
            result = ingest_raw_text(raw_text)
            source_digest = hashlib.sha256(raw_text.encode()).hexdigest()
        else:
            assert payload is not None and filename is not None
            source_digest = hashlib.sha256(payload).hexdigest()
            suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
            if suffix == "pdf":
                result = ingest_pdf_bytes(payload, filename)
            elif suffix == "txt":
                result = ingest_text_bytes(payload, filename)
            else:
                raise WorkflowGuardError("Only PDF and plain-text files are supported")
        existing_workspace = self.repository.load_workspace(assessment_id)
        existing_ingestion = existing_workspace.active_artifacts.get(
            ArtifactType.INGESTION_RESULT
        )
        if (
            existing_ingestion is not None
            and existing_ingestion.payload.document is not None
            and existing_ingestion.payload.document.source.sha256 != source_digest
            and not replace_existing
        ):
            raise WorkflowGuardError(
                "Replacing the source requires explicit confirmation because the active downstream chain will become non-current."
            )
        operation = self.repository.begin_operation(
            assessment_id, OperationKind.INGEST, source_digest
        )
        if operation.status is OperationStatus.COMPLETED:
            assert operation.produced_artifact_id
            stored = self.repository.load_artifact(operation.produced_artifact_id)
            active = existing_workspace.active_artifacts.get(
                ArtifactType.INGESTION_RESULT
            )
            if active is None or active.artifact_id != stored.artifact_id:
                document = stored.payload.document
                self.repository.activate_artifact_and_advance(
                    assessment_id,
                    stored.artifact_id,
                    stage=(
                        WorkflowStage.INGESTED
                        if document is not None
                        else WorkflowStage.NEW
                    ),
                    deactivate_types=[
                        ArtifactType.CANDIDATE_EXTRACTION_RESULT,
                        ArtifactType.REVIEW_SESSION,
                        ArtifactType.APPROVED_REVIEW,
                        ArtifactType.INTEGRATED_ASSESSMENT_RESULT,
                        ArtifactType.DECISION_PACKAGE_RESULT,
                    ],
                    source_filename=(document.source.original_filename if document else None),
                    source_input_type=(document.source.input_type.value if document else None),
                    document_id=(document.document_id if document else None),
                )
            return stored.payload
        stage = (
            WorkflowStage.INGESTED
            if result.status is not IngestionStatus.FAILED
            else WorkflowStage.NEW
        )
        document = result.document
        try:
            self.repository.save_artifact_and_advance(
                assessment_id,
                ArtifactType.INGESTION_RESULT,
                result,
                artifact_schema_version="phase2-v0.1",
                stage=stage,
                source_filename=(
                    (document.source.original_filename or source_label)
                    if document
                    else (filename or source_label)
                ),
                source_input_type=(document.source.input_type.value if document else None),
                document_id=(document.document_id if document else None),
                operation_id=operation.operation_id,
                deactivate_types=(
                    [
                        ArtifactType.CANDIDATE_EXTRACTION_RESULT,
                        ArtifactType.REVIEW_SESSION,
                        ArtifactType.APPROVED_REVIEW,
                        ArtifactType.INTEGRATED_ASSESSMENT_RESULT,
                        ArtifactType.DECISION_PACKAGE_RESULT,
                    ]
                    if replace_existing
                    else []
                ),
            )
        except Exception:
            self.repository.fail_operation(operation.operation_id, "ingestion-persist-failed")
            raise
        return result

    def extract(self, assessment_id: str) -> CandidateExtractionResult:
        workspace = self.repository.load_workspace(assessment_id)
        ingestion = workspace.active_artifacts.get(ArtifactType.INGESTION_RESULT)
        if ingestion is None or ingestion.payload.document is None:
            raise WorkflowGuardError("Successful document ingestion is required")
        document = ingestion.payload.document
        service: ProcessExtractionService = self.extraction_service_factory(
            workspace.assessment.execution_mode, document
        )
        key = hashlib.sha256(
            f"{document.document_id}:{service.provider.provider_name}:{service.provider.model_name}:{service.schema_version}:{service.prompt_version}".encode()
        ).hexdigest()
        operation = self.repository.begin_operation(
            assessment_id, OperationKind.EXTRACT, key
        )
        if operation.status is OperationStatus.COMPLETED:
            assert operation.produced_artifact_id
            stored = self.repository.load_artifact(operation.produced_artifact_id)
            active = workspace.active_artifacts.get(
                ArtifactType.CANDIDATE_EXTRACTION_RESULT
            )
            if active is None or active.artifact_id != stored.artifact_id:
                if stored.parent_artifact_id != ingestion.artifact_id:
                    raise WorkflowGuardError(
                        "Historical extraction does not belong to the active document revision"
                    )
                self.repository.activate_artifact_and_advance(
                    assessment_id,
                    stored.artifact_id,
                    stage=(
                        WorkflowStage.CANDIDATE_READY
                        if stored.payload.status is not ExtractionStatus.FAILED
                        else WorkflowStage.INGESTED
                    ),
                    deactivate_types=[
                        ArtifactType.REVIEW_SESSION,
                        ArtifactType.APPROVED_REVIEW,
                        ArtifactType.INTEGRATED_ASSESSMENT_RESULT,
                        ArtifactType.DECISION_PACKAGE_RESULT,
                    ],
                )
            return stored.payload
        try:
            result = service.extract(document)
        except Exception:
            self.repository.fail_operation(operation.operation_id, "extraction-failed")
            raise
        stage = (
            WorkflowStage.CANDIDATE_READY
            if result.status is not ExtractionStatus.FAILED
            else WorkflowStage.INGESTED
        )
        try:
            self.repository.save_artifact_and_advance(
                assessment_id,
                ArtifactType.CANDIDATE_EXTRACTION_RESULT,
                result,
                artifact_schema_version="phase3-v0.1",
                stage=stage,
                parent_artifact_id=ingestion.artifact_id,
                operation_id=operation.operation_id,
            )
        except Exception:
            self.repository.fail_operation(operation.operation_id, "extraction-persist-failed")
            raise
        return result

    def start_review(self, assessment_id: str) -> ProcessReviewSession:
        workspace = self.repository.load_workspace(assessment_id)
        candidate = workspace.active_artifacts.get(
            ArtifactType.CANDIDATE_EXTRACTION_RESULT
        )
        if candidate is None:
            raise WorkflowGuardError("Candidate extraction is required")
        existing = workspace.active_artifacts.get(ArtifactType.REVIEW_SESSION)
        if existing is not None:
            return existing.payload
        session = self.review_service.start_review(candidate.payload)
        self.repository.save_artifact_and_advance(
            assessment_id,
            ArtifactType.REVIEW_SESSION,
            session,
            artifact_schema_version="phase4-v0.1",
            stage=WorkflowStage.IN_REVIEW,
            parent_artifact_id=candidate.artifact_id,
        )
        return session

    def save_review(self, assessment_id: str, session: ProcessReviewSession) -> None:
        workspace = self.repository.load_workspace(assessment_id)
        current = workspace.active_artifacts.get(ArtifactType.REVIEW_SESSION)
        if current is None or current.payload.review_id != session.review_id:
            raise WorkflowGuardError("Only the current review session may be saved")
        self.repository.save_artifact_and_advance(
            assessment_id,
            ArtifactType.REVIEW_SESSION,
            session,
            artifact_schema_version=current.artifact_schema_version,
            stage=WorkflowStage.IN_REVIEW,
            parent_artifact_id=current.parent_artifact_id,
            replace_current_review=True,
        )

    def approve(
        self,
        assessment_id: str,
        *,
        rationale: str | None = None,
        approved_at: datetime | None = None,
    ) -> ApprovalResult:
        workspace = self.repository.load_workspace(assessment_id)
        review = workspace.active_artifacts.get(ArtifactType.REVIEW_SESSION)
        if review is None:
            raise WorkflowGuardError("An in-progress review is required")
        if ArtifactType.APPROVED_REVIEW in workspace.active_artifacts:
            raise WorkflowGuardError("The current review is already approved")
        result = approve_review(
            review.payload,
            ExplicitApproval(
                approval_statement="APPROVE CURRENT-STATE PROCESS",
                approved_at=approved_at or datetime.now(UTC),
                rationale=rationale,
            ),
        )
        if result.approved is not None:
            self.repository.save_artifact_and_advance(
                assessment_id,
                ArtifactType.APPROVED_REVIEW,
                result.approved,
                artifact_schema_version="phase4-v0.1",
                stage=WorkflowStage.APPROVED,
                parent_artifact_id=review.artifact_id,
            )
        return result

    def assess(self, assessment_id: str):
        workspace = self.repository.load_workspace(assessment_id)
        approved = workspace.active_artifacts.get(ArtifactType.APPROVED_REVIEW)
        if approved is None:
            raise WorkflowGuardError("Explicitly approved review is required")
        key = hashlib.sha256(approved.artifact_id.encode()).hexdigest()
        operation = self.repository.begin_operation(
            assessment_id, OperationKind.ASSESS, key
        )
        if operation.status is OperationStatus.COMPLETED:
            assert operation.produced_artifact_id
            return self.repository.load_artifact(operation.produced_artifact_id).payload
        result = self.assessment_service.assess(approved.payload)
        try:
            self.repository.save_artifact_and_advance(
                assessment_id,
                ArtifactType.INTEGRATED_ASSESSMENT_RESULT,
                result,
                artifact_schema_version="phase5-v0.1",
                stage=(
                    WorkflowStage.ASSESSED
                    if isinstance(result, IntegratedAssessmentSuccess)
                    else WorkflowStage.APPROVED
                ),
                parent_artifact_id=approved.artifact_id,
                operation_id=operation.operation_id,
            )
        except Exception:
            self.repository.fail_operation(operation.operation_id, "assessment-persist-failed")
            raise
        return result

    def generate_package(self, assessment_id: str):
        workspace = self.repository.load_workspace(assessment_id)
        integrated = workspace.active_artifacts.get(
            ArtifactType.INTEGRATED_ASSESSMENT_RESULT
        )
        if integrated is None or not isinstance(
            integrated.payload, IntegratedAssessmentSuccess
        ):
            raise WorkflowGuardError("A successful integrated assessment is required")
        key = hashlib.sha256(integrated.artifact_id.encode()).hexdigest()
        operation = self.repository.begin_operation(
            assessment_id, OperationKind.GENERATE_PACKAGE, key
        )
        if operation.status is OperationStatus.COMPLETED:
            assert operation.produced_artifact_id
            return self.repository.load_artifact(operation.produced_artifact_id).payload
        result = self.package_service.generate(integrated.payload)
        try:
            self.repository.save_artifact_and_advance(
                assessment_id,
                ArtifactType.DECISION_PACKAGE_RESULT,
                result,
                artifact_schema_version="phase6-v0.1",
                stage=(
                    WorkflowStage.PACKAGE_READY
                    if isinstance(result, DecisionPackageSuccess)
                    else WorkflowStage.ASSESSED
                ),
                parent_artifact_id=integrated.artifact_id,
                operation_id=operation.operation_id,
            )
        except Exception:
            self.repository.fail_operation(operation.operation_id, "package-persist-failed")
            raise
        return result

    def reset_to_review(self, assessment_id: str) -> None:
        workspace = self.repository.load_workspace(assessment_id)
        if ArtifactType.REVIEW_SESSION not in workspace.active_artifacts:
            raise WorkflowGuardError("No review session is available to reopen")
        self.repository.invalidate_active_artifacts(
            assessment_id,
            [
                ArtifactType.APPROVED_REVIEW,
                ArtifactType.INTEGRATED_ASSESSMENT_RESULT,
                ArtifactType.DECISION_PACKAGE_RESULT,
            ],
            stage=WorkflowStage.IN_REVIEW,
        )
