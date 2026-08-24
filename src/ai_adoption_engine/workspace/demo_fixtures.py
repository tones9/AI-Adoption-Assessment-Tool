"""The bundled offline demonstration fixtures, and how a document selects one.

Two fixtures ship with the application, and they are complementary:

* the **evidence-gap** fixture, whose source narrative states no assessment
  criterion, so every activity honestly reaches "more information needed"; and
* the **decision-variety** fixture, whose source records the operational facts
  an adoption decision needs, so the activities reach different outcomes.

Both are SYNTHETIC DEMONSTRATION DATA.  Neither is a customer process, research
evidence, or a record of any measured outcome.

Selection is by document identity alone.  Offline scripted extraction has always
been bound to the exact bundled document it was written for; this registry keeps
that binding and simply allows more than one entry.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ai_adoption_engine.workspace import demo_extraction, demo_field_service


SYNTHETIC_LABEL = "SYNTHETIC DEMONSTRATION DATA"


@dataclass(frozen=True)
class DemoFixture:
    """One bundled synthetic document and the scripted response written for it."""

    key: str
    title: str
    summary: str
    source_label: str
    text: Callable[[], str]
    document_id: Callable[[], str]
    provider: Callable[[], Any]


EVIDENCE_GAP = DemoFixture(
    key="evidence-gap",
    title="Customer complaint handling — evidence gap",
    summary=(
        "A process narrative that states no assessment criterion. Every activity "
        "reaches 'more information needed', which is what the engine does when a "
        "document does not support a decision."
    ),
    source_label="synthetic_complaint_process.txt",
    text=demo_extraction.demo_text,
    document_id=demo_extraction.demo_document_id,
    provider=demo_extraction.ScriptedDemoExtractionProvider,
)

DECISION_VARIETY = DemoFixture(
    key="decision-variety",
    title="Field service request handling — documented facts",
    summary=(
        "A process whose source records the operational facts an adoption "
        "decision needs. The activities reach different outcomes, and one keeps "
        "an open data-readiness question."
    ),
    source_label="synthetic_field_service_process.txt",
    text=demo_field_service.field_service_text,
    document_id=demo_field_service.field_service_document_id,
    provider=demo_field_service.ScriptedFieldServiceExtractionProvider,
)

DEMO_FIXTURES: tuple[DemoFixture, ...] = (EVIDENCE_GAP, DECISION_VARIETY)


def fixture_for_document_id(document_id: str) -> DemoFixture | None:
    """Return the bundled fixture a document is, or ``None`` for anything else."""

    for fixture in DEMO_FIXTURES:
        if fixture.document_id() == document_id:
            return fixture
    return None


def fixture_for_key(key: str) -> DemoFixture:
    """Return one bundled fixture by its stable key."""

    for fixture in DEMO_FIXTURES:
        if fixture.key == key:
            return fixture
    raise KeyError(f"Unknown demo fixture: {key}")
