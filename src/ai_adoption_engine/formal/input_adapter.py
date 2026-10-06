"""Deterministic, persistence-free D-037 formal four-gate input adapter."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, TypeAdapter, ValidationError

from ai_adoption_engine.application.fingerprints import fingerprint_business_process
from ai_adoption_engine.models.enums import CriterionName, KnowledgeState, UncertaintyStatus
from ai_adoption_engine.models.evidence import (
    BooleanCriterionInput,
    CriterionInput,
    EvidenceReference,
)
from ai_adoption_engine.models.formal_assessment import (
    FORMAL_ASSESSMENT_INPUT_PROJECTION_SCHEMA,
    FORMAL_ASSESSMENT_RUN_STORE_ID,
    FORMAL_GUIDANCE_CATALOGUE_FINGERPRINT,
    FORMAL_GUIDANCE_CATALOGUE_ID,
    FORMAL_INPUT_ADAPTER_ID,
    FORMAL_INPUT_ADAPTER_RULES_FINGERPRINT,
    FORMAL_INPUT_ADAPTER_RULES_ID,
    FORMAL_INPUT_ADAPTER_VERSION,
    FOUR_GATE_POLICY_FINGERPRINT,
    CompetingFormalValue,
    FormalAssessmentActivityProjection,
    FormalAssessmentAuthorization,
    FormalAssessmentCompatibilityIdentity,
    FormalAssessmentInputMode,
    FormalAssessmentInputProjection,
    FormalEvidenceReferencePin,
    FormalFieldResolutionTrace,
    FormalInputConflictResolution,
    FormalMappingReferencePin,
    FormalValueOrigin,
    ProjectedValueOrigin,
)
from ai_adoption_engine.models.formal_assessment_adapter import (
    FORMAL_FOUR_GATE_INPUT_ADAPTER_RULES,
    FormalFourGateInputAdapterRules,
    FormalInputAdapterError,
    FormalInputAdapterFailure,
    FormalInputAdapterFailureCode,
    FormalInputAdapterResult,
    FormalInputAdapterSuccess,
)
from ai_adoption_engine.models.formal_evidence import (
    EvidenceClassification,
    FormalEvidenceReadiness,
    FormalInputCandidateSet,
    FormalInputMapping,
    FormalTarget,
    FormalTargetKind,
    MappingDisposition,
    ReadinessStatus,
    ReviewAction as SupportingReviewAction,
    SupportingEvidenceReviewRevision,
)
from ai_adoption_engine.models.four_gate_assessment import CapabilitySignalName
from ai_adoption_engine.models.process import (
    BusinessProcess,
    CapabilitySignalInput,
    ProcessStep,
)
from ai_adoption_engine.models.review import (
    ApprovedProcessReview,
    ConflictStatus,
    ReviewAction,
    ReviewStatus,
)
from ai_adoption_engine.review.approval import _project_business_process


_APPROVED_REVIEW_ADAPTER = TypeAdapter(ApprovedProcessReview)


def _canonical_json_bytes(value: Any) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _approved_review_payload_sha256(value: ApprovedProcessReview) -> str:
    """Match the exact phase4-v0.1 bytes pinned by the persisted lifecycle."""

    encoded = _APPROVED_REVIEW_ADAPTER.dump_json(
        value,
        by_alias=True,
        exclude_none=False,
    )
    return hashlib.sha256(encoded).hexdigest()


def _target_key(target: FormalTarget) -> tuple[str, str]:
    if target.kind is FormalTargetKind.CRITERION:
        return target.kind.value, target.criterion.value
    if target.kind is FormalTargetKind.CAPABILITY_SIGNAL:
        return target.kind.value, target.capability_signal.value
    return target.kind.value, ""


def _target_path(prefix: str, activity_id: str, target: FormalTarget) -> str:
    base = f"{prefix}.steps[step_id={activity_id}].characteristics"
    if target.kind is FormalTargetKind.CRITERION:
        return f"{base}.{target.criterion.value}"
    if target.kind is FormalTargetKind.HUMAN_ACCOUNTABILITY_REQUIRED:
        return f"{base}.human_accountability_required"
    return f"{base}.capability_signals.{target.capability_signal.value}"


def _scalar_targets() -> tuple[FormalTarget, ...]:
    from ai_adoption_engine.models.formal_evidence import (
        CapabilitySignalFormalTarget,
        CriterionFormalTarget,
        HumanAccountabilityFormalTarget,
    )

    return (
        *(
            CriterionFormalTarget(
                kind=FormalTargetKind.CRITERION,
                criterion=name,
            )
            for name in CriterionName
        ),
        HumanAccountabilityFormalTarget(
            kind=FormalTargetKind.HUMAN_ACCOUNTABILITY_REQUIRED
        ),
        *(
            CapabilitySignalFormalTarget(
                kind=FormalTargetKind.CAPABILITY_SIGNAL,
                capability_signal=name,
            )
            for name in CapabilitySignalName
        ),
    )


def _input_for_target(step: ProcessStep, target: FormalTarget):
    if target.kind is FormalTargetKind.CRITERION:
        return step.characteristics.criterion(target.criterion)
    if target.kind is FormalTargetKind.HUMAN_ACCOUNTABILITY_REQUIRED:
        return step.characteristics.human_accountability_required
    return getattr(step.characteristics.capability_signals, target.capability_signal.value)


def _set_input(step: ProcessStep, target: FormalTarget, value: Any) -> None:
    if target.kind is FormalTargetKind.CRITERION:
        setattr(step.characteristics, target.criterion.value, value)
    elif target.kind is FormalTargetKind.HUMAN_ACCOUNTABILITY_REQUIRED:
        step.characteristics.human_accountability_required = value
    else:
        setattr(
            step.characteristics.capability_signals,
            target.capability_signal.value,
            value,
        )


def _mapping_pin(mapping: FormalInputMapping) -> FormalMappingReferencePin:
    return FormalMappingReferencePin(
        mapping_id=mapping.mapping_id,
        mapping_payload_sha256=_sha256(mapping),
    )


def _evidence_pin(evidence: EvidenceReference) -> FormalEvidenceReferencePin:
    return FormalEvidenceReferencePin(
        evidence_id=evidence.evidence_id,
        evidence_payload_sha256=_sha256(evidence),
    )


@dataclass(frozen=True)
class _AdapterProblem(Exception):
    code: FormalInputAdapterFailureCode
    message: str
    field_path: str | None = None
    activity_id: str | None = None


@dataclass(frozen=True)
class _EffectiveGroup:
    value: int | bool
    knowledge_state: KnowledgeState
    confidence: float | None
    mappings: tuple[FormalInputMapping, ...]
    evidence: tuple[EvidenceReference, ...]

    @property
    def key(self) -> tuple[str, int | bool, KnowledgeState, float | None]:
        return (
            type(self.value).__name__,
            self.value,
            self.knowledge_state,
            self.confidence,
        )

    @property
    def mapping_pins(self) -> tuple[FormalMappingReferencePin, ...]:
        return tuple(_mapping_pin(item) for item in self.mappings)

    @property
    def evidence_pins(self) -> tuple[FormalEvidenceReferencePin, ...]:
        return tuple(_evidence_pin(item) for item in self.evidence)


@dataclass(frozen=True)
class FormalInputConflictPreflight:
    """Read-only conflict alternatives for one fully pinned supporting attempt.

    This is deliberately a narrow public view of the adapter's existing grouping
    and alternative construction.  It does not create a projection, mutate an
    authorization, or select a value; the UI uses it only to collect the frozen
    human resolutions that :meth:`project` later verifies exactly.
    """

    conflicts: tuple[tuple[CompetingFormalValue, ...], ...]


def _canonical_compatibility() -> FormalAssessmentCompatibilityIdentity:
    return FormalAssessmentCompatibilityIdentity(
        adapter_id=FORMAL_INPUT_ADAPTER_ID,
        adapter_version=FORMAL_INPUT_ADAPTER_VERSION,
        adapter_rules_id=FORMAL_INPUT_ADAPTER_RULES_ID,
        adapter_rules_fingerprint=FORMAL_INPUT_ADAPTER_RULES_FINGERPRINT,
        engine_input_contract="phase1-v0.4",
        framework_id="four-gate-framework.v0.1",
        framework_version="0.1",
        policy_id="decision_policy.v0.3",
        policy_version="0.3.0",
        policy_fingerprint=FOUR_GATE_POLICY_FINGERPRINT,
        engine_id="four-gate-assessment-engine.v0.1",
        engine_version="0.1.0",
        formal_evidence_contract="preliminary-formal-evidence.v0.1",
        candidate_contract="formal-input-candidate-set.v0.1",
        readiness_contract="formal-evidence-readiness.v0.1",
        output_contract="phase1-v0.4",
        guidance_catalogue_id=FORMAL_GUIDANCE_CATALOGUE_ID,
        guidance_catalogue_fingerprint=FORMAL_GUIDANCE_CATALOGUE_FINGERPRINT,
    )


def formal_assessment_compatibility_identity() -> FormalAssessmentCompatibilityIdentity:
    """Return the one frozen adapter/engine/policy compatibility identity.

    Product composition uses this public value when it mechanically constructs a
    run authorization; it never recreates or relaxes the pinned identity.
    """

    return _canonical_compatibility()


class FormalFourGateInputAdapter:
    """Create one complete formal engine projection without external state."""

    def __init__(self, rules: object = FORMAL_FOUR_GATE_INPUT_ADAPTER_RULES) -> None:
        self.rules = rules

    def project(
        self,
        *,
        authorization: object,
        approved_review: object,
        candidate_set: object | None = None,
        readiness: object | None = None,
        supporting_reviews: tuple[object, ...] = (),
    ) -> FormalInputAdapterResult:
        try:
            rules = self._validated_rules()
            validated_authorization = self._validated_authorization(authorization)
            approved = self._validated_approved_review(
                validated_authorization,
                approved_review,
            )
            candidate, ready, reviews = self._validated_mode_inputs(
                validated_authorization,
                candidate_set,
                readiness,
                supporting_reviews,
            )
            projection = self._build_projection(
                validated_authorization,
                approved,
                candidate,
                ready,
                reviews,
            )
            return FormalInputAdapterSuccess(rules=rules, projection=projection)
        except _AdapterProblem as exc:
            return self._failure(
                exc.code,
                exc.message,
                exc.field_path,
                exc.activity_id,
            )
        except (AttributeError, KeyError, TypeError, ValueError, ValidationError) as exc:
            return self._failure(
                FormalInputAdapterFailureCode.PROJECTION_VALIDATION_FAILED,
                f"The formal input projection could not be validated: {exc}",
                "projection",
            )

    def preflight_conflicts(
        self,
        *,
        authorization: object,
        approved_review: object,
        candidate_set: object,
        readiness: object,
        supporting_reviews: tuple[object, ...],
    ) -> FormalInputConflictPreflight | FormalInputAdapterFailure:
        """Return every exact unresolved conflict without projecting or running.

        The same validation, effective-value grouping, and alternative builder
        used by ``project`` are kept authoritative.  A process-only attempt has
        no supporting mappings and therefore has no conflict preflight surface.
        """

        try:
            rules = self._validated_rules()
            authorization_value = self._validated_authorization(authorization)
            approved = self._validated_approved_review(
                authorization_value, approved_review
            )
            candidate, ready, reviews = self._validated_mode_inputs(
                authorization_value,
                candidate_set,
                readiness,
                supporting_reviews,
            )
            if candidate is None:
                return FormalInputConflictPreflight(conflicts=())
            conflicts: list[tuple[CompetingFormalValue, ...]] = []
            self._build_projection(
                authorization_value,
                approved,
                candidate,
                ready,
                reviews,
                conflict_sink=conflicts,
            )
            del rules  # validation is intentional; it is not an alternate rule path.
            return FormalInputConflictPreflight(conflicts=tuple(conflicts))
        except _AdapterProblem as exc:
            return self._failure(
                exc.code, exc.message, exc.field_path, exc.activity_id
            )
        except (AttributeError, KeyError, TypeError, ValueError, ValidationError) as exc:
            return self._failure(
                FormalInputAdapterFailureCode.PROJECTION_VALIDATION_FAILED,
                f"The formal conflict preflight could not be validated: {exc}",
                "preflight",
            )

    def _failure(
        self,
        code: FormalInputAdapterFailureCode,
        message: str,
        field_path: str | None = None,
        activity_id: str | None = None,
    ) -> FormalInputAdapterFailure:
        rules = (
            self.rules
            if isinstance(self.rules, FormalFourGateInputAdapterRules)
            and self.rules == FORMAL_FOUR_GATE_INPUT_ADAPTER_RULES
            else None
        )
        return FormalInputAdapterFailure(
            rules=rules,
            errors=(
                FormalInputAdapterError(
                    code=code,
                    message=message,
                    field_path=field_path,
                    activity_id=activity_id,
                ),
            ),
        )

    def _validated_rules(self) -> FormalFourGateInputAdapterRules:
        try:
            payload = (
                self.rules.model_dump(mode="json")
                if isinstance(self.rules, BaseModel)
                else self.rules
            )
            rules = FormalFourGateInputAdapterRules.model_validate(payload)
        except (TypeError, ValueError, ValidationError) as exc:
            raise _AdapterProblem(
                FormalInputAdapterFailureCode.INCOMPATIBLE_IDENTITY_OR_RULES,
                "The supplied formal input adapter rules are invalid.",
                "rules",
            ) from exc
        if rules != FORMAL_FOUR_GATE_INPUT_ADAPTER_RULES:
            raise _AdapterProblem(
                FormalInputAdapterFailureCode.INCOMPATIBLE_IDENTITY_OR_RULES,
                "The supplied formal input adapter rules drift from the frozen artifact.",
                "rules",
            )
        return rules

    def _validated_authorization(self, value: object) -> FormalAssessmentAuthorization:
        if (
            isinstance(value, FormalAssessmentAuthorization)
            and value.compatibility != _canonical_compatibility()
        ):
            raise _AdapterProblem(
                FormalInputAdapterFailureCode.INCOMPATIBLE_IDENTITY_OR_RULES,
                "Authorization compatibility identities drift from the frozen contract.",
                "authorization.compatibility",
            )
        if isinstance(value, FormalAssessmentAuthorization):
            try:
                for resolution in value.conflict_resolutions:
                    if not isinstance(resolution, FormalInputConflictResolution):
                        raise TypeError("conflict resolution type")
                    FormalInputConflictResolution.model_validate(
                        resolution.model_dump(mode="json")
                    )
                    if (
                        resolution.lineage != value.approved_process.lineage
                        or resolution.run_lineage != value.run_lineage
                    ):
                        raise ValueError("conflict resolution lineage")
            except (TypeError, ValueError, ValidationError) as exc:
                raise _AdapterProblem(
                    FormalInputAdapterFailureCode.INVALID_CONFLICT_RESOLUTION,
                    "An authorization conflict resolution is malformed or cross-lineage.",
                    "authorization.conflict_resolutions",
                ) from exc
        try:
            if not isinstance(value, FormalAssessmentAuthorization):
                raise TypeError("authorization type")
            authorization = FormalAssessmentAuthorization.model_validate(
                value.model_dump(mode="json")
            )
        except (TypeError, ValueError, ValidationError) as exc:
            raise _AdapterProblem(
                FormalInputAdapterFailureCode.INVALID_AUTHORIZATION,
                "The formal assessment authorization is malformed or inconsistent.",
                "authorization",
            ) from exc
        return authorization

    def _validated_approved_review(
        self,
        authorization: FormalAssessmentAuthorization,
        value: object,
    ) -> ApprovedProcessReview:
        try:
            if not isinstance(value, ApprovedProcessReview):
                raise TypeError("approved review type")
            approved = ApprovedProcessReview.model_validate(value.model_dump(mode="json"))
        except (TypeError, ValueError, ValidationError) as exc:
            raise _AdapterProblem(
                FormalInputAdapterFailureCode.INVALID_APPROVED_REVIEW,
                "The adapter requires one valid ApprovedProcessReview.",
                "approved_review",
            ) from exc

        review = approved.review
        if review.status.value != ReviewStatus.APPROVED.value or not review.order_accepted:
            raise _AdapterProblem(
                FormalInputAdapterFailureCode.INVALID_APPROVED_REVIEW,
                "The review must be approved with accepted activity order.",
                "approved_review.review",
            )
        if any(
            item.blocking and item.status.value == ConflictStatus.OPEN.value
            for item in review.conflicts
        ):
            raise _AdapterProblem(
                FormalInputAdapterFailureCode.INVALID_APPROVED_REVIEW,
                "The approved review contains an unresolved blocking conflict.",
                "approved_review.review.conflicts",
            )
        approval_events = [
            item for item in review.events if item.action.value == ReviewAction.APPROVE.value
        ]
        if len(approval_events) != 1:
            raise _AdapterProblem(
                FormalInputAdapterFailureCode.INVALID_APPROVED_REVIEW,
                "The approved review must contain exactly one approval event.",
                "approved_review.review.events",
            )
        event = approval_events[0]
        if event.occurred_at != approved.approval.approved_at:
            raise _AdapterProblem(
                FormalInputAdapterFailureCode.INVALID_APPROVED_REVIEW,
                "The approval event timestamp does not match explicit approval.",
                "approved_review.approval.approved_at",
            )
        try:
            derived_process = _project_business_process(review)
        except (TypeError, ValueError, ValidationError) as exc:
            raise _AdapterProblem(
                FormalInputAdapterFailureCode.INVALID_APPROVED_REVIEW,
                "The approved review cannot reproduce its process projection.",
                "approved_review.business_process",
            ) from exc
        if derived_process != approved.business_process:
            raise _AdapterProblem(
                FormalInputAdapterFailureCode.INVALID_APPROVED_REVIEW,
                "The approved BusinessProcess is not the exact review projection.",
                "approved_review.business_process",
            )

        pin = authorization.approved_process
        lineage = pin.lineage
        candidate = review.original_candidate
        source_document_id = candidate.source_document_id
        source_document_sha256 = source_document_id.removeprefix("doc-")
        if (
            lineage.formal_lifecycle_id
            != authorization.run_lineage.formal_lifecycle_id
            or lineage.approved_review_payload_sha256
            != _approved_review_payload_sha256(approved)
            or lineage.source_document_id != source_document_id
            or lineage.source_document_sha256 != source_document_sha256
            or pin.source_extraction_run_id != candidate.extraction_run_id
            or pin.approval_event_id != event.event_id
            or pin.approved_at != approved.approval.approved_at
            or lineage.validated_process_id != approved.business_process.process_id
            or lineage.validated_process_fingerprint
            != fingerprint_business_process(approved.business_process)
        ):
            raise _AdapterProblem(
                FormalInputAdapterFailureCode.INVALID_APPROVED_LINEAGE,
                "Authorization pins do not match the immutable approved review.",
                "authorization.approved_process",
            )
        if any(
            item.source_id != lineage.source_document_id
            for item in approved.business_process.evidence
        ):
            raise _AdapterProblem(
                FormalInputAdapterFailureCode.INVALID_APPROVED_LINEAGE,
                "Approved-process evidence is outside the pinned source document.",
                "approved_review.business_process.evidence",
            )
        return approved

    def _validated_mode_inputs(
        self,
        authorization: FormalAssessmentAuthorization,
        candidate_value: object | None,
        readiness_value: object | None,
        review_values: tuple[object, ...],
    ) -> tuple[
        FormalInputCandidateSet | None,
        FormalEvidenceReadiness | None,
        dict[str, SupportingEvidenceReviewRevision],
    ]:
        mode = authorization.input_choice.mode
        if mode is FormalAssessmentInputMode.APPROVED_PROCESS_ONLY:
            if candidate_value is not None or readiness_value is not None or review_values:
                raise _AdapterProblem(
                    FormalInputAdapterFailureCode.MODE_INPUT_MISMATCH,
                    "Process-only mode forbids all migration-7 supporting inputs.",
                    "supporting_inputs",
                )
            return None, None, {}
        if candidate_value is None or readiness_value is None:
            raise _AdapterProblem(
                FormalInputAdapterFailureCode.MODE_INPUT_MISMATCH,
                "Supporting-evidence mode requires candidate and readiness records.",
                "supporting_inputs",
            )
        try:
            if not isinstance(candidate_value, FormalInputCandidateSet) or not isinstance(
                readiness_value, FormalEvidenceReadiness
            ):
                raise TypeError("supporting input type")
            candidate = FormalInputCandidateSet.model_validate(
                candidate_value.model_dump(mode="json")
            )
            readiness = FormalEvidenceReadiness.model_validate(
                readiness_value.model_dump(mode="json")
            )
        except (TypeError, ValueError, ValidationError) as exc:
            raise _AdapterProblem(
                FormalInputAdapterFailureCode.INVALID_CANDIDATE_OR_READINESS_PIN,
                "Candidate or readiness input is malformed.",
                "supporting_inputs",
            ) from exc

        pin = authorization.input_choice.supporting_candidate
        assert pin is not None
        if (
            candidate.lineage != authorization.approved_process.lineage
            or readiness.lineage != candidate.lineage
            or readiness.candidate_set != candidate
            or readiness.status is not ReadinessStatus.READY_TO_ATTEMPT
            or pin.lineage != candidate.lineage
            or pin.candidate_set_id != candidate.candidate_set_id
            or pin.candidate_set_payload_sha256 != _sha256(candidate)
            or pin.readiness_id != readiness.readiness_id
            or pin.readiness_payload_sha256 != _sha256(readiness)
            or pin.readiness_candidate_set_id != candidate.candidate_set_id
            or pin.readiness_candidate_set_payload_sha256 != _sha256(candidate)
        ):
            raise _AdapterProblem(
                FormalInputAdapterFailureCode.INVALID_CANDIDATE_OR_READINESS_PIN,
                "Candidate/readiness records do not match exact authorization pins.",
                "authorization.input_choice.supporting_candidate",
            )

        reviews: dict[str, SupportingEvidenceReviewRevision] = {}
        try:
            for item in review_values:
                if not isinstance(item, SupportingEvidenceReviewRevision):
                    raise TypeError("review revision type")
                reviewed = SupportingEvidenceReviewRevision.model_validate(
                    item.model_dump(mode="json")
                )
                if reviewed.revision_id in reviews:
                    raise ValueError("duplicate review revision")
                reviews[reviewed.revision_id] = reviewed
        except (TypeError, ValueError, ValidationError) as exc:
            raise _AdapterProblem(
                FormalInputAdapterFailureCode.INVALID_SUPPORTING_PROVENANCE,
                "Supporting review revisions are malformed or duplicated.",
                "supporting_reviews",
            ) from exc
        expected_ids = [item.review_revision_id for item in candidate.current_reviews]
        if set(reviews) != set(expected_ids):
            raise _AdapterProblem(
                FormalInputAdapterFailureCode.INVALID_SUPPORTING_PROVENANCE,
                "Supplied review revisions must equal the current candidate reviews.",
                "supporting_reviews",
            )
        for reference in candidate.current_reviews:
            reviewed = reviews[reference.review_revision_id]
            if (
                reviewed.lineage != candidate.lineage
                or reviewed.proposal_id != reference.proposal_id
                or reviewed.action is not reference.action
                or reviewed.approved_classification is not reference.classification
            ):
                raise _AdapterProblem(
                    FormalInputAdapterFailureCode.INVALID_SUPPORTING_PROVENANCE,
                    "A supplied review revision does not match its current reference.",
                    "supporting_reviews",
                )
        self._validate_mapping_provenance(candidate, reviews)
        return candidate, readiness, reviews

    def _validate_mapping_provenance(
        self,
        candidate: FormalInputCandidateSet,
        reviews: dict[str, SupportingEvidenceReviewRevision],
    ) -> None:
        for mapping in candidate.ordered_formal_mappings:
            if mapping.lineage != candidate.lineage:
                raise _AdapterProblem(
                    FormalInputAdapterFailureCode.INVALID_SUPPORTING_PROVENANCE,
                    "A formal mapping has cross-lineage provenance.",
                    "candidate_set.ordered_formal_mappings",
                    mapping.activity_id,
                )
            if mapping.disposition is MappingDisposition.CONTEXT_ONLY:
                continue
            referenced = []
            for reference in mapping.supporting_reviews:
                reviewed = reviews.get(reference.review_revision_id)
                if reviewed is None or (
                    reviewed.proposal_id != reference.proposal_id
                    or reviewed.action is not reference.action
                    or reviewed.approved_classification is not reference.classification
                ):
                    raise _AdapterProblem(
                        FormalInputAdapterFailureCode.INVALID_SUPPORTING_PROVENANCE,
                        "A mapping does not reference the exact current review revision.",
                        "candidate_set.ordered_formal_mappings",
                        mapping.activity_id,
                    )
                referenced.append(reviewed)
            eligible = [
                item
                for item in referenced
                if item.action
                in {SupportingReviewAction.ACCEPT, SupportingReviewAction.CORRECT}
                and item.candidate_eligible
                and item.approved_classification
                in {
                    EvidenceClassification.DOCUMENTED_FACT,
                    EvidenceClassification.REVIEWED_INFERENCE,
                }
            ]
            if mapping.approved_evidence_classification in {
                EvidenceClassification.DOCUMENTED_FACT,
                EvidenceClassification.REVIEWED_INFERENCE,
            }:
                if not eligible or any(
                    item.approved_classification
                    is not mapping.approved_evidence_classification
                    for item in referenced
                ):
                    raise _AdapterProblem(
                        FormalInputAdapterFailureCode.INVALID_SUPPORTING_PROVENANCE,
                        "A positive mapping lacks exact accepted or corrected evidence.",
                        "candidate_set.ordered_formal_mappings",
                        mapping.activity_id,
                    )
            if (
                mapping.approved_evidence_classification
                is EvidenceClassification.REVIEWED_INFERENCE
            ):
                inference_reviews = [
                    item
                    for item in eligible
                    if item.approved_classification
                    is EvidenceClassification.REVIEWED_INFERENCE
                ]
                fact_ids = {
                    item.review_revision_id
                    for review in inference_reviews
                    for item in review.inference_documented_facts
                }
                if (
                    any(
                        item.inference_confidence != mapping.inference_confidence
                        for item in inference_reviews
                    )
                    or fact_ids != set(mapping.supporting_documented_fact_review_ids)
                    or any(
                        fact_id not in reviews
                        or reviews[fact_id].approved_classification
                        is not EvidenceClassification.DOCUMENTED_FACT
                        for fact_id in fact_ids
                    )
                ):
                    raise _AdapterProblem(
                        FormalInputAdapterFailureCode.INVALID_SUPPORTING_PROVENANCE,
                        "Reviewed-inference confidence or fact links are incomplete.",
                        "candidate_set.ordered_formal_mappings",
                        mapping.activity_id,
                    )

    def _build_projection(
        self,
        authorization: FormalAssessmentAuthorization,
        approved: ApprovedProcessReview,
        candidate: FormalInputCandidateSet | None,
        readiness: FormalEvidenceReadiness | None,
        reviews: dict[str, SupportingEvidenceReviewRevision],
        conflict_sink: list[tuple[CompetingFormalValue, ...]] | None = None,
    ) -> FormalAssessmentInputProjection | None:
        """Build the projection, or collect unresolved conflicts when asked.

        ``conflict_sink`` is the read-only preflight mode: every field follows
        the identical grouping and alternative path, but an unresolved conflict
        is recorded instead of failing and no projection is returned.
        """

        del readiness
        approved_process = BusinessProcess.model_validate(
            approved.business_process.model_dump(mode="json")
        )
        engine_input = BusinessProcess.model_validate(
            approved.business_process.model_dump(mode="json")
        )
        complete_evidence: dict[str, EvidenceReference] = {
            item.evidence_id: item for item in engine_input.evidence
        }
        approved_evidence_by_id = {
            item.evidence_id: item for item in approved_process.evidence
        }
        mappings_by_field: dict[
            tuple[str, tuple[str, str]], list[FormalInputMapping]
        ] = {}
        activity_evidence_mappings: dict[str, list[FormalInputMapping]] = {}
        if candidate is not None:
            known_activity_ids = {item.step_id for item in engine_input.steps}
            for mapping in candidate.ordered_formal_mappings:
                if mapping.activity_id not in known_activity_ids:
                    raise _AdapterProblem(
                        FormalInputAdapterFailureCode.INVALID_SUPPORTING_PROVENANCE,
                        "A mapping references an activity outside the approved process.",
                        "candidate_set.ordered_formal_mappings",
                        mapping.activity_id,
                    )
                if not self._is_positive_mapping(mapping):
                    continue
                assert mapping.target is not None
                if mapping.target.kind is FormalTargetKind.ACTIVITY_EVIDENCE:
                    activity_evidence_mappings.setdefault(
                        mapping.activity_id, []
                    ).append(mapping)
                else:
                    mappings_by_field.setdefault(
                        (mapping.activity_id, _target_key(mapping.target)), []
                    ).append(mapping)

        evidence_by_mapping: dict[str, tuple[EvidenceReference, ...]] = {}
        if candidate is not None:
            for mapping in candidate.ordered_formal_mappings:
                if not self._is_positive_mapping(mapping):
                    continue
                created = self._evidence_for_mapping(mapping, reviews)
                evidence_by_mapping[mapping.mapping_id] = created
                for evidence in created:
                    existing = complete_evidence.get(evidence.evidence_id)
                    if existing is not None and existing != evidence:
                        raise _AdapterProblem(
                            FormalInputAdapterFailureCode.INVALID_SUPPORTING_PROVENANCE,
                            "A deterministic supporting evidence ID collided.",
                            "supporting_evidence",
                            mapping.activity_id,
                        )
                    complete_evidence[evidence.evidence_id] = evidence

        resolution_by_target: dict[
            tuple[str, tuple[str, str]], FormalInputConflictResolution
        ] = {}
        for resolution in authorization.conflict_resolutions:
            key = (resolution.activity_id, _target_key(resolution.target))
            if key in resolution_by_target:
                raise _AdapterProblem(
                    FormalInputAdapterFailureCode.INVALID_CONFLICT_RESOLUTION,
                    "Only one conflict resolution may exist for an activity target.",
                    "authorization.conflict_resolutions",
                    resolution.activity_id,
                )
            resolution_by_target[key] = resolution

        activities: list[FormalAssessmentActivityProjection] = []
        used_resolution_keys: set[tuple[str, tuple[str, str]]] = set()
        engine_steps = {item.step_id: item for item in engine_input.steps}
        approved_steps = {item.step_id: item for item in approved_process.steps}
        for approved_step in approved_process.steps:
            projected_step = engine_steps[approved_step.step_id]
            activity_mappings = activity_evidence_mappings.get(
                approved_step.step_id, []
            )
            for mapping in activity_mappings:
                for evidence in evidence_by_mapping[mapping.mapping_id]:
                    if evidence.evidence_id not in projected_step.evidence_ids:
                        projected_step.evidence_ids.append(evidence.evidence_id)
            traces: list[FormalFieldResolutionTrace] = []
            for target in _scalar_targets():
                field_key = (approved_step.step_id, _target_key(target))
                field_mappings = mappings_by_field.get(field_key, [])
                trace, projected = self._project_field(
                    authorization,
                    approved_step,
                    target,
                    field_mappings,
                    evidence_by_mapping,
                    resolution_by_target.get(field_key),
                    approved_evidence_by_id,
                    conflict_sink,
                )
                if trace is None:
                    continue
                if trace.conflict_resolution_id is not None:
                    used_resolution_keys.add(field_key)
                _set_input(projected_step, target, projected)
                traces.append(trace)
            if conflict_sink is not None:
                continue
            activities.append(
                FormalAssessmentActivityProjection(
                    activity_id=projected_step.step_id,
                    sequence=projected_step.sequence,
                    engine_input=projected_step,
                    field_resolutions=tuple(traces),
                    activity_evidence=tuple(
                        complete_evidence[item]
                        for item in projected_step.evidence_ids
                    ),
                )
            )

        extra_resolutions = set(resolution_by_target) - used_resolution_keys
        if extra_resolutions:
            activity_id, _ = sorted(extra_resolutions)[0]
            raise _AdapterProblem(
                FormalInputAdapterFailureCode.INVALID_CONFLICT_RESOLUTION,
                "A conflict resolution is attached to a non-conflicting field.",
                "authorization.conflict_resolutions",
                activity_id,
            )
        if conflict_sink is not None:
            return None
        engine_input.evidence = list(complete_evidence.values())
        engine_input = BusinessProcess.model_validate(engine_input.model_dump(mode="json"))
        activities = [
            item.model_copy(
                update={"engine_input": engine_input.steps[index]}
            )
            for index, item in enumerate(activities)
        ]
        try:
            return FormalAssessmentInputProjection(
                schema_version=FORMAL_ASSESSMENT_INPUT_PROJECTION_SCHEMA,
                store_contract=FORMAL_ASSESSMENT_RUN_STORE_ID,
                projection_id=authorization.run_lineage.projection_id,
                run_lineage=authorization.run_lineage,
                authorization=authorization,
                approved_process=approved_process,
                engine_input=engine_input,
                activities=tuple(activities),
                complete_evidence=tuple(complete_evidence.values()),
            )
        except (TypeError, ValueError, ValidationError) as exc:
            raise _AdapterProblem(
                FormalInputAdapterFailureCode.PROJECTION_VALIDATION_FAILED,
                f"The deterministic projection failed contract validation: {exc}",
                "projection",
            ) from exc

    @staticmethod
    def _is_positive_mapping(mapping: FormalInputMapping) -> bool:
        return (
            mapping.disposition is MappingDisposition.MAPPED_FORMAL_INPUT
            and mapping.approved_evidence_classification
            in {
                EvidenceClassification.DOCUMENTED_FACT,
                EvidenceClassification.REVIEWED_INFERENCE,
            }
            and (
                mapping.target is not None
                and (
                    mapping.target.kind is FormalTargetKind.ACTIVITY_EVIDENCE
                    or mapping.value is not None
                )
            )
        )

    def _evidence_for_mapping(
        self,
        mapping: FormalInputMapping,
        reviews: dict[str, SupportingEvidenceReviewRevision],
    ) -> tuple[EvidenceReference, ...]:
        result: list[EvidenceReference] = []
        seen: set[str] = set()
        ordered_review_ids = [
            item.review_revision_id for item in mapping.supporting_reviews
        ]
        ordered_review_ids.extend(
            item
            for item in mapping.supporting_documented_fact_review_ids
            if item not in ordered_review_ids
        )
        for review_id in ordered_review_ids:
            review = reviews[review_id]
            classification = review.approved_classification
            if classification is EvidenceClassification.REVIEWED_INFERENCE:
                state = KnowledgeState.INFERRED
                confidence = review.inference_confidence
                uncertainty = UncertaintyStatus.UNCERTAIN
            else:
                state = KnowledgeState.KNOWN
                confidence = None
                uncertainty = UncertaintyStatus.CERTAIN
            for span in review.source_spans:
                provenance_payload = {
                    "contract": "formal-supporting-evidence-reference.v0.1",
                    "mapping_id": mapping.mapping_id,
                    "review_revision_id": review.revision_id,
                    "proposal_id": review.proposal_id,
                    "classification": classification.value,
                    "document_id": span.document_id,
                    "document_content_sha256": span.document_content_sha256,
                    "parsed_document_id": span.parsed_document_id,
                    "block_id": span.block_id,
                    "excerpt_sha256": span.excerpt_sha256,
                    "locator": span.locator,
                }
                evidence_id = f"fev-{_sha256(provenance_payload)}"
                if evidence_id in seen:
                    continue
                seen.add(evidence_id)
                result.append(
                    EvidenceReference(
                        evidence_id=evidence_id,
                        source_id=span.document_id,
                        source_locator=span.locator,
                        supporting_snippet=span.exact_excerpt,
                        provenance=json.dumps(
                            provenance_payload,
                            allow_nan=False,
                            ensure_ascii=False,
                            separators=(",", ":"),
                            sort_keys=True,
                        ),
                        knowledge_state=state,
                        uncertainty_status=uncertainty,
                        confidence=confidence,
                    )
                )
        if not result:
            raise _AdapterProblem(
                FormalInputAdapterFailureCode.INVALID_SUPPORTING_PROVENANCE,
                "An eligible mapping has no exact reviewed source span.",
                "candidate_set.ordered_formal_mappings",
                mapping.activity_id,
            )
        return tuple(result)

    def _project_field(
        self,
        authorization: FormalAssessmentAuthorization,
        approved_step: ProcessStep,
        target: FormalTarget,
        mappings: list[FormalInputMapping],
        evidence_by_mapping: dict[str, tuple[EvidenceReference, ...]],
        resolution: FormalInputConflictResolution | None,
        approved_evidence_by_id: dict[str, EvidenceReference],
        conflict_sink: list[tuple[CompetingFormalValue, ...]] | None = None,
    ) -> tuple[
        FormalFieldResolutionTrace | None, CriterionInput | BooleanCriterionInput
    ]:
        approved_input = _input_for_target(approved_step, target)
        groups = self._groups(mappings, evidence_by_mapping)
        approved_key = None
        if approved_input.knowledge_state is not KnowledgeState.UNKNOWN:
            approved_key = (
                type(approved_input.value).__name__,
                approved_input.value,
                approved_input.knowledge_state,
                approved_input.confidence,
            )
        field_path = _target_path("approved_process", approved_step.step_id, target)
        projected_path = _target_path("engine_input", approved_step.step_id, target)

        if not groups:
            if resolution is not None:
                self._extra_resolution(approved_step.step_id)
            trace = FormalFieldResolutionTrace(
                activity_id=approved_step.step_id,
                target=target,
                approved_process_field_path=field_path,
                projected_field_path=projected_path,
                approved_value=approved_input.value,
                approved_knowledge_state=approved_input.knowledge_state,
                projected_value=approved_input.value,
                projected_knowledge_state=approved_input.knowledge_state,
                projected_confidence=approved_input.confidence,
                origin=ProjectedValueOrigin.SOURCE_ONLY,
                evidence_ids=tuple(approved_input.evidence_ids),
            )
            return trace, approved_input.model_copy(deep=True)

        groups_by_key = {item.key: item for item in groups}
        distinct_keys = set(groups_by_key)
        if approved_key is None and len(distinct_keys) == 1:
            if resolution is not None:
                self._extra_resolution(approved_step.step_id)
            group = groups[0]
            projected = self._projected_input(target, group)
            return (
                self._trace(
                    approved_step,
                    target,
                    approved_input,
                    projected,
                    ProjectedValueOrigin.FILLED_UNKNOWN,
                    group.mapping_pins,
                ),
                projected,
            )
        if approved_key is not None and distinct_keys == {approved_key}:
            if resolution is not None:
                self._extra_resolution(approved_step.step_id)
            group = groups_by_key[approved_key]
            evidence_ids = tuple(
                dict.fromkeys(
                    [*approved_input.evidence_ids, *(item.evidence_id for item in group.evidence)]
                )
            )
            projected = approved_input.model_copy(
                deep=True,
                update={"evidence_ids": list(evidence_ids)},
            )
            return (
                self._trace(
                    approved_step,
                    target,
                    approved_input,
                    projected,
                    ProjectedValueOrigin.CORROBORATED,
                    group.mapping_pins,
                ),
                projected,
            )

        expected = self._conflict_alternatives(
            authorization,
            approved_step,
            target,
            approved_input,
            groups,
            approved_evidence_by_id,
        )
        if resolution is None and conflict_sink is not None:
            conflict_sink.append(expected)
            return None, approved_input.model_copy(deep=True)
        if resolution is None:
            raise _AdapterProblem(
                FormalInputAdapterFailureCode.UNRESOLVED_CONFLICT,
                "Distinct effective values require an exact authorized human resolution.",
                projected_path,
                approved_step.step_id,
            )
        if (
            resolution.lineage != authorization.approved_process.lineage
            or resolution.run_lineage != authorization.run_lineage
            or resolution.activity_id != approved_step.step_id
            or resolution.target != target
            or resolution.alternatives != expected
        ):
            raise _AdapterProblem(
                FormalInputAdapterFailureCode.INVALID_CONFLICT_RESOLUTION,
                "Conflict resolution does not contain every exact effective alternative.",
                "authorization.conflict_resolutions",
                approved_step.step_id,
            )
        selected_key = (
            type(resolution.selected_value).__name__,
            resolution.selected_value,
            resolution.selected_knowledge_state,
            resolution.selected_confidence,
        )
        if selected_key == approved_key:
            selected_alternative = next(
                item
                for item in expected
                if (
                    type(item.value).__name__,
                    item.value,
                    item.knowledge_state,
                    item.confidence,
                )
                == selected_key
            )
            selected_evidence_ids = tuple(
                item.evidence_id for item in selected_alternative.evidence
            )
            selected_rationale = approved_input.rationale
        else:
            selected_group = groups_by_key.get(selected_key)
            if selected_group is None:
                raise _AdapterProblem(
                    FormalInputAdapterFailureCode.INVALID_CONFLICT_RESOLUTION,
                    "Selected conflict value is not an effective alternative.",
                    "authorization.conflict_resolutions",
                    approved_step.step_id,
                )
            selected_evidence_ids = tuple(
                item.evidence_id for item in selected_group.evidence
            )
            selected_rationale = self._supporting_rationale(selected_group.mappings)
        projected = self._new_input(
            target,
            resolution.selected_value,
            resolution.selected_knowledge_state,
            selected_rationale,
            selected_evidence_ids,
            resolution.selected_confidence,
        )
        all_mapping_pins = tuple(
            pin for group in groups for pin in group.mapping_pins
        )
        trace = self._trace(
            approved_step,
            target,
            approved_input,
            projected,
            ProjectedValueOrigin.EXPLICITLY_RESOLVED,
            all_mapping_pins,
            resolution.resolution_id,
        )
        return trace, projected

    @staticmethod
    def _groups(
        mappings: list[FormalInputMapping],
        evidence_by_mapping: dict[str, tuple[EvidenceReference, ...]],
    ) -> tuple[_EffectiveGroup, ...]:
        grouped: dict[
            tuple[str, int | bool, KnowledgeState, float | None],
            tuple[list[FormalInputMapping], list[EvidenceReference]],
        ] = {}
        for mapping in mappings:
            assert mapping.value is not None
            key = (
                type(mapping.value).__name__,
                mapping.value,
                mapping.knowledge_state,
                mapping.inference_confidence,
            )
            mapping_items, evidence_items = grouped.setdefault(key, ([], []))
            mapping_items.append(mapping)
            known_ids = {item.evidence_id for item in evidence_items}
            evidence_items.extend(
                item
                for item in evidence_by_mapping[mapping.mapping_id]
                if item.evidence_id not in known_ids
            )
        return tuple(
            _EffectiveGroup(
                value=key[1],
                knowledge_state=key[2],
                confidence=key[3],
                mappings=tuple(items[0]),
                evidence=tuple(items[1]),
            )
            for key, items in grouped.items()
        )

    def _conflict_alternatives(
        self,
        authorization: FormalAssessmentAuthorization,
        step: ProcessStep,
        target: FormalTarget,
        approved_input: Any,
        groups: tuple[_EffectiveGroup, ...],
        approved_evidence_by_id: dict[str, EvidenceReference],
    ) -> tuple[CompetingFormalValue, ...]:
        result: list[CompetingFormalValue] = []
        approved_key = None
        if approved_input.knowledge_state is not KnowledgeState.UNKNOWN:
            approved_key = (
                type(approved_input.value).__name__,
                approved_input.value,
                approved_input.knowledge_state,
                approved_input.confidence,
            )
            corroborating = next(
                (item for item in groups if item.key == approved_key), None
            )
            try:
                approved_evidence = tuple(
                    _evidence_pin(approved_evidence_by_id[item])
                    for item in approved_input.evidence_ids
                )
            except KeyError as exc:
                raise _AdapterProblem(
                    FormalInputAdapterFailureCode.INVALID_APPROVED_LINEAGE,
                    "Approved conflict provenance references unknown source evidence.",
                    "approved_review.business_process.evidence",
                    step.step_id,
                ) from exc
            if corroborating is None:
                origin = FormalValueOrigin.APPROVED_PROCESS
                mappings: tuple[FormalMappingReferencePin, ...] = ()
                evidence = approved_evidence
            else:
                origin = FormalValueOrigin.CORROBORATED
                mappings = corroborating.mapping_pins
                evidence_by_id = {
                    item.evidence_id: item
                    for item in [*approved_evidence, *corroborating.evidence_pins]
                }
                evidence = tuple(evidence_by_id.values())
            result.append(
                CompetingFormalValue(
                    lineage=authorization.approved_process.lineage,
                    activity_id=step.step_id,
                    target=target,
                    origin=origin,
                    value=approved_input.value,
                    knowledge_state=approved_input.knowledge_state,
                    confidence=approved_input.confidence,
                    approved_process_field_path=_target_path(
                        "approved_process", step.step_id, target
                    ),
                    evidence=evidence,
                    supporting_mappings=mappings,
                )
            )
        for group in groups:
            if group.key == approved_key:
                continue
            result.append(
                CompetingFormalValue(
                    lineage=authorization.approved_process.lineage,
                    activity_id=step.step_id,
                    target=target,
                    origin=FormalValueOrigin.SUPPORTING_MAPPING,
                    value=group.value,
                    knowledge_state=group.knowledge_state,
                    confidence=group.confidence,
                    evidence=group.evidence_pins,
                    supporting_mappings=group.mapping_pins,
                )
            )
        return tuple(result)

    @staticmethod
    def _projected_input(
        target: FormalTarget,
        group: _EffectiveGroup,
    ) -> CriterionInput | BooleanCriterionInput:
        return FormalFourGateInputAdapter._new_input(
            target,
            group.value,
            group.knowledge_state,
            FormalFourGateInputAdapter._supporting_rationale(group.mappings),
            tuple(item.evidence_id for item in group.evidence),
            group.confidence,
        )

    @staticmethod
    def _new_input(
        target: FormalTarget,
        value: int | bool | None,
        knowledge_state: KnowledgeState,
        rationale: str,
        evidence_ids: tuple[str, ...],
        confidence: float | None,
    ) -> CriterionInput | BooleanCriterionInput:
        payload = {
            "value": value,
            "knowledge_state": knowledge_state,
            "rationale": rationale,
            "evidence_ids": list(evidence_ids),
            "confidence": confidence,
        }
        if target.kind is FormalTargetKind.CRITERION:
            return CriterionInput(**payload)
        if target.kind is FormalTargetKind.HUMAN_ACCOUNTABILITY_REQUIRED:
            return BooleanCriterionInput(**payload)
        return CapabilitySignalInput(**payload)

    @staticmethod
    def _supporting_rationale(mappings: tuple[FormalInputMapping, ...]) -> str:
        return "Reviewed supporting evidence: " + " | ".join(
            item.mapping_rationale for item in mappings
        )

    @staticmethod
    def _trace(
        step: ProcessStep,
        target: FormalTarget,
        approved_input: Any,
        projected_input: Any,
        origin: ProjectedValueOrigin,
        mappings: tuple[FormalMappingReferencePin, ...],
        conflict_resolution_id: str | None = None,
    ) -> FormalFieldResolutionTrace:
        return FormalFieldResolutionTrace(
            activity_id=step.step_id,
            target=target,
            approved_process_field_path=_target_path(
                "approved_process", step.step_id, target
            ),
            projected_field_path=_target_path("engine_input", step.step_id, target),
            approved_value=approved_input.value,
            approved_knowledge_state=approved_input.knowledge_state,
            projected_value=projected_input.value,
            projected_knowledge_state=projected_input.knowledge_state,
            projected_confidence=projected_input.confidence,
            origin=origin,
            evidence_ids=tuple(projected_input.evidence_ids),
            supporting_mappings=mappings,
            conflict_resolution_id=conflict_resolution_id,
        )

    @staticmethod
    def _extra_resolution(activity_id: str) -> None:
        raise _AdapterProblem(
            FormalInputAdapterFailureCode.INVALID_CONFLICT_RESOLUTION,
            "A conflict resolution is attached to a non-conflicting field.",
            "authorization.conflict_resolutions",
            activity_id,
        )
