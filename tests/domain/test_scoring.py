from support.builders import findings
from vencar.domain.models import Category, SpecialistFindings, VehicleScore
from vencar.domain.scoring import calculate_score


def test_low_confidence_damage_does_not_reduce_the_score() -> None:
    """Scoring ignores findings the agent is not sure about."""
    damage = SpecialistFindings(**findings()).damages[0].model_copy(update={"confidence": "low"})
    score = calculate_score([damage], {Category.AESTHETIC})
    assert score.value == 100


def test_number_of_listed_damages_barely_changes_the_score() -> None:
    """Listing 2 or 5 severe damages changes the score by a small, capped amount."""
    damage = SpecialistFindings(**findings()).damages[0].model_copy(update={"severity": "severe"})

    two = calculate_score([damage] * 2, {Category.AESTHETIC}).value
    five = calculate_score([damage] * 5, {Category.AESTHETIC}).value

    assert two - five <= 10
    assert five == 20


def test_score_is_marked_provisional() -> None:
    """The scale stays marked until an automotive expert validates it."""
    assert calculate_score([], {Category.AESTHETIC}).is_provisional is True


def test_scores_saved_before_the_provisional_flag_still_load() -> None:
    """Older stored scores remain readable and count as provisional."""
    stored = {
        "value": 50,
        "band": "regular",
        "is_partial": True,
        "coverage_percent": 15,
        "categories": [],
    }

    assert VehicleScore(**stored).is_provisional is True
