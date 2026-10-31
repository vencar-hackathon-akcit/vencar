from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import ChatGeneration, ChatResult

from vencar.domain.models import SpecialistFindings, SpecialistReport


class ScriptedChatModel(BaseChatModel):
    """Chat model that replays scripted orchestrator turns and records what it received."""

    script: list
    received: list

    @property
    def _llm_type(self) -> str:
        """Identify this fake model."""
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        """Accept the tools without changing behavior."""
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        """Return the next scripted message."""
        self.received.append(list(messages))

        return ChatResult(generations=[ChatGeneration(message=self.script.pop(0))])


class FakeSpecialist:
    """Specialist with canned findings that records its calls."""

    def __init__(self, name: str, findings: dict) -> None:
        """Store the canned findings."""
        self.name = name
        self.findings = findings
        self.calls = []

    def inspect(self, vehicle, description, answers, photos, focus) -> SpecialistReport:
        """Record the call and return the findings."""
        self.calls.append([photo.evidence_id for photo in photos])
        self.answers = answers

        return SpecialistReport(specialist=self.name, findings=SpecialistFindings(**self.findings))
