"""A fresh, source-backed Phase 2–6 baseline for narrow M2 M1 tests."""

from __future__ import annotations

from pathlib import Path

from ai_adoption_engine.extraction.service import ProcessExtractionService
from ai_adoption_engine.models.enums import CriterionName, KnowledgeState
from ai_adoption_engine.persistence.sqlite import SQLiteAssessmentRepository
from ai_adoption_engine.workspace.models import ExecutionMode
from ai_adoption_engine.workspace.service import AssessmentWorkspaceService
from tests.fakes.extraction_provider import ScriptedExtractionProvider, known, raw_chunk, raw_step, unknown


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures"


def _candidate_chunk():
    """One deterministic extraction response whose pointers target the fixture text."""

    source = (FIXTURE_ROOT / "m2_data_readiness_baseline.txt").read_text(encoding="utf-8")
    block_id = "t-b0001"
    step = raw_step(
        local_step_id="categorise",
        activity="Categorise incoming service requests",
        block_id=block_id,
        snippet="The intake team categorises each incoming service request",
    )
    step.document_order = known(1, block_id=block_id, snippet="The intake team categorises each incoming service request")
    snippets = {
        CriterionName.REPETITION: (4, "work is repeated"),
        CriterionName.PREDICTABILITY: (3, "predictable"),
        CriterionName.AI_CAPABILITY_FIT: (4, "suitable for AI classification"),
        CriterionName.HUMAN_JUDGEMENT_REQUIREMENT: (3, "requires human judgement"),
        CriterionName.BUSINESS_VALUE: (4, "high business value"),
        CriterionName.RISK_CONSEQUENCE: (2, "consequence as low"),
        CriterionName.RESIDUAL_RISK_WITH_HUMAN_OVERSIGHT: (1, "low with human oversight"),
        CriterionName.IMPLEMENTATION_COMPLEXITY: (2, "moderate implementation complexity"),
        CriterionName.CONVENTIONAL_SOLUTION_FIT: (0, "rules-only solution is not sufficient"),
    }
    for characteristic in step.characteristics.criteria:
        if characteristic.name is CriterionName.DATA_READINESS:
            characteristic.assertion = unknown(int)
        else:
            value, snippet = snippets[characteristic.name]
            characteristic.assertion = known(value, block_id=block_id, snippet=snippet)
    step.characteristics.human_accountability_required = known(
        True, block_id=block_id, snippet="retains human accountability"
    )
    for signal in step.characteristics.capability_signals:
        if signal.name.value == "categorises_items":
            signal.assertion = known(
                True, block_id=block_id, snippet="AI classification of request categories"
            )
    return raw_chunk(
        step,
        process_name=known(
            "Synthetic service-request categorisation", block_id=block_id,
            snippet="Synthetic fixture: categorise incoming service requests.",
        ),
    )


def package_ready_m2_baseline(tmp_path):
    """Run the normal synthetic Phase 2–6 workflow with no PORT input."""

    repository = SQLiteAssessmentRepository(tmp_path / "m2-synthetic.db")
    provider = ScriptedExtractionProvider([_candidate_chunk()])

    def extraction_factory(_mode, _document):
        return ProcessExtractionService(provider, run_id_factory=lambda: "m2-synthetic-extraction")

    workspace = AssessmentWorkspaceService(repository, extraction_service_factory=extraction_factory)
    assessment = repository.create_assessment("M2 synthetic data readiness", ExecutionMode.OFFLINE_DEMO)
    source = (FIXTURE_ROOT / "m2_data_readiness_baseline.txt").read_text(encoding="utf-8")
    workspace.ingest_upload(assessment.assessment_id, raw_text=source)
    workspace.extract(assessment.assessment_id)
    review = workspace.start_review(assessment.assessment_id)
    workspace.review_service.accept_assertion(review, review.process_name, "process.name")
    for step in review.steps:
        workspace.review_service.accept_assertion(review, step.activity, f"steps.{step.candidate_step_id}.activity")
        for characteristic in step.criteria:
            path = f"steps.{step.candidate_step_id}.criteria.{characteristic.name.value}"
            if characteristic.assertion.knowledge_state is KnowledgeState.UNKNOWN:
                workspace.review_service.retain_unknown(review, characteristic.assertion, path)
            else:
                workspace.review_service.accept_assertion(review, characteristic.assertion, path)
        workspace.review_service.accept_assertion(
            review, step.human_accountability_required,
            f"steps.{step.candidate_step_id}.human_accountability_required",
        )
        for signal in step.capability_signals:
            if signal.assertion.knowledge_state is KnowledgeState.KNOWN:
                workspace.review_service.accept_assertion(
                    review, signal.assertion,
                    f"steps.{step.candidate_step_id}.capability_signals.{signal.name}",
                )
    workspace.review_service.accept_step_order(review)
    workspace.save_review(assessment.assessment_id, review)
    assert workspace.approve(assessment.assessment_id).approved is not None
    integrated = workspace.assess(assessment.assessment_id)
    package = workspace.generate_package(assessment.assessment_id)
    assert integrated.status == "success" and package.status == "success"
    return repository, assessment.assessment_id
