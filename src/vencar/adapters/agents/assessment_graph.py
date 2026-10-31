from collections.abc import Callable

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from vencar.adapters.agents.nodes import AssessmentNodes
from vencar.adapters.agents.routes import (
    route_after_intake,
    route_after_orchestrate,
    route_after_tools,
)
from vencar.adapters.agents.specialists import Specialist
from vencar.adapters.agents.state import RECURSION_LIMIT, AgentState, Node
from vencar.adapters.agents.tools import AssessmentTools
from vencar.application.ports import AssessmentRepository, EventSink
from vencar.domain.models import AgentRequest, Dossier, SpecialistName


class LangGraphAssessmentAgent:
    """Adapter that implements the agent port with LangGraph."""

    def __init__(
        self,
        model_factory: Callable[[], BaseChatModel],
        specialist_factory: Callable[[], dict[SpecialistName, Specialist]],
        repository: AssessmentRepository,
    ) -> None:
        """Keep factories so the API can start before model credentials are available."""
        self.model_factory = model_factory
        self.specialist_factory = specialist_factory
        self.repository = repository

    def run(self, request: AgentRequest, sink: EventSink) -> Dossier:
        """Run the graph for one assessment and return its dossier."""
        tools = AssessmentTools(request, self.specialist_factory(), self.repository).build()
        orchestrator = self.model_factory().bind_tools(tools, strict=True)
        graph = self.build_assessment_graph(AssessmentNodes(request, orchestrator, tools, sink))

        return graph.invoke({}, {"recursion_limit": RECURSION_LIMIT})["dossier"]

    @staticmethod
    def build_assessment_graph(nodes: AssessmentNodes) -> CompiledStateGraph:
        """Connect the steps: an orchestrator looping over its tools, then deterministic rules."""
        graph = StateGraph(AgentState)

        graph.add_node(Node.INTAKE, nodes.intake)
        graph.add_node(Node.REQUEST_MISSING_DATA, nodes.request_missing_data)
        graph.add_node(Node.PREPARE_CASE, nodes.prepare_case)
        graph.add_node(Node.ORCHESTRATE, nodes.orchestrate)
        graph.add_node(Node.RUN_TOOLS, nodes.run_tools)
        graph.add_node(Node.NUDGE, nodes.nudge)
        graph.add_node(Node.CONSOLIDATE, nodes.consolidate)

        graph.add_edge(START, Node.INTAKE)
        graph.add_edge(Node.REQUEST_MISSING_DATA, END)
        graph.add_edge(Node.PREPARE_CASE, Node.ORCHESTRATE)
        graph.add_edge(Node.NUDGE, Node.ORCHESTRATE)
        graph.add_edge(Node.CONSOLIDATE, END)

        graph.add_conditional_edges(
            Node.INTAKE, route_after_intake, [Node.REQUEST_MISSING_DATA, Node.PREPARE_CASE]
        )

        graph.add_conditional_edges(
            Node.ORCHESTRATE,
            route_after_orchestrate,
            [Node.RUN_TOOLS, Node.NUDGE, Node.CONSOLIDATE],
        )

        graph.add_conditional_edges(
            Node.RUN_TOOLS, route_after_tools, [Node.ORCHESTRATE, Node.CONSOLIDATE]
        )

        return graph.compile()
