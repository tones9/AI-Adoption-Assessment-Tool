from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ai_adoption_engine.grw.m2.models import M2DocumentLocator, M2SupportingDocument


def test_m2_document_identity_and_locator_fail_closed() -> None:
    digest = "a" * 64
    doc = M2SupportingDocument(document_id=f"doc-{digest}", content_sha256=digest, filename="source.txt", byte_length=3, received_at=datetime.now(UTC), source_label="owner")
    assert doc.content_type == "text/plain"
    with pytest.raises(ValidationError):
        M2SupportingDocument(document_id="doc-" + "b" * 64, content_sha256=digest, filename="source.txt", byte_length=3, received_at=datetime.now(UTC), source_label="owner")
    with pytest.raises(ValidationError):
        M2DocumentLocator(start_offset=3, end_offset=3, line_start=1, line_end=1, exact_excerpt="x")
