from __future__ import annotations

import json

import pytest

from ai_adoption_engine.grw.m2.instrument import load_instrument_reference
from ai_adoption_engine.grw.m2.policy import load_policy_reference


def test_m2_policy_and_instrument_are_stable_and_narrow(tmp_path) -> None:
    payload, policy = load_policy_reference()
    instrument_payload, instrument = load_instrument_reference()
    assert payload["allowed_criterion"] == "data_readiness"
    assert payload["allowed_evidence_class"] == "DOCUMENT_SUPPORTED"
    assert instrument_payload["allowed_values"] == [0, 1, 2, 3, 4]
    altered = tmp_path / "instrument.json"
    altered.write_text(json.dumps({**instrument_payload, "version": "0.1.1"}), encoding="utf-8")
    assert load_instrument_reference(altered)[1].fingerprint != instrument.fingerprint
    assert len(policy.fingerprint) == 64


def test_m2_instrument_refuses_value_five_configuration(tmp_path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps({"instrument_id": "x", "version": "1", "criterion": "data_readiness", "allowed_values": [0, 1, 2, 3, 4, 5], "anchors": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="0..4"):
        load_instrument_reference(path)
