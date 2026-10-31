from vencar.application.ports import AssessmentAgent, AssessmentRepository
from vencar.domain.models import AgentRequest, EventKind, EventName, NewEvent


class RunAssessment:
    """Run the agent on an assessment and persist its outcome."""

    def __init__(self, repository: AssessmentRepository, agent: AssessmentAgent) -> None:
        """Receive the ports this use case depends on."""
        self.repository = repository
        self.agent = agent

    def answers_of(self, assessment_id: str) -> list[str]:
        """Collect the answers the user has already given."""
        events = self.repository.list_events(assessment_id)

        return [
            event.input["answer"]
            for event in events
            if event.kind == EventKind.USER_INPUT and event.input.get("answer")
        ]

    def execute(self, assessment_id: str, owner: str) -> None:
        """Run the agent, recording either the dossier or the failure."""
        run = self.repository.next_run(assessment_id)

        def sink(event: NewEvent) -> None:
            """Forward an agent event to the history of this run."""
            self.repository.append_event(assessment_id, run, event)

        try:
            assessment = self.repository.get(assessment_id, owner)

            request = AgentRequest(
                assessment_id=assessment_id,
                owner=owner,
                vehicle=assessment.vehicle,
                description=assessment.description,
                answers=self.answers_of(assessment_id),
                photos=self.repository.list_photos(assessment_id),
            )

            dossier = self.agent.run(request, sink)
            sink(
                NewEvent(
                    kind=EventKind.STEP,
                    name=EventName.DOSSIER_ISSUED,
                    output=dossier.model_dump(mode="json"),
                )
            )
            self.repository.finish(assessment_id, dossier)
        except Exception as error:
            sink(NewEvent(kind=EventKind.STEP, name=EventName.FAILED, output={"error": str(error)}))
            self.repository.fail(assessment_id, str(error))
