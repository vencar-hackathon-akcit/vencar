from vencar.application.ports import AssessmentRepository
from vencar.domain.errors import AssessmentNotFoundError
from vencar.domain.models import Assessment, AssessmentDetails, Photo


class ReadAssessments:
    """Read assessments, always scoped to their owner."""

    def __init__(self, repository: AssessmentRepository) -> None:
        """Receive the port this use case depends on."""
        self.repository = repository

    def list_for(self, owner: str) -> list[Assessment]:
        """List the owner's assessments."""
        return self.repository.list_by_owner(owner)

    def detail(self, assessment_id: str, owner: str) -> AssessmentDetails:
        """Return an assessment with its full history, integrity verdict and photos."""
        assessment = self.repository.get(assessment_id, owner)

        if assessment is None:
            raise AssessmentNotFoundError(assessment_id)

        return AssessmentDetails(
            assessment=assessment,
            events=self.repository.list_events(assessment_id),
            history_intact=self.repository.history_is_intact(assessment_id),
            photos=self.repository.list_photos(assessment_id),
        )

    def photo(self, assessment_id: str, photo_id: str, owner: str) -> Photo:
        """Return a photo only to the owner of its assessment."""
        if self.repository.get(assessment_id, owner) is None:
            raise AssessmentNotFoundError(assessment_id)

        for photo in self.repository.list_photos(assessment_id):
            if photo.id == photo_id:
                return photo

        raise AssessmentNotFoundError(photo_id)
