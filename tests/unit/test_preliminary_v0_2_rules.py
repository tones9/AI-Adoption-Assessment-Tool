import pytest

from ai_adoption_engine.models.preliminary_assessment_v0_2 import ComponentAction
from ai_adoption_engine.preliminary.evaluator_v0_2 import (
    Clause,
    _match_clause,
    normalize_matching_text,
    segment_clauses,
)
from ai_adoption_engine.preliminary.rules_v0_2 import (
    LITERAL_MANIFEST,
    PRELIMINARY_EVALUATOR_RULES_V0_2,
)


def _sentence(rule: str, action: ComponentAction, form: str) -> str:
    if rule == "PD2-001": return f"The officer {form} the complaint."
    if rule == "PD2-002": return f"The officer {form} the complaint record."
    if rule == "PD2-003": return f"The officer {form} staff of the complaint."
    if rule == "PD2-004": return f"The officer {form} the complaint to the team."
    if rule == "PD2-005": return f"The officer {form} the complaint hearing."
    if rule == "PD2-006": return f"The officer {form} the complaint status."
    if rule == "PD2-007": return f"The officer {form} the source record to produce the result record."
    if rule == "PD2-008": return f"The officer {form} the complaint to identify the issue."
    if rule == "PD2-009": return f"The officer {form} the complaint to establish findings."
    if rule == "PD2-010": return f"The officer {form} the complaint as stage 1."
    if rule == "PD2-011": return f"The officer {form} the complaints register."
    if rule == "PD2-012": return f"The officer {form} the options to produce the recommendation."
    if rule == "PD2-013" and action is ComponentAction.SUMMARISE: return f"Using the report, the officer {form} the report."
    if rule == "PD2-013": return f"The officer {form} the response."
    if rule == "PD2-014": return f"The officer {form} the data to produce the flagged condition."
    if rule == "PD2-015": return f"The officer {form} the complainant to produce agreed points."
    if rule == "PD2-016": return f"The officer {form} the final determination."
    if rule == "PD2-017": return f"The officer {form} to determine the exception treatment."
    if rule == "PD2-018": return f"The officer {form} the complaint to produce the corrected state."
    return f"The officer {form} the complaint to produce the delayed state."


@pytest.mark.parametrize(
    ("family", "surface"),
    [
        (family, surface)
        for family in LITERAL_MANIFEST
        if family.component_action is not None
        for surface in family.surface_forms
    ],
)
def test_every_literal_and_listed_inflection_is_accepted(family, surface) -> None:
    text = _sentence(family.pd2_rule_code, family.component_action, surface)
    matches = _match_clause(Clause(index=0, start=0, end=len(text), text=text))
    assert family.matched_literal_code in {item.family.matched_literal_code for item in matches}


def test_literal_codes_are_stable_unique_families_and_fingerprint_is_pinned() -> None:
    codes = [item.matched_literal_code for item in LITERAL_MANIFEST]
    assert len(codes) == len(set(codes)) == 124
    assert codes[0] == "PD2-001-L001"
    assert codes[-1] == "PD2-021-L006"
    assert PRELIMINARY_EVALUATOR_RULES_V0_2.fingerprint() == "1c06b6a9ce1fe9ee3f68c9b16a452ca2c283e3423a39ae6ef43bd5ccecb855c6"


def test_pd2_021_structural_literal_codes_are_manifested_but_never_actions() -> None:
    structural = [item for item in LITERAL_MANIFEST if item.pd2_rule_code == "PD2-021"]
    assert [item.matched_literal_code for item in structural] == [
        f"PD2-021-L{index:03d}" for index in range(1, 7)
    ]
    assert all(item.component_action is None for item in structural)


@pytest.mark.parametrize("word", ["recordation", "notifier", "transference", "analysises", "approvement", "recommender"])
def test_nearby_and_unlisted_words_are_rejected(word) -> None:
    text = f"The officer {word} the complaint to produce a result."
    assert not _match_clause(Clause(index=0, start=0, end=len(text), text=text))


@pytest.mark.parametrize("prefix", ["does not", "will", "may", "might", "could", "optionally"])
def test_negation_future_and_optional_wording_are_rejected(prefix) -> None:
    text = f"The officer {prefix} record the complaint."
    assert not _match_clause(Clause(index=0, start=0, end=len(text), text=text))


def test_normative_should_is_accepted_only_with_all_required_fields() -> None:
    accepted = "The officer should notify staff of the complaint."
    rejected = "The officer should notify staff."
    assert _match_clause(Clause(index=0, start=0, end=len(accepted), text=accepted))
    assert not _match_clause(Clause(index=0, start=0, end=len(rejected), text=rejected))


def test_quotes_are_excluded_and_longest_phrase_wins() -> None:
    quoted = 'The guide says "the officer records the complaint".'
    assert not _match_clause(Clause(index=0, start=0, end=len(quoted), text=quoted))
    text = "The officer makes the final determination."
    matches = _match_clause(Clause(index=0, start=0, end=len(text), text=text))
    assert [item.family.matched_literal_code for item in matches] == ["PD2-016-L003"]


def test_normalization_and_segmentation_are_deterministic() -> None:
    assert normalize_matching_text("  ＲＥＣＯＲＤ—Complaint\tNow ") == "record complaint now"
    text = "Dr. Rao records the case; then routes it to Team A.\nOfficer notifies staff of the case."
    first = segment_clauses(text)
    assert first == segment_clauses(text)
    assert len(first) == 3


def test_notification_transfer_and_accountable_system_guards() -> None:
    missing_subject = "The officer notifies staff."
    assert not _match_clause(Clause(index=0, start=0, end=len(missing_subject), text=missing_subject))
    transfer = "The officer transfers the complaint to the team."
    assert _match_clause(Clause(index=0, start=0, end=len(transfer), text=transfer))[0].family.component_action is ComponentAction.ROUTE
    system = "The system approves the final determination."
    assert not _match_clause(Clause(index=0, start=0, end=len(system), text=system))
