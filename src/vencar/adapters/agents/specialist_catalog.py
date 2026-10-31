from collections.abc import Callable
from dataclasses import dataclass

from langchain_core.language_models.chat_models import BaseChatModel

from vencar.adapters.agents.prompts import build_orchestrator_prompt, build_specialist_prompt
from vencar.adapters.agents.specialists import ChatSpecialist, Specialist
from vencar.domain.models import Category, SpecialistName


@dataclass(frozen=True)
class SpecialistDefinition:
    """Everything that defines a specialist agent, kept in one place."""

    name: SpecialistName
    tool_name: str
    tool_description: str
    orchestrator_guidance: str
    identity: str
    allowed_categories: frozenset[Category]


SPECIALISTS = (
    SpecialistDefinition(
        name=SpecialistName.BODYWORK,
        tool_name="analyze_bodywork",
        tool_description=(
            "Aciona o agente de funilaria para lataria, pintura e estrutura visivel nas fotos."
        ),
        orchestrator_guidance=(
            "aciona o agente de funilaria, para lataria, pintura e estrutura visivel."
        ),
        identity=(
            "Voce e o agente de funilaria da Vencar, especialista em lataria, pintura, "
            "para-choques, vidros, rodas e sinais visiveis de dano estrutural. "
            "Use somente as categorias aesthetic e structural."
        ),
        allowed_categories=frozenset({Category.AESTHETIC, Category.STRUCTURAL}),
    ),
    SpecialistDefinition(
        name=SpecialistName.INTERIOR,
        tool_name="analyze_interior",
        tool_description=(
            "Aciona o agente de tapecaria para bancos, estofamento e acabamento interno nas fotos."
        ),
        orchestrator_guidance=(
            "aciona o agente de tapecaria, para bancos, estofamento, forros e acabamento interno."
        ),
        identity=(
            "Voce e o agente de tapecaria da Vencar, especialista em bancos, estofamento, "
            "forros, carpetes e acabamento interno. Use somente a categoria aesthetic."
        ),
        allowed_categories=frozenset({Category.AESTHETIC}),
    ),
)

ORCHESTRATOR_PROMPT = build_orchestrator_prompt(
    [f"- {item.tool_name} {item.orchestrator_guidance}" for item in SPECIALISTS]
)


class SpecialistCatalog:
    """Create agents from the specialist definitions."""

    @staticmethod
    def create_specialists(
        model_factory: Callable[[], BaseChatModel],
    ) -> dict[SpecialistName, Specialist]:
        """Create one agent for each specialist in the catalog."""
        return {
            item.name: ChatSpecialist(
                item.name,
                model_factory(),
                build_specialist_prompt(item.identity),
                set(item.allowed_categories),
            )
            for item in SPECIALISTS
        }
