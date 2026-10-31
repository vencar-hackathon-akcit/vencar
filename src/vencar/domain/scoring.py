from vencar.domain.models import (
    Category,
    CategoryScore,
    Confidence,
    Damage,
    ScoreBand,
    Severity,
    VehicleScore,
)

CATEGORY_WEIGHTS = {
    Category.STRUCTURAL: 30,
    Category.MECHANICAL: 30,
    Category.ELECTRICAL: 10,
    Category.AESTHETIC: 15,
    Category.DOCUMENTATION: 15,
}
ATTENTION_MAX_SCORE = 40
REGULAR_MAX_SCORE = 70
MAX_GRADE = 10.0
MAX_SCORE_PER_GRADE_POINT = 10
FULL_COVERAGE_PERCENT = 100
WORST_SEVERITY_GRADE = {Severity.MINOR: 8.5, Severity.MODERATE: 6.0, Severity.SEVERE: 3.0}
EXTRA_DAMAGE_PENALTY = 0.25
MAX_EXTRA_PENALTY = 1.0
SCORE_IS_PROVISIONAL = True
NOT_EVALUATED_REASON = "Sem evidencia suficiente para avaliar esta categoria."


def band_for(value: int) -> ScoreBand:
    """Map a 0-100 value to its band on the Vencar scale."""
    if value <= ATTENTION_MAX_SCORE:
        return ScoreBand.ATTENTION

    if value <= REGULAR_MAX_SCORE:
        return ScoreBand.REGULAR

    return ScoreBand.VERY_GOOD


def grade_category(category: Category, damages: list[Damage]) -> float:
    """Grade a category by its worst damage, so the number of items listed matters little."""
    severities = [
        item.severity
        for item in damages
        if item.category == category and item.confidence != Confidence.LOW
    ]

    if not severities:
        return MAX_GRADE

    worst = min(WORST_SEVERITY_GRADE[item] for item in severities)
    extra_penalty = min(EXTRA_DAMAGE_PENALTY * (len(severities) - 1), MAX_EXTRA_PENALTY)

    return max(0.0, worst - extra_penalty)


def calculate_score(damages: list[Damage], evaluated: set[Category]) -> VehicleScore | None:
    """Calculate the weighted score using only categories backed by evidence."""
    if not evaluated:
        return None

    categories = []
    weighted_total = 0.0
    evaluated_weight = 0

    for category, weight in CATEGORY_WEIGHTS.items():
        if category not in evaluated:
            categories.append(
                CategoryScore(
                    category=category, evaluated=False, grade=None, reason=NOT_EVALUATED_REASON
                )
            )

            continue

        grade = grade_category(category, damages)

        categories.append(
            CategoryScore(
                category=category,
                evaluated=True,
                grade=grade,
                reason="Calculada a partir das avarias validadas.",
            )
        )

        weighted_total += grade * weight
        evaluated_weight += weight

    value = round(weighted_total / evaluated_weight * MAX_SCORE_PER_GRADE_POINT)
    coverage = round(evaluated_weight / sum(CATEGORY_WEIGHTS.values()) * FULL_COVERAGE_PERCENT)

    return VehicleScore(
        value=value,
        band=band_for(value),
        is_partial=coverage < FULL_COVERAGE_PERCENT,
        is_provisional=SCORE_IS_PROVISIONAL,
        coverage_percent=coverage,
        categories=categories,
    )
