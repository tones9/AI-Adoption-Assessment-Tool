import hashlib
import json

import pytest

from ai_adoption_engine.persistence.base import ArtifactCorruptionError
from ai_adoption_engine.persistence.formal_evidence_serialization import (
    FORMAL_EVIDENCE_ADAPTERS,
    deserialize_formal_evidence_record,
    serialize_formal_evidence_record,
)
from tests.unit.test_formal_evidence_models import proposal, reviewer


EXPECTED_SCHEMAS = {
    "supporting-source-blob.v0.1",
    "supporting-document.v0.1",
    "supporting-document-metadata-revision.v0.1",
    "supporting-document-ingestion-attempt.v0.1",
    "supporting-evidence-extraction-attempt.v0.1",
    "supporting-evidence-proposal.v0.1",
    "supporting-evidence-review-revision.v0.1",
    "formal-input-mapping.v0.1",
    "formal-input-candidate-set.v0.1",
    "formal-evidence-readiness.v0.1",
    "formal-evidence-workflow-event.v0.1",
    "reviewer-declaration.v0.1",
    "external-provider-consent.v0.1",
    "context-note.v0.1",
}


def test_exact_slice_one_serialization_registry_is_closed() -> None:
    assert set(FORMAL_EVIDENCE_ADAPTERS) == EXPECTED_SCHEMAS


@pytest.mark.parametrize("record", [reviewer(), proposal()])
def test_canonical_payload_and_hash_are_stable_and_round_trip_exactly(record) -> None:
    first = serialize_formal_evidence_record(record)
    second = serialize_formal_evidence_record(record)
    assert first == second
    assert hashlib.sha256(first[0].encode()).hexdigest() == first[1]
    assert deserialize_formal_evidence_record(record.schema_version, *first) == record


def test_unknown_schema_family_hash_and_fields_fail_closed() -> None:
    record = reviewer()
    payload_json, payload_sha = serialize_formal_evidence_record(record)
    with pytest.raises(ArtifactCorruptionError, match="Unsupported"):
        deserialize_formal_evidence_record(
            "reviewer-declaration.v9.9", payload_json, payload_sha
        )
    with pytest.raises(ArtifactCorruptionError, match="integrity"):
        deserialize_formal_evidence_record(
            record.schema_version, payload_json, "0" * 64
        )

    payload = json.loads(payload_json)
    payload["contract_family"] = "preliminary-formal-evidence.v9.9"
    corrupt_family = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    with pytest.raises(ArtifactCorruptionError, match="schema validation"):
        deserialize_formal_evidence_record(
            record.schema_version,
            corrupt_family,
            hashlib.sha256(corrupt_family.encode()).hexdigest(),
        )

    payload = json.loads(payload_json)
    payload["unexpected"] = True
    corrupt_extra = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    with pytest.raises(ArtifactCorruptionError, match="schema validation"):
        deserialize_formal_evidence_record(
            record.schema_version,
            corrupt_extra,
            hashlib.sha256(corrupt_extra.encode()).hexdigest(),
        )
