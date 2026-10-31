from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from vencar.adapters.agents.specialist_catalog import SPECIALISTS, SpecialistDefinition
from vencar.adapters.agents.specialists import Specialist
from vencar.application.ports import AssessmentRepository
from vencar.domain.errors import ErrorCode, VencarError
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


class AssessmentTools:
    """Tools the orchestrator can choose from for one assessment."""

    def __init__(
        self,
        request: AgentRequest,
        specialists: dict[SpecialistName, Specialist],
        repository: AssessmentRepository,
    ) -> None:
        """Receive what the tools need for this case."""
        self.request = request
        self.specialists = specialists
        self.repository = repository

    @staticmethod
    def summarize_previous_assessment(assessment: Assessment) -> dict:
        """Keep only what the orchestrator needs from an earlier assessment."""
        dossier = assessment.dossier

        return {
            "date": assessment.created_at.isoformat(),
            "status": assessment.status,
            "score": dossier.score.value if dossier and dossier.score else None,
            "damages": [item.model_dump(mode="json") for item in dossier.damages]
            if dossier
            else [],
        }

    def build_specialist_tool(self, definition: SpecialistDefinition) -> StructuredTool:
        """Expose a specialist agent as a tool the orchestrator can choose."""
        photos = {photo.evidence_id: photo for photo in self.request.photos}
        specialist = self.specialists[definition.name]

        def call_specialist(photo_ids: list[str], focus: str) -> SpecialistReport:
            """Run the specialist on the selected photos."""
            unknown = [item for item in photo_ids if item not in photos]

            if unknown or not photo_ids:
                invalid = unknown or "nenhuma informada"
                message = f"Fotos invalidas: {invalid}. Disponiveis: {sorted(photos)}."

                raise VencarError(ErrorCode.AGENT_FAILURE, message)

            selected = [photos[item] for item in photo_ids]

            return specialist.inspect(
                self.request.vehicle, self.request.description, selected, focus
            )

        return StructuredTool.from_function(
            call_specialist,
            name=definition.tool_name,
            description=definition.tool_description,
            args_schema=SpecialistArgs,
        )

    def get_vehicle_history(self) -> list[dict]:
        """Consulta as avaliacoes anteriores deste usuario para a mesma placa."""
        previous = self.repository.previous_dossiers(
            self.request.vehicle.plate, self.request.owner, self.request.assessment_id
        )

        return [self.summarize_previous_assessment(item) for item in previous]

    @staticmethod
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

    def build(self) -> list[StructuredTool]:
        """Create every tool available to the orchestrator."""
        return [
            *(self.build_specialist_tool(definition) for definition in SPECIALISTS),
            StructuredTool.from_function(self.get_vehicle_history, args_schema=HistoryArgs),
            StructuredTool.from_function(self.submit_conclusion, args_schema=ConclusionArgs),
        ]
