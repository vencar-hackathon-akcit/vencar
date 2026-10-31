from langchain_core.messages import AIMessage

from support.builders import USER_A, bodywork, call, conclude


def test_agent_chooses_specialist_and_builds_dossier_with_partial_score(harness) -> None:
    """The orchestrator's choices drive the run, and code calculates a partial score."""
    result = harness.submit([bodywork(), conclude()])
    dossier = result["dossier"]
    assert result["status"] == "completed"
    assert harness.bodywork.calls == [["P1"]] and harness.interior.calls == []
    assert dossier["score"]["value"] == 60 and dossier["score"]["band"] == "regular"
    assert dossier["score"]["isPartial"] is True and dossier["score"]["coveragePercent"] == 15
    graded = {item["category"]: item["evaluated"] for item in dossier["score"]["categories"]}
    assert graded["aesthetic"] is True and graded["mechanical"] is False
    assert dossier["requiresHumanValidation"] is True
    assert result["vehicle"]["plate"] == "ABC1D23"


def test_agent_can_call_specialists_in_parallel_and_use_history(harness) -> None:
    """The orchestrator may call several tools in one turn and see earlier assessments."""
    harness.submit([bodywork(), conclude()])

    turn = AIMessage(
        content="",
        tool_calls=[
            call("analyze_bodywork", {"photo_ids": ["P1"], "focus": "a"}, "c1"),
            call("analyze_interior", {"photo_ids": ["P1"], "focus": "b"}, "c2"),
            call("get_vehicle_history", {}, "c3"),
        ],
    )

    result = harness.submit([turn, conclude()])
    history = next(event for event in result["events"] if event["name"] == "get_vehicle_history")
    assert history["output"][0]["score"] == 60
    assert harness.interior.calls == [["P1"]]


def test_tool_error_returns_to_the_agent_so_it_can_recover(harness) -> None:
    """A wrong photo id reaches the orchestrator as an error it can correct."""
    wrong = AIMessage(
        content="", tool_calls=[call("analyze_bodywork", {"photo_ids": ["P9"], "focus": "x"})]
    )

    result = harness.submit([wrong, bodywork(), conclude()])
    assert result["status"] == "completed"
    assert any("P9" in warning for warning in result["dossier"]["warnings"])
    tool_messages = harness.model.received[1][-1]
    assert tool_messages.status == "error"


def test_agent_can_ask_the_user_and_resume_with_the_answer(harness) -> None:
    """The agent's question and the user's answer become a new run with more evidence."""
    first = harness.submit(
        [bodywork(), conclude(needs_user_input=True, questions=["Houve colisao?"])]
    )

    assert first["status"] == "needs_input" and first["dossier"]["questions"] == ["Houve colisao?"]
    harness.model.script[:] = [bodywork(), conclude()]

    response = harness.client.post(
        f"/api/v1/assessments/{first['id']}/answers", data={"answer": "Nao houve"}, headers=USER_A
    )

    assert response.status_code == 202
    second = harness.client.get(f"/api/v1/assessments/{first['id']}", headers=USER_A).json()
    assert second["status"] == "completed"
    assert [item["id"] for item in second["dossier"]["evidence"]] == ["E1", "R1", "P1"]
    assert "Nao houve" in harness.model.received[-1][1].content[-1]["text"]
    assert harness.bodywork.answers == ["Nao houve"]


def test_orchestrator_skipping_specialists_cannot_produce_a_score(harness) -> None:
    """Concluding without evidence is inconclusive, whatever the model claims."""
    result = harness.submit([conclude()])
    assert result["status"] == "inconclusive" and result["dossier"]["score"] is None


def test_orchestrator_is_nudged_then_stopped(harness) -> None:
    """An orchestrator that never concludes cannot loop forever."""
    result = harness.submit([AIMessage(content="Pensando"), AIMessage(content="Ainda pensando")])
    assert result["status"] == "inconclusive"
    assert any("sem registrar" in warning for warning in result["dossier"]["warnings"])


def test_turn_limit_stops_the_agent_loop(harness) -> None:
    """Repeated tool use ends at the turn limit with the evidence gathered so far."""
    result = harness.submit([bodywork() for _ in range(8)])
    assert result["status"] == "completed"
    assert len(harness.model.received) == 8


def test_agent_failure_is_recorded(harness) -> None:
    """A model failure leaves the assessment failed with the reason in its history."""
    harness.model.script[:] = []
    result = harness.submit([])
    assert result["status"] == "failed" and result["error"]
    assert result["events"][-1]["name"] == "failed"
