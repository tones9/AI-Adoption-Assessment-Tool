from pathlib import Path

from ai_adoption_engine.workspace.composition import extraction_service_for
from ai_adoption_engine.workspace.demo_extraction import demo_text
from ai_adoption_engine.workspace.service import AssessmentWorkspaceService
from ai_adoption_engine.workspace.models import ArtifactType, ExecutionMode
from ai_adoption_engine.persistence.sqlite import SQLiteAssessmentRepository
from ai_adoption_engine.application.assessment import IntegratedAssessmentService
from ai_adoption_engine.decision_support import DecisionSupportPackageService


def test_complete_offline_workspace_save_and_reopen(tmp_path: Path, monkeypatch) -> None:
    from ai_adoption_engine.extraction.providers.openai import OpenAIExtractionProvider

    monkeypatch.setattr(
        OpenAIExtractionProvider,
        "extract_chunk",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("OpenAI called")),
    )
    path = tmp_path / "workspace.db"
    repository = SQLiteAssessmentRepository(path)
    service = AssessmentWorkspaceService(
        repository, extraction_service_factory=extraction_service_for
    )
    assessment = repository.create_assessment("End-to-end demo", ExecutionMode.OFFLINE_DEMO)
    ingestion = service.ingest_upload(assessment.assessment_id, raw_text=demo_text())
    candidate = service.extract(assessment.assessment_id)
    session = service.start_review(assessment.assessment_id)
    service.review_service.accept_assertion(session, session.process_name, "process.name")
    service.review_service.correct_assertion(
        session,
        session.process_objective,
        "process.objective",
        "Handle complaints fairly and communicate the outcome.",
        rationale="Reviewer supplied a concise objective.",
    )
    for step in session.steps:
        service.review_service.accept_assertion(
            session, step.activity, f"steps.{step.candidate_step_id}.activity"
        )
    service.review_service.retain_unknown(
        session,
        session.steps[0].criteria[0].assertion,
        f"steps.{session.steps[0].candidate_step_id}.criteria[0]",
    )
    service.review_service.accept_step_order(session)
    service.save_review(assessment.assessment_id, session)
    approval = service.approve(assessment.assessment_id)
    assert approval.approved is not None
    integrated = service.assess(assessment.assessment_id)
    package = service.generate_package(assessment.assessment_id)
    assert ingestion.document is not None
    assert candidate.candidate is not None
    assert integrated.status == "success"
    assert package.status == "success"
    assert all(item.recommendation_mode.value == "INVESTIGATE_FURTHER" for item in package.package.portfolio.items)
    first_evidence = candidate.candidate.steps[0].activity.evidence[0]
    assert first_evidence.exact_snippet in ingestion.document.canonical_text
    assert approval.approved.review.process_objective.origin.value == "HUMAN_SUPPLIED"
    assert approval.approved.review.process_objective.evidence == []

    reopened = SQLiteAssessmentRepository(path).load_workspace(assessment.assessment_id)
    assert reopened.active_artifacts[ArtifactType.APPROVED_REVIEW].payload == approval.approved
    assert reopened.active_artifacts[ArtifactType.INTEGRATED_ASSESSMENT_RESULT].payload == integrated
    assert reopened.active_artifacts[ArtifactType.DECISION_PACKAGE_RESULT].payload == package


def test_repeated_explicit_extract_does_not_rerun_provider(tmp_path: Path) -> None:
    calls: list[str] = []

    def factory(mode, document):
        service = extraction_service_for(mode, document)
        original = service.provider.extract_chunk

        def counted(request):
            calls.append(request.chunk.chunk_id)
            return original(request)

        service.provider.extract_chunk = counted
        return service

    repository = SQLiteAssessmentRepository(tmp_path / "idempotent.db")
    service = AssessmentWorkspaceService(repository, extraction_service_factory=factory)
    assessment = repository.create_assessment("Idempotent", ExecutionMode.OFFLINE_DEMO)
    service.ingest_upload(assessment.assessment_id, raw_text=demo_text())
    first = service.extract(assessment.assessment_id)
    second = service.extract(assessment.assessment_id)
    assert first == second
    assert len(calls) == 1


def test_repeated_assessment_and_package_actions_reuse_completed_artifacts(tmp_path: Path) -> None:
    assessment_calls: list[str] = []
    package_calls: list[str] = []

    class CountingAssessmentService:
        def assess(self, approved):
            assessment_calls.append(approved.review.review_id)
            return IntegratedAssessmentService().assess(approved)

    class CountingPackageService:
        def generate(self, integrated):
            package_calls.append(integrated.metadata.assessment_run_id)
            return DecisionSupportPackageService().generate(integrated)

    repository = SQLiteAssessmentRepository(tmp_path / "reruns.db")
    service = AssessmentWorkspaceService(
        repository,
        extraction_service_factory=extraction_service_for,
        assessment_service=CountingAssessmentService(),
        package_service=CountingPackageService(),
    )
    assessment = repository.create_assessment("No reruns", ExecutionMode.OFFLINE_DEMO)
    service.ingest_upload(assessment.assessment_id, raw_text=demo_text())
    service.extract(assessment.assessment_id)
    session = service.start_review(assessment.assessment_id)
    service.review_service.accept_assertion(session, session.process_name, "process.name")
    for step in session.steps:
        service.review_service.accept_assertion(
            session, step.activity, f"steps.{step.candidate_step_id}.activity"
        )
    service.review_service.accept_step_order(session)
    service.save_review(assessment.assessment_id, session)
    assert service.approve(assessment.assessment_id).approved is not None
    assert service.assess(assessment.assessment_id) == service.assess(assessment.assessment_id)
    assert service.generate_package(assessment.assessment_id) == service.generate_package(
        assessment.assessment_id
    )
    assert len(assessment_calls) == 1
    assert len(package_calls) == 1
