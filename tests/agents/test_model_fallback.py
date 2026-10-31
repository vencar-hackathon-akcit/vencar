from langchain_core.runnables import RunnableLambda

from support.builders import conclude
from support.fakes import ScriptedChatModel
from vencar.adapters.agents.assessment_graph import LangGraphAssessmentAgent
from vencar.adapters.agents.specialists import ChatSpecialist
from vencar.config import ModelProvider, Settings
from vencar.domain.models import (
    AgentRequest,
    Category,
    Photo,
    SpecialistFindings,
    SpecialistName,
    VehicleData,
)


class StructuredFake:
    """Model stand-in whose structured output is a given function."""

    def __init__(self, respond) -> None:
        """Keep the function that produces the model's answer."""
        self.respond = respond

    def with_structured_output(self, schema, method) -> RunnableLambda:
        """Return a runnable that calls the function."""
        return RunnableLambda(self.respond)


def fail(messages) -> None:
    """Simulate an overloaded model."""
    raise RuntimeError("503 UNAVAILABLE")


def test_orchestrator_uses_the_fallback_when_the_main_model_fails(tmp_path) -> None:
    """A failing main model does not stop the run when a fallback answers."""
    image = tmp_path / "a.jpg"
    image.write_bytes(b"jpeg")
    photo = Photo(id="1", evidence_id="P1", filename="a.jpg", path=str(image))
    vehicle = VehicleData(make="Fiat", model="Uno", year="2015", plate="ABC1D23")
    fallback = ScriptedChatModel(script=[conclude()], received=[])

    agent = LangGraphAssessmentAgent(
        lambda: ScriptedChatModel(script=[], received=[]),
        lambda: dict.fromkeys(SpecialistName),
        None,
        {},
        lambda: fallback,
    )

    request = AgentRequest(
        assessment_id="a",
        owner="o",
        vehicle=vehicle,
        description="x",
        answers=[],
        photos=[photo],
    )

    dossier = agent.run(request, lambda event: None)

    assert dossier.summary == "Resumo"
    assert len(fallback.received) == 1


def test_specialist_uses_the_fallback_when_the_main_model_fails() -> None:
    """A specialist answers through the fallback when the main model fails."""
    findings = SpecialistFindings(
        vehicle_match={"status": "matches", "reason": "ok", "evidence_ids": []},
        photo_assessments=[],
        damages=[],
        hypotheses=[],
        conflicts=[],
        evaluated_categories=[],
        limitations=["Veio do modelo reserva"],
    )

    specialist = ChatSpecialist(
        SpecialistName.BODYWORK,
        StructuredFake(fail),
        "prompt",
        {Category.AESTHETIC},
        StructuredFake(lambda messages: findings),
    )

    report = specialist.inspect(VehicleData(), "x", [], [], "foco")

    assert report.findings.limitations == ["Veio do modelo reserva"]


def test_each_provider_has_the_expected_fallback() -> None:
    """Gemini has a reserve model, while Claude relies on its server-side fallback."""
    google = Settings(_env_file=None, vencar_provider=ModelProvider.GOOGLE)
    anthropic = Settings(_env_file=None, vencar_provider=ModelProvider.ANTHROPIC)

    assert google.fallback_model_name() == "gemini-3.1-flash-lite"
    assert anthropic.fallback_model_name() == ""
