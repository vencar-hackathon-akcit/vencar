from typing import NamedTuple

from vencar.domain.models import (
    AgentConclusion,
    AgentRequest,
    AssessmentStatus,
    Category,
    Conflict,
    Damage,
    Dossier,
    Evidence,
    Hypothesis,
    PhotoAssessment,
    SpecialistReport,
)
from vencar.domain.scoring import calculate_score

DEFAULT_HUMAN_REASON = "Resultados gerados por IA precisam de validacao de um profissional."
NEW_PHOTO_QUESTION = "Envie novas fotos nitidas e bem iluminadas do veiculo."
CONFLICT_REASON = "Ha informacoes conflitantes que precisam ser esclarecidas."
NO_SPECIALIST_REASON = "Nenhum agente especialista foi acionado."
NO_EVIDENCE_REASON = "Nao ha evidencia suficiente para avaliar nenhuma categoria."


class Validated[T](NamedTuple):
    """Items that passed validation and the warnings about those that did not."""

    items: list[T]
    warnings: list[str]


def collect_evidence(request: AgentRequest) -> list[Evidence]:
    """List and identify every piece of evidence received."""
    evidence = [Evidence(id="E1", kind="description", content=request.description)]

    evidence += [
        Evidence(id=f"R{index}", kind="answer", content=answer)
        for index, answer in enumerate(request.answers, start=1)
    ]

    evidence += [
        Evidence(id=photo.evidence_id, kind="photo", content=photo.filename, photo_id=photo.id)
        for photo in request.photos
    ]

    return evidence


def find_missing_inputs(request: AgentRequest) -> list[str]:
    """Return the mandatory inputs that are absent before any model call."""
    missing = request.vehicle.missing_required()

    if not request.photos:
        missing.append("photos")

    return missing


def build_missing_data_dossier(request: AgentRequest, missing: list[str]) -> Dossier:
    """Ask for mandatory data without presuming anything about the vehicle."""
    return Dossier(
        status=AssessmentStatus.NEEDS_INPUT,
        status_reason="Faltam dados obrigatorios; os agentes nao foram acionados.",
        vehicle=request.vehicle,
        evidence=collect_evidence(request),
        pending_information=missing,
        questions=[f"Informe: {item}." for item in missing],
        recommendation="Complete os dados para iniciar a avaliacao.",
        human_validation_reason=DEFAULT_HUMAN_REASON,
    )


def merge_photo_assessments(
    reports: list[SpecialistReport], photo_ids: set[str]
) -> dict[str, PhotoAssessment]:
    """Merge verdicts per photo, considering a photo usable if any specialist could use it."""
    merged: dict[str, PhotoAssessment] = {}

    for report in reports:
        for item in report.findings.photo_assessments:
            if item.evidence_id not in photo_ids:
                continue

            current = merged.get(item.evidence_id)

            if current is None or (item.usable and not current.usable):
                merged[item.evidence_id] = item

    return merged


def validate_damages(
    reports: list[SpecialistReport], photo_ids: set[str], unusable: set[str]
) -> Validated[Damage]:
    """Keep only damages backed by a usable photo."""
    damages = []
    warnings = []

    for report in reports:
        for damage in report.findings.damages:
            if damage.evidence_id in photo_ids and damage.evidence_id not in unusable:
                damages.append(damage)
            else:
                warnings.append(f"Avaria descartada por nao ter foto valida: {damage.location}.")

    return Validated(damages, warnings)


def validate_hypotheses(
    reports: list[SpecialistReport], known: set[str], unusable: set[str]
) -> Validated[Hypothesis]:
    """Keep only hypotheses citing evidence that exists and is usable."""
    hypotheses = []
    warnings = []

    for report in reports:
        for hypothesis in report.findings.hypotheses:
            valid = [
                item for item in hypothesis.evidence_ids if item in known and item not in unusable
            ]

            if valid:
                hypotheses.append(hypothesis.model_copy(update={"evidence_ids": valid}))
            else:
                warnings.append(
                    f"Hipotese descartada por nao ter evidencia valida: {hypothesis.description}"
                )

    return Validated(hypotheses, warnings)


def find_evaluated_categories(
    reports: list[SpecialistReport], photo_ids: set[str]
) -> set[Category]:
    """Accept a specialist's categories only if it had at least one usable photo."""
    evaluated: set[Category] = set()

    for report in reports:
        assessed = report.findings.photo_assessments

        if any(item.usable for item in assessed if item.evidence_id in photo_ids):
            evaluated.update(report.findings.evaluated_categories)

    return evaluated


def all_photos_unusable(photo_ids: set[str], unusable: set[str]) -> bool:
    """Tell whether photos were received and none of them can be used."""
    return bool(photo_ids) and photo_ids <= unusable


def decide_status(
    reports: list[SpecialistReport],
    photo_ids: set[str],
    unusable: set[str],
    conflicts: list[Conflict],
    conclusion: AgentConclusion | None,
    evaluated: set[Category],
) -> tuple[AssessmentStatus, str]:
    """Decide the final status, checking the most blocking situations first."""
    if not reports:
        return AssessmentStatus.INCONCLUSIVE, NO_SPECIALIST_REASON

    if all_photos_unusable(photo_ids, unusable):
        return AssessmentStatus.NEEDS_INPUT, "Nenhuma foto recebida permite analise."

    if conflicts:
        return AssessmentStatus.NEEDS_INPUT, CONFLICT_REASON

    if conclusion and conclusion.needs_user_input and conclusion.questions:
        return AssessmentStatus.NEEDS_INPUT, "O agente precisa de mais informacoes para concluir."

    if not evaluated:
        return AssessmentStatus.INCONCLUSIVE, NO_EVIDENCE_REASON

    return AssessmentStatus.COMPLETED, "Avaliacao concluida, sujeita a validacao humana."


def build_questions(
    conclusion: AgentConclusion | None,
    photo_ids: set[str],
    unusable: set[str],
    conflicts: list[Conflict],
    has_reports: bool,
) -> list[str]:
    """Combine the agent's questions with those the rules require."""
    questions = list(conclusion.questions) if conclusion else []

    if not has_reports:
        return questions

    if all_photos_unusable(photo_ids, unusable):
        return [*questions, NEW_PHOTO_QUESTION]

    return [*questions, *(f"Esclareca o conflito: {item.description}" for item in conflicts)]


def human_validation_reason(conclusion: AgentConclusion | None) -> str:
    """Prefer the inspection reason given by the agent, when there is one."""
    if conclusion and conclusion.requires_in_person_inspection and conclusion.inspection_reason:
        return conclusion.inspection_reason

    return DEFAULT_HUMAN_REASON


def build_dossier(
    request: AgentRequest,
    reports: list[SpecialistReport],
    conclusion: AgentConclusion | None,
    warnings: list[str],
) -> Dossier:
    """Apply the deterministic rules that have the final word over the agents' output."""
    evidence = collect_evidence(request)
    known = {item.id for item in evidence}
    photo_ids = {photo.evidence_id for photo in request.photos}
    assessments = merge_photo_assessments(reports, photo_ids)
    unusable = {key for key, item in assessments.items() if not item.usable}

    damages = validate_damages(reports, photo_ids, unusable)
    hypotheses = validate_hypotheses(reports, known, unusable)
    conflicts = [conflict for report in reports for conflict in report.findings.conflicts]
    limitations = [item for report in reports for item in report.findings.limitations]
    evaluated = find_evaluated_categories(reports, photo_ids)

    status, reason = decide_status(reports, photo_ids, unusable, conflicts, conclusion, evaluated)
    no_specialist = [NO_SPECIALIST_REASON] if not reports else []

    return Dossier(
        status=status,
        status_reason=reason,
        vehicle=request.vehicle,
        evidence=evidence,
        photo_assessments=list(assessments.values()),
        damages=damages.items,
        hypotheses=hypotheses.items,
        conflicts=conflicts,
        questions=build_questions(conclusion, photo_ids, unusable, conflicts, bool(reports)),
        limitations=limitations,
        warnings=[*warnings, *damages.warnings, *hypotheses.warnings, *no_specialist],
        score=calculate_score(damages.items, evaluated),
        summary=conclusion.summary if conclusion else "",
        recommendation=conclusion.recommendation if conclusion else "",
        human_validation_reason=human_validation_reason(conclusion),
    )
