from langchain_core.messages import AIMessage

from support.builders import bodywork, call, conclude, findings

MISMATCH = {"status": "mismatch", "reason": "Painel de outra epoca", "evidence_ids": ["P1"]}


def test_missing_data_never_calls_any_agent(harness) -> None:
    """Without the vehicle's data and photos, the agents are not used."""
    result = harness.submit([], data={"description": "x"}, files=[])
    assert result["status"] == "needs_input"
    assert result["dossier"]["pendingInformation"] == ["make", "model", "year", "plate", "photos"]
    assert harness.model.received == []


def test_unusable_photo_discards_findings_and_requests_a_new_one(harness) -> None:
    """Findings tied only to a bad photo do not survive validation."""
    harness.bodywork.findings = findings(
        photo_assessments=[{"evidence_id": "P1", "usable": False, "reason": "desfocada"}]
    )

    result = harness.submit([bodywork(), conclude()])
    dossier = result["dossier"]
    assert result["status"] == "needs_input"
    assert dossier["damages"] == [] and dossier["score"] is None
    assert any("novas fotos" in question for question in dossier["questions"])


def test_conflict_is_surfaced_to_the_user(harness) -> None:
    """A conflict stops the conclusion instead of being silently resolved."""
    harness.bodywork.findings = findings(
        conflicts=[{"description": "Foto mostra um Onix", "evidence_ids": ["P1"]}]
    )

    result = harness.submit([bodywork(), conclude()])
    assert result["status"] == "needs_input"
    assert any("Onix" in question for question in result["dossier"]["questions"])


def test_vehicle_mismatch_blocks_completion_and_is_asked_once(harness) -> None:
    """Two specialists reporting a mismatch produce one conflict and one question."""
    harness.bodywork.findings = findings(vehicle_match=MISMATCH)
    harness.interior.findings = findings(vehicle_match=MISMATCH)

    turn = AIMessage(
        content="",
        tool_calls=[
            call("analyze_bodywork", {"photo_ids": ["P1"], "focus": "a"}, "c1"),
            call("analyze_interior", {"photo_ids": ["P1"], "focus": "b"}, "c2"),
        ],
    )

    result = harness.submit([turn, conclude()])
    dossier = result["dossier"]

    assert result["status"] == "needs_input"
    assert len(dossier["conflicts"]) == 1
    assert [item for item in dossier["questions"] if "outra epoca" in item] == [
        "Esclareca o conflito: Painel de outra epoca"
    ]


def test_vehicle_mismatch_needs_a_usable_photo(harness) -> None:
    """A mismatch based only on an unusable photo does not count as a conflict."""
    harness.bodywork.findings = findings(
        vehicle_match=MISMATCH,
        photo_assessments=[{"evidence_id": "P1", "usable": False, "reason": "escura"}],
    )

    result = harness.submit([bodywork(), conclude()])

    assert result["dossier"]["conflicts"] == []


def test_unknown_vehicle_match_does_not_block_completion(harness) -> None:
    """Being unable to compare is not a conflict."""
    harness.bodywork.findings = findings(
        vehicle_match={"status": "cannot_determine", "reason": "Pouco visivel", "evidence_ids": []}
    )

    result = harness.submit([bodywork(), conclude()])

    assert result["status"] == "completed"
