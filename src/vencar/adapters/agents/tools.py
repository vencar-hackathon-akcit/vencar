from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from vencar.adapters.agents.specialist_catalog import SPECIALISTS, SpecialistDefinition
from vencar.adapters.agents.specialists import Specialist
from vencar.application.ports import AssessmentRepository
from vencar.domain.errors import AgentFailureError
from vencar.domain.models import (
    AgentConclusion,
    AgentRequest,
    Assessment,
    SpecialistName,
    SpecialistReport,
)


class SpecialistArgs(BaseModel):
    """Arguments for calling a specialist agent."""

    photo_ids: list[str] = Field(description="Ids das evidencias de foto, como P1 e P2.")
    focus: str = Field(description="O que o especialista deve observar neste caso.")


class HistoryArgs(BaseModel):
    """The history lookup needs no arguments."""


class ConclusionArgs(BaseModel):
    """Final position of the orchestrator."""

    summary: str = Field(description="Resumo em linguagem simples, sem jargao.")
    recommendation: str = Field(description="Proxima etapa recomendada.")
    needs_user_input: bool
    questions: list[str] = Field(description="Perguntas objetivas ao usuario; vazia se nao houver.")
    requires_in_person_inspection: bool
    inspection_reason: str = Field(
        description="Motivo da inspecao presencial; vazio se nao houver."
    )


def summarize_previous_assessment(assessment: Assessment) -> dict:
    """Keep only what the orchestrator needs from an earlier assessment."""
    dossier = assessment.dossier

    return {
        "date": assessment.created_at.isoformat(),
        "status": assessment.status,
        "score": dossier.score.value if dossier and dossier.score else None,
        "damages": [item.model_dump(mode="json") for item in dossier.damages] if dossier else [],
    }


def build_specialist_tool(
    definition: SpecialistDefinition, request: AgentRequest, specialist: Specialist
) -> StructuredTool:
    """Expose a specialist agent as a tool the orchestrator can choose."""
    photos = {photo.evidence_id: photo for photo in request.photos}

    def call_specialist(photo_ids: list[str], focus: str) -> SpecialistReport:
        """Run the specialist on the selected photos."""
        unknown = [item for item in photo_ids if item not in photos]

        if unknown or not photo_ids:
            raise AgentFailureError(
                f"Fotos invalidas: {unknown or 'nenhuma informada'}. Disponiveis: {sorted(photos)}."
            )

        selected = [photos[item] for item in photo_ids]

        return specialist.inspect(request.vehicle, request.description, selected, focus)

    return StructuredTool.from_function(
        call_specialist,
        name=definition.tool_name,
        description=definition.tool_description,
        args_schema=SpecialistArgs,
    )


def build_history_tool(request: AgentRequest, repository: AssessmentRepository) -> StructuredTool:
    """Expose the earlier assessments of the same plate as a tool."""

    def get_vehicle_history() -> list[dict]:
        """Consulta as avaliacoes anteriores deste usuario para a mesma placa."""
        previous = repository.previous_dossiers(
            request.vehicle.plate, request.owner, request.assessment_id
        )

        return [summarize_previous_assessment(item) for item in previous]

    return StructuredTool.from_function(get_vehicle_history, args_schema=HistoryArgs)


def submit_conclusion(
    summary: str,
    recommendation: str,
    needs_user_input: bool,
    questions: list[str],
    requires_in_person_inspection: bool,
    inspection_reason: str,
) -> AgentConclusion:
    """Registra a posicao final do orquestrador e encerra a investigacao."""
    return AgentConclusion(
        summary=summary,
        recommendation=recommendation,
        needs_user_input=needs_user_input,
        questions=questions,
        requires_in_person_inspection=requires_in_person_inspection,
        inspection_reason=inspection_reason,
    )


def build_tools(
    request: AgentRequest,
    specialists: dict[SpecialistName, Specialist],
    repository: AssessmentRepository,
) -> list[StructuredTool]:
    """Create the tools the orchestrator can choose from for this case."""
    specialist_tools = [
        build_specialist_tool(definition, request, specialists[definition.name])
        for definition in SPECIALISTS
    ]

    return [
        *specialist_tools,
        build_history_tool(request, repository),
        StructuredTool.from_function(submit_conclusion, args_schema=ConclusionArgs),
    ]
