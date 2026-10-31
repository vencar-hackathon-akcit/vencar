from datetime import UTC, datetime

from support.builders import USER_A, USER_B, bodywork, conclude
from vencar.domain.models import (
    AgentEvent,
    Assessment,
    AssessmentStage,
    AssessmentStatus,
    EventKind,
    EventName,
    VehicleData,
)
from vencar.domain.progress import POLL_INTERVAL_MS, build_progress

NOW = datetime(2026, 10, 31, tzinfo=UTC)


def assessment(status: AssessmentStatus) -> Assessment:
    """Build an assessment in the given status."""
    return Assessment(
        id="a1",
        owner="o",
        vehicle=VehicleData(),
        description="",
        status=status,
        created_at=NOW,
        updated_at=NOW,
    )


def event(kind: EventKind, name: str) -> AgentEvent:
    """Build a stored history event."""
    return AgentEvent(run=1, kind=kind, name=name, created_at=NOW, hash="h")


def test_status_endpoint_returns_only_progress(harness) -> None:
    """A finished assessment reports its status without the dossier or history."""
    created = harness.submit([bodywork(), conclude()])
    response = harness.client.get(f"/api/v1/assessments/{created['id']}/status", headers=USER_A)
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "completed"
    assert body["stage"] == "finished"
    assert body["isFinished"] is True
    assert body["pollAfterMs"] is None
    assert body["lastAction"] == "dossier_issued"
    assert "dossier" not in body and "events" not in body


def test_status_endpoint_respects_ownership(harness) -> None:
    """Another user or an anonymous client cannot poll an assessment."""
    created = harness.submit([bodywork(), conclude()])
    url = f"/api/v1/assessments/{created['id']}/status"

    assert harness.client.get(url, headers=USER_B).status_code == 404
    assert harness.client.get(url).status_code == 401


def test_progress_follows_each_stage_of_a_run() -> None:
    """The stage changes as events arrive, and polling continues until the end."""
    processing = assessment(AssessmentStatus.PROCESSING)
    received = event(EventKind.STEP, EventName.RECEIVED)
    decision = event(EventKind.DECISION, EventName.ORCHESTRATOR)
    tool = event(EventKind.TOOL, "analyze_bodywork")
    validated = event(EventKind.STEP, EventName.VALIDATED)

    assert build_progress(processing, []).stage == AssessmentStage.RECEIVED
    assert build_progress(processing, [received]).stage == AssessmentStage.RECEIVED
    assert build_progress(processing, [received, decision]).stage == AssessmentStage.ANALYZING

    running = build_progress(processing, [received, decision, tool])
    assert running.last_action == "analyze_bodywork"
    assert running.is_finished is False
    assert running.poll_after_ms == POLL_INTERVAL_MS

    assert build_progress(processing, [received, validated]).stage == AssessmentStage.VALIDATING


def test_progress_ignores_the_previous_run_after_an_answer() -> None:
    """A rerun starts from the beginning instead of showing the old result."""
    processing = assessment(AssessmentStatus.PROCESSING)
    previous = event(EventKind.STEP, EventName.DOSSIER_ISSUED)
    answer = event(EventKind.USER_INPUT, EventName.USER_ANSWER)

    progress = build_progress(processing, [previous, answer])

    assert progress.stage == AssessmentStage.RECEIVED
    assert progress.last_action is None


def test_progress_reports_failures_as_finished() -> None:
    """A failed run stops polling and exposes its error."""
    failed = assessment(AssessmentStatus.FAILED).model_copy(update={"error": "falhou"})

    progress = build_progress(failed, [event(EventKind.STEP, EventName.FAILED)])

    assert progress.is_finished is True
    assert progress.error == "falhou"
