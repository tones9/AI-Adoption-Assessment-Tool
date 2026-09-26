"""Closed decision-contract pin identities used by persistence adapters."""

from __future__ import annotations

from ai_adoption_engine.workspace.models import AssessmentContractPin


LEGACY_POLICY_FINGERPRINT = (
    "b72e528b102bf893b45e6de9ec311e0888341d12b8aa3f99b8047e324d6a6d66"
)

LEGACY_CONTRACT_PIN = AssessmentContractPin(
    decision_contract_version="phase1-v0.3",
    policy_id="decision_policy.v0.2",
    policy_version="0.2.0",
    decision_policy_fingerprint=LEGACY_POLICY_FINGERPRINT,
)

VIRTUAL_LEGACY_CONTRACT_PIN = LEGACY_CONTRACT_PIN.model_copy(
    update={"virtual": True}
)


def successor_contract_pin(policy_fingerprint: str) -> AssessmentContractPin:
    """Build an explicit successor pin; no default policy is loaded here."""

    return AssessmentContractPin(
        decision_contract_version="phase1-v0.4",
        policy_id="decision_policy.v0.3",
        policy_version="0.3.0",
        decision_policy_fingerprint=policy_fingerprint,
    )


def contract_operation_identity(
    idempotency_key: str,
    pin: AssessmentContractPin,
) -> str:
    """Scope an assessment/package operation to its immutable contract pin."""

    return ":".join(
        (
            pin.decision_contract_version,
            pin.decision_policy_fingerprint,
            idempotency_key,
        )
    )
