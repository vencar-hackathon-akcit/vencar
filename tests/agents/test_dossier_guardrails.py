import pytest
from langchain_core.messages import AIMessage
from pydantic import ValidationError

from support.builders import bodywork, call, conclude, findings, photo
from vencar.domain.models import PhotoAssessment, SpecialistFindings

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
        photo_assessments=[
            {"evidence_id": "P1", "usable": False, "reason": "desfocada", "shows_car": True}
        ]
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
        photo_assessments=[
            {"evidence_id": "P1", "usable": False, "reason": "escura", "shows_car": True}
        ],
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


def test_question_without_specialists_waits_for_the_user(harness) -> None:
    """Asking for a correct photo keeps the case open instead of inconclusive."""
    result = harness.submit([conclude(needs_user_input=True, questions=["Envie outra foto."])])

    assert result["status"] == "needs_input"
    assert result["dossier"]["questions"] == ["Envie outra foto."]


def test_follow_up_questions_do_not_block_completion(harness) -> None:
    """Useful but unnecessary questions become optional pending information."""
    result = harness.submit([bodywork(), conclude(follow_up_questions=["Houve airbag?"])])

    assert result["status"] == "completed"
    assert result["dossier"]["questions"] == []
    assert result["dossier"]["pendingInformation"] == ["Houve airbag?"]


def test_conflict_replaces_the_agents_own_question(harness) -> None:
    """The user is asked about a conflict once, and other questions become optional."""
    harness.bodywork.findings = findings(vehicle_match=MISMATCH)
    conclusion = conclude(needs_user_input=True, questions=["O modelo esta correto?"])

    dossier = harness.submit([bodywork(), conclusion])["dossier"]

    assert dossier["questions"] == ["Esclareca o conflito: Painel de outra epoca"]
    assert dossier["pendingInformation"] == ["O modelo esta correto?"]


def test_score_only_appears_on_completed_assessments(harness) -> None:
    """No number is shown while the vehicle's identity is in doubt."""
    harness.bodywork.findings = findings(vehicle_match=MISMATCH)

    assert harness.submit([bodywork(), conclude()])["dossier"]["score"] is None


def test_identity_conflict_is_not_repeated(harness) -> None:
    """An identity conflict from a specialist does not duplicate the mismatch."""
    repeated = {"topic": "vehicle_identity", "description": "Outro carro", "evidence_ids": ["P1"]}
    harness.bodywork.findings = findings(vehicle_match=MISMATCH, conflicts=[repeated])

    dossier = harness.submit([bodywork(), conclude()])["dossier"]

    assert [item["description"] for item in dossier["conflicts"]] == ["Painel de outra epoca"]


NOT_A_CAR = {"evidence_id": "P1", "usable": True, "reason": "E uma moto", "shows_car": False}


def test_photo_without_a_car_is_rejected(harness) -> None:
    """A non-car photo gets no findings, conflict or score, even if marked usable."""
    harness.bodywork.findings = findings(photo_assessments=[NOT_A_CAR], vehicle_match=MISMATCH)

    result = harness.submit([bodywork(), conclude()])
    dossier = result["dossier"]

    assert result["status"] == "needs_input"
    assert dossier["questions"] == [
        "A Vencar avalia somente carros. Envie fotos do carro a ser avaliado."
    ]
    assert dossier["damages"] == [] and dossier["hypotheses"] == []
    assert dossier["conflicts"] == [] and dossier["score"] is None


def test_non_car_photo_is_ignored_when_another_photo_shows_a_car(harness) -> None:
    """Only the non-car photo is dropped from a mixed submission."""
    damage = findings()["damages"][0]
    other = {"evidence_id": "P2", "usable": True, "reason": "E um carro", "shows_car": True}
    harness.bodywork.findings = findings(
        photo_assessments=[NOT_A_CAR, other],
        damages=[damage, {**damage, "evidence_id": "P2", "location": "porta"}],
        hypotheses=[],
    )

    turn = AIMessage(
        content="",
        tool_calls=[call("analyze_bodywork", {"photo_ids": ["P1", "P2"], "focus": "a"})],
    )

    result = harness.submit([turn, conclude()], files=[photo(), photo()])
    dossier = result["dossier"]

    assert result["status"] == "completed"
    assert [item["evidenceId"] for item in dossier["damages"]] == ["P2"]
    assert "Foto P1 ignorada por nao mostrar um carro." in dossier["warnings"]


def test_specialists_must_answer_the_car_check() -> None:
    """The model cannot skip the car check, and older saved verdicts still load."""
    missing = {"evidence_id": "P1", "usable": True, "reason": "ok"}

    with pytest.raises(ValidationError):
        SpecialistFindings(**findings(photo_assessments=[missing]))

    assert PhotoAssessment(**missing).shows_car is True
