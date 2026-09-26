"""Exact presentation dispatch for legacy and successor artifact contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from ai_adoption_engine.models.decision_support import DecisionSupportPackage
from ai_adoption_engine.models.four_gate_decision_support import (
    FourGateDecisionSupportPackage,
)
from ai_adoption_engine.models.four_gate_integrated_assessment import (
    FourGateIntegratedAssessmentSuccess,
)
from ai_adoption_engine.models.integrated_assessment import (
    IntegratedAssessmentSuccess,
)


class PresentationContract(StrEnum):
    LEGACY = "legacy"
    FOUR_GATE = "four-gate"


class UnsupportedPresentationContract(ValueError):
    """Raised when no exact presentation contract matches an artifact."""


def phase5_presentation_contract(value: Any) -> PresentationContract:
    """Classify one successful Phase 5 artifact without version fallback."""

    if isinstance(value, IntegratedAssessmentSuccess):
        if (
            value.metadata.integration_schema_version == "phase5-v0.1"
            and value.metadata.phase1_contract_version == "phase1-v0.3"
        ):
            return PresentationContract.LEGACY
    elif isinstance(value, FourGateIntegratedAssessmentSuccess):
        if (
            value.metadata.integration_schema_version == "phase5-v0.2"
            and value.metadata.phase1_contract_version == "phase1-v0.4"
            and value.process_assessment.framework_id
            == "four-gate-framework.v0.1"
        ):
            return PresentationContract.FOUR_GATE
    raise UnsupportedPresentationContract(
        "The Phase 5 artifact contract is not supported for presentation."
    )


def phase6_presentation_contract(value: Any) -> PresentationContract:
    """Classify one Phase 6 package without guessing from its contents."""

    if isinstance(value, DecisionSupportPackage):
        if value.package_schema_version == "phase6-v0.1":
            return PresentationContract.LEGACY
    elif isinstance(value, FourGateDecisionSupportPackage):
        if (
            value.package_schema_version == "phase6-v0.2"
            and value.source.integration_schema_version == "phase5-v0.2"
            and value.source.phase1_contract_version == "phase1-v0.4"
            and value.current_state.framework_id
            == "four-gate-framework.v0.1"
        ):
            return PresentationContract.FOUR_GATE
    raise UnsupportedPresentationContract(
        "The Phase 6 artifact contract is not supported for presentation."
    )
