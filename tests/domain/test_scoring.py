from support.builders import findings
from vencar.domain.models import Category, SpecialistFindings
from vencar.domain.scoring import calculate_score


def test_low_confidence_damage_does_not_reduce_the_score() -> None:
    """Scoring ignores findings the agent is not sure about."""
    damage = SpecialistFindings(**findings()).damages[0].model_copy(update={"confidence": "low"})
    score = calculate_score([damage], {Category.AESTHETIC})
    assert score.value == 100
