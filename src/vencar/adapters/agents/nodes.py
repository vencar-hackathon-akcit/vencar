import json
from concurrent.futures import ThreadPoolExecutor
from typing import NamedTuple

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from vencar.adapters.agents.specialist_catalog import ORCHESTRATOR_PROMPT
from vencar.adapters.agents.specialists import build_case_content
from vencar.adapters.agents.state import MAX_TOOL_WORKERS, AgentState
from vencar.application.ports import EventSink
from vencar.domain.dossier_rules import (
    build_dossier,
    build_missing_data_dossier,
    collect_evidence,
    find_missing_inputs,
)
from vencar.domain.models import (
    AgentConclusion,
    AgentRequest,
    EventKind,
    EventName,
    NewEvent,
    SpecialistReport,
)

NUDGE_MESSAGE = "Termine chamando a ferramenta submit_conclusion."
NO_CONCLUSION_WARNING = "O orquestrador encerrou sem registrar uma conclusao."


class ToolOutcome(NamedTuple):
    """Result of one tool call, or the error it produced."""

    call: dict
    result: object | None
    error: str | None


def describe_turn(message: AIMessage) -> str:
    """Extract the reasoning the model chose to show from one of its turns."""
    if isinstance(message.content, str):
        return message.content

    parts = [
        block.get("text") or block.get("thinking") or ""
        for block in message.content
        if isinstance(block, dict) and block.get("type") in ("text", "thinking")
    ]

    return "\n".join(part for part in parts if part)


def to_serializable(result: object) -> object:
    """Turn a tool result into plain data for the model and the history."""
    return result.model_dump(mode="json") if isinstance(result, BaseModel) else result


def to_tool_message(outcome: ToolOutcome) -> ToolMessage:
    """Tell the orchestrator how a tool call ended, including failures."""
    call_id = outcome.call["id"]

    if outcome.error:
        return ToolMessage(content=f"Erro: {outcome.error}", tool_call_id=call_id, status="error")

    content = json.dumps(to_serializable(outcome.result), ensure_ascii=False)

    return ToolMessage(content=content, tool_call_id=call_id)


class AssessmentNodes:
    """Steps of the agent graph for one assessment run."""

    def __init__(
        self,
        request: AgentRequest,
        orchestrator: Runnable,
        tools: list[StructuredTool],
        sink: EventSink,
    ) -> None:
        """Receive what the steps need during the run."""
        self.request = request
        self.orchestrator = orchestrator
        self.tools = {tool.name: tool for tool in tools}
        self.sink = sink

    def intake(self, state: AgentState) -> AgentState:
        """Register the evidence and detect missing mandatory inputs."""
        missing = find_missing_inputs(self.request)
        evidence_ids = [item.id for item in collect_evidence(self.request)]

        self.sink(
            NewEvent(
                kind=EventKind.STEP,
                name=EventName.RECEIVED,
                input={"vehicle": self.request.vehicle.model_dump()},
                output={"evidence": evidence_ids, "missing": missing},
            )
        )

        return {"missing": missing}

    def request_missing_data(self, state: AgentState) -> AgentState:
        """Ask for what is missing without calling any model."""
        self.sink(
            NewEvent(
                kind=EventKind.STEP,
                name=EventName.MISSING_DATA_REQUESTED,
                output={"missing": state["missing"]},
            )
        )

        return {"dossier": build_missing_data_dossier(self.request, state["missing"])}

    def prepare_case(self, state: AgentState) -> AgentState:
        """Give the orchestrator the case: photos, description and answers."""
        answers = enumerate(self.request.answers, start=1)

        case = {
            "vehicle": self.request.vehicle.model_dump(),
            "E1_description": self.request.description,
            "answers": {f"R{index}": answer for index, answer in answers},
            "photo_ids": [photo.evidence_id for photo in self.request.photos],
        }

        content = build_case_content(self.request.photos, case)

        return {
            "messages": [SystemMessage(content=ORCHESTRATOR_PROMPT), HumanMessage(content=content)],
            "turns": 0,
            "nudges": 0,
            "conclusion": None,
        }

    def orchestrate(self, state: AgentState) -> AgentState:
        """Let the orchestrator decide its next action."""
        message = self.orchestrator.invoke(state["messages"])

        self.sink(
            NewEvent(
                kind=EventKind.DECISION,
                name=EventName.ORCHESTRATOR,
                output={
                    "reasoning": describe_turn(message),
                    "tools": [call["name"] for call in message.tool_calls],
                },
            )
        )

        return {"messages": [message], "turns": state["turns"] + 1}

    def execute_tool(self, call: dict) -> ToolOutcome:
        """Run one tool call, returning failures as data so the agent can react to them."""
        try:
            return ToolOutcome(call, self.tools[call["name"]].invoke(call["args"]), None)
        except Exception as error:
            return ToolOutcome(call, None, str(error))

    def record_tool_call(self, outcome: ToolOutcome) -> None:
        """Add a tool call, with its parameters and result, to the history."""
        output = {"error": outcome.error} if outcome.error else to_serializable(outcome.result)

        self.sink(
            NewEvent(
                kind=EventKind.TOOL,
                name=outcome.call["name"],
                input=outcome.call["args"],
                output=output,
            )
        )

    def run_tools(self, state: AgentState) -> AgentState:
        """Execute the tools chosen by the orchestrator, specialists in parallel."""
        calls = state["messages"][-1].tool_calls

        with ThreadPoolExecutor(max_workers=MAX_TOOL_WORKERS) as pool:
            outcomes = list(pool.map(self.execute_tool, calls))

        for outcome in outcomes:
            self.record_tool_call(outcome)

        results = [item.result for item in outcomes]
        conclusions = [item for item in results if isinstance(item, AgentConclusion)]

        return {
            "messages": [to_tool_message(item) for item in outcomes],
            "reports": [item for item in results if isinstance(item, SpecialistReport)],
            "warnings": [
                f"Falha em {item.call['name']}: {item.error}" for item in outcomes if item.error
            ],
            "conclusion": conclusions[-1] if conclusions else state.get("conclusion"),
        }

    def nudge(self, state: AgentState) -> AgentState:
        """Remind the orchestrator once that it must conclude through the tool."""
        return {"messages": [HumanMessage(content=NUDGE_MESSAGE)], "nudges": state["nudges"] + 1}

    def consolidate(self, state: AgentState) -> AgentState:
        """Apply the deterministic rules and calculate the score."""
        conclusion = state.get("conclusion")
        warnings = state.get("warnings", [])

        if conclusion is None:
            warnings = [*warnings, NO_CONCLUSION_WARNING]

        dossier = build_dossier(self.request, state.get("reports", []), conclusion, warnings)

        self.sink(
            NewEvent(
                kind=EventKind.STEP,
                name=EventName.VALIDATED,
                output={
                    "status": dossier.status,
                    "warnings": dossier.warnings,
                    "score": dossier.score.value if dossier.score else None,
                },
            )
        )

        return {"dossier": dossier}
