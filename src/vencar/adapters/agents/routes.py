from vencar.adapters.agents.state import MAX_NUDGES, MAX_ORCHESTRATOR_TURNS, AgentState, Node


def route_after_intake(state: AgentState) -> Node:
    """Skip the agents when mandatory data is missing."""
    return Node.REQUEST_MISSING_DATA if state["missing"] else Node.PREPARE_CASE


def route_after_orchestrate(state: AgentState) -> Node:
    """Follow the orchestrator's decision."""
    if state["messages"][-1].tool_calls:
        return Node.RUN_TOOLS

    if state["nudges"] < MAX_NUDGES and state["turns"] < MAX_ORCHESTRATOR_TURNS:
        return Node.NUDGE

    return Node.CONSOLIDATE


def route_after_tools(state: AgentState) -> Node:
    """Finish once the agent concluded or used all of its turns."""
    if state.get("conclusion") is not None or state["turns"] >= MAX_ORCHESTRATOR_TURNS:
        return Node.CONSOLIDATE

    return Node.ORCHESTRATE
