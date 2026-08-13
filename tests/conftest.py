import json
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
)

from ai_adoption_engine.decision.engine import AssessmentEngine
from ai_adoption_engine.decision.policy import DecisionPolicy, load_policy
from ai_adoption_engine.models.process import BusinessProcess

PROJECT_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = PROJECT_ROOT / "config" / "decision_policy.v0.2.json"
SAMPLE_PATH = (
    PROJECT_ROOT
    / "data"
    / "sample_processes"
    / "synthetic_customer_complaint_process.json"
)


@pytest.fixture
def policy() -> DecisionPolicy:
    return load_policy(POLICY_PATH)


@pytest.fixture
def process() -> BusinessProcess:
    with SAMPLE_PATH.open(encoding="utf-8") as handle:
        return BusinessProcess.model_validate(json.load(handle))


@pytest.fixture
def engine(policy: DecisionPolicy) -> AssessmentEngine:
    return AssessmentEngine(policy)


@pytest.fixture
def pdf_fixture_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_metadata({"/Title": "Traceable Phase 2 Fixture", "/Author": "Test Suite"})
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)
    for text in ("Page one process text", None, "Page three process text"):
        page = writer.add_blank_page(width=612, height=792)
        if text is None:
            continue
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {NameObject("/F1"): font_ref}
                )
            }
        )
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.fixture
def encrypted_pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt("test-password")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()
