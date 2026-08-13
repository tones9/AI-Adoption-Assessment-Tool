"""Transparent priority scoring for opportunities that pass the gates."""

from ai_adoption_engine.decision.policy import DecisionPolicy
from ai_adoption_engine.models.assessment import PriorityScore, ScoreComponent
from ai_adoption_engine.models.enums import PriorityBand
from ai_adoption_engine.models.process import ProcessStep


def calculate_priority(step: ProcessStep, policy: DecisionPolicy) -> PriorityScore:
    components: list[ScoreComponent] = []
    total = 0.0
    scale_maximum = policy.scale.maximum

    for criterion_name, criterion_policy in policy.scoring.criteria.items():
        criterion = step.characteristics.criterion(criterion_name)
        if criterion.value is None:
            raise ValueError(f"Cannot score unknown criterion: {criterion_name.value}")
        favourable_value = (
            criterion.value
            if criterion_policy.direction == "favourable"
            else scale_maximum - criterion.value
        )
        contribution = favourable_value / scale_maximum * criterion_policy.weight * 100
        total += contribution
        components.append(
            ScoreComponent(
                criterion=criterion_name,
                raw_value=criterion.value,
                favourable_value=favourable_value,
                weight=criterion_policy.weight,
                contribution=round(contribution, 2),
            )
        )

    score = round(total, 2)
    if score >= policy.scoring.bands.high_minimum:
        band = PriorityBand.HIGH
    elif score >= policy.scoring.bands.medium_minimum:
        band = PriorityBand.MEDIUM
    else:
        band = PriorityBand.LOW
    return PriorityScore(score=score, band=band, components=components)

