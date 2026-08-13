from ai_adoption_engine.application.assessment import IntegratedAssessmentService
from ai_adoption_engine.extraction.service import ProcessExtractionService
from ai_adoption_engine.extraction.providers.openai import OpenAIExtractionProvider
from ai_adoption_engine.ingestion.text import ingest_raw_text
from ai_adoption_engine.models.enums import CriterionName, KnowledgeState, RecommendationMode
from ai_adoption_engine.models.extraction import (
    RawCandidateOrdinalAssertion,
    RawEvidencePointer,
)
from ai_adoption_engine.models.integrated_assessment import IntegratedAssessmentSuccess
from ai_adoption_engine.models.review import (
    ExplicitApproval,
    InformationOrigin,
)
from ai_adoption_engine.review.approval import approve_review
from tests.fakes.extraction_provider import (
    ScriptedExtractionProvider,
    known,
    raw_chunk,
    raw_step,
)
from tests.fakes.review import FIXED_TIME, review_service


def test_complete_offline_pipeline_preserves_assessment_traceability(
    monkeypatch,
) -> None:
    def fail_if_openai_called(*args, **kwargs):
        raise AssertionError("The offline Phase 5 pipeline called OpenAI")

    monkeypatch.setattr(OpenAIExtractionProvider, "extract_chunk", fail_if_openai_called)
    ingestion = ingest_raw_text(
        "Complaint handling\n\n"
        "Agent records the complaint in the case system.\n\n"
        "Manager reviews the complaint."
    )
    assert ingestion.document is not None
    first_step = raw_step(
        local_step_id="record",
        activity="Record complaint",
        block_id="t-b0002",
        snippet="Agent records the complaint in the case system.",
    )
    data_readiness = next(
        item
        for item in first_step.characteristics.criteria
        if item.name is CriterionName.DATA_READINESS
    )
    data_readiness.assertion = RawCandidateOrdinalAssertion(
        value=2,
        knowledge_state=KnowledgeState.INFERRED,
        rationale="The named case system suggests some structured operational data.",
        evidence=[
            RawEvidencePointer(
                block_id="t-b0002",
                exact_snippet="case system",
                occurrence=None,
                slice_id=None,
            )
        ],
        confidence=0.7,
    )
    provider = ScriptedExtractionProvider(
        [
            raw_chunk(
                first_step,
                raw_step(
                    local_step_id="review",
                    activity="Review complaint",
                    block_id="t-b0003",
                    snippet="Manager reviews the complaint.",
                ),
                process_name=known(
                    "Complaint handling",
                    block_id="t-b0001",
                    snippet="Complaint handling",
                ),
            )
        ]
    )
    extraction = ProcessExtractionService(
        provider, run_id_factory=lambda: "phase5-offline-extraction"
    ).extract(ingestion.document)
    assert extraction.candidate is not None

    reviewer = review_service()
    review = reviewer.start_review(extraction)
    reviewer.accept_assertion(review, review.process_name, "process.name")
    for step in review.steps:
        reviewer.accept_assertion(
            review, step.activity, f"steps.{step.candidate_step_id}.activity"
        )
    first_reviewed = review.steps[0]
    repetition = next(
        item.assertion
        for item in first_reviewed.criteria
        if item.name is CriterionName.REPETITION
    )
    reviewer.resolve_unknown(
        review,
        repetition,
        f"steps.{first_reviewed.candidate_step_id}.criteria.repetition",
        3,
        rationale="The process owner confirmed that this activity recurs daily.",
    )
    inferred_data = next(
        item.assertion
        for item in first_reviewed.criteria
        if item.name is CriterionName.DATA_READINESS
    )
    reviewer.accept_assertion(
        review,
        inferred_data,
        f"steps.{first_reviewed.candidate_step_id}.criteria.data_readiness",
    )
    reviewer.accept_step_order(review)
    approval = approve_review(
        review,
        ExplicitApproval(
            approval_statement="APPROVE CURRENT-STATE PROCESS",
            approved_at=FIXED_TIME,
            rationale="Synthetic current-state process confirmed.",
        ),
    )
    assert approval.approved is not None

    integrated = IntegratedAssessmentService(
        clock=lambda: FIXED_TIME,
        run_id_factory=lambda: "phase5-offline-assessment",
    ).assess(approval.approved)
    assert isinstance(integrated, IntegratedAssessmentSuccess)
    assert integrated.lineage.source_document_id == ingestion.document.document_id
    assert integrated.lineage.extraction_run_id == "phase5-offline-extraction"
    assert integrated.lineage.review_id == review.review_id
    assert len(integrated.process_assessment.step_assessments) == 2
    assert all(
        item.recommendation_mode is RecommendationMode.INVESTIGATE_FURTHER
        for item in integrated.process_assessment.step_assessments
    )

    first_trace = integrated.step_traceability[0]
    assert len(first_trace.criteria) == 10
    assert len(first_trace.capability_signals) == 10
    assert first_trace.activity.origin is InformationOrigin.DOCUMENT_SUPPORTED
    assert first_trace.activity.evidence[0].document_id == ingestion.document.document_id
    assert first_trace.activity.evidence[0].block_id == "t-b0002"
    assert first_trace.activity.evidence[0].source_locator == "line 3"
    repetition_trace = next(
        item for item in first_trace.criteria if "repetition]" in item.review_field_path
    )
    assert repetition_trace.origin is InformationOrigin.HUMAN_SUPPLIED
    assert repetition_trace.evidence == []
    inferred_trace = next(
        item
        for item in first_trace.criteria
        if "data_readiness]" in item.review_field_path
    )
    assert inferred_trace.origin is InformationOrigin.MODEL_INFERRED
    assert inferred_trace.evidence[0].block_id == "t-b0002"
    assessed_data = next(
        item
        for item in integrated.process_assessment.step_assessments[0].criteria
        if item.criterion is CriterionName.DATA_READINESS
    )
    assert assessed_data.knowledge_state is KnowledgeState.INFERRED
    assert assessed_data.confidence == 0.7
