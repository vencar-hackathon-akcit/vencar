from vencar.domain.models import (
    AgentEvent,
    Assessment,
    AssessmentDetails,
    AssessmentStatus,
    DomainModel,
)


class AssessmentAccepted(DomainModel):
    """Response for a request that started an agent run."""

    id: str
    status: AssessmentStatus


class PhotoSummary(DomainModel):
    """Public description of a photo, without its storage location."""

    id: str
    evidence_id: str
    filename: str


class AssessmentDetail(Assessment):
    """Assessment with its complete traceable history."""

    events: list[AgentEvent]
    history_intact: bool
    photos: list[PhotoSummary]

    @classmethod
    def from_details(cls, details: AssessmentDetails) -> "AssessmentDetail":
        """Build the response from what the use case returned."""
        assessment = details.assessment

        return cls(
            **assessment.model_dump(),
            owner=assessment.owner,
            events=details.events,
            history_intact=details.history_intact,
            photos=[
                PhotoSummary(id=item.id, evidence_id=item.evidence_id, filename=item.filename)
                for item in details.photos
            ],
        )
