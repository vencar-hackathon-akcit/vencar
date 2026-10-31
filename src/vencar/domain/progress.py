from vencar.domain.models import (
    AgentEvent,
    Assessment,
    AssessmentProgress,
    AssessmentStage,
    AssessmentStatus,
    EventKind,
    EventName,
)

POLL_INTERVAL_MS = 2000


def events_of_current_run(events: list[AgentEvent]) -> list[AgentEvent]:
    """Keep the events recorded after the user's last answer."""
    answers = [index for index, event in enumerate(events) if event.kind == EventKind.USER_INPUT]

    return events[answers[-1] + 1 :] if answers else events


def find_stage(assessment: Assessment, current: list[AgentEvent]) -> AssessmentStage:
    """Translate the status and latest event into a stage for the user."""
    if assessment.status != AssessmentStatus.PROCESSING:
        return AssessmentStage.FINISHED

    if not current or current[-1].name == EventName.RECEIVED:
        return AssessmentStage.RECEIVED

    if current[-1].name == EventName.VALIDATED:
        return AssessmentStage.VALIDATING

    return AssessmentStage.ANALYZING


def build_progress(assessment: Assessment, events: list[AgentEvent]) -> AssessmentProgress:
    """Summarize where a run is, without its dossier or history."""
    current = events_of_current_run(events)
    is_finished = assessment.status != AssessmentStatus.PROCESSING

    return AssessmentProgress(
        id=assessment.id,
        status=assessment.status,
        stage=find_stage(assessment, current),
        last_action=current[-1].name if current else None,
        is_finished=is_finished,
        poll_after_ms=None if is_finished else POLL_INTERVAL_MS,
        error=assessment.error,
        updated_at=assessment.updated_at,
    )
