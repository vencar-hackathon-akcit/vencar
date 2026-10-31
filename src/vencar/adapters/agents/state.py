from enum import StrEnum
from operator import add
from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages

from vencar.domain.models import AgentConclusion, Dossier, SpecialistReport

MAX_ORCHESTRATOR_TURNS = 8
MAX_NUDGES = 1
MAX_TOOL_WORKERS = 4
RECURSION_LIMIT = 3 * MAX_ORCHESTRATOR_TURNS + 10


class Node(StrEnum):
    """Names of the graph nodes."""

    INTAKE = "intake"
    REQUEST_MISSING_DATA = "request_missing_data"
    PREPARE_CASE = "prepare_case"
    ORCHESTRATE = "orchestrate"
    RUN_TOOLS = "run_tools"
    NUDGE = "nudge"
    CONSOLIDATE = "consolidate"


class AgentState(TypedDict, total=False):
    """State shared by the graph nodes during one run."""

    missing: list[str]
    messages: Annotated[list, add_messages]
    reports: Annotated[list[SpecialistReport], add]
    warnings: Annotated[list[str], add]
    conclusion: AgentConclusion | None
    turns: int
    nudges: int
    dossier: Dossier
