from vencar.application.ports import AssessmentRepository, PhotoStorage
from vencar.application.use_cases.create_assessment import MAX_PHOTOS
from vencar.domain.errors import ErrorCode, VencarError
from vencar.domain.models import EventKind, EventName, NewEvent, PhotoUpload


class AnswerAssessment:
    """Record a user intervention so the agent can continue with new information."""

    def __init__(self, repository: AssessmentRepository, storage: PhotoStorage) -> None:
        """Receive the ports this use case depends on."""
        self.repository = repository
        self.storage = storage

    def execute(
        self,
        assessment_id: str,
        owner: str,
        answer: str,
        vehicle_updates: dict[str, str],
        uploads: list[PhotoUpload],
    ) -> None:
        """Validate, store and log the new information, then release the case for a new run."""
        assessment = self.repository.get(assessment_id, owner)

        if assessment is None:
            raise VencarError(ErrorCode.ASSESSMENT_NOT_FOUND)

        existing = len(self.repository.list_photos(assessment_id))

        if existing + len(uploads) > MAX_PHOTOS:
            raise VencarError(
                ErrorCode.TOO_MANY_PHOTOS, f"A avaliacao aceita no maximo {MAX_PHOTOS} fotos."
            )

        for upload in uploads:
            self.storage.validate(upload)

        updates = {key: value.strip() for key, value in vehicle_updates.items() if value.strip()}

        if "plate" in updates:
            updates["plate"] = updates["plate"].upper()

        vehicle = assessment.vehicle.model_copy(update=updates)

        if not self.repository.begin_rerun(assessment_id, vehicle):
            raise VencarError(ErrorCode.ASSESSMENT_BUSY)

        for index, upload in enumerate(uploads, start=existing + 1):
            self.repository.add_photo(
                assessment_id, self.storage.save(assessment_id, f"P{index}", upload)
            )

        details = {
            "answer": answer,
            "vehicle_updates": updates,
            "new_photos": [upload.filename for upload in uploads],
        }

        self.repository.append_event(
            assessment_id,
            self.repository.latest_run(assessment_id),
            NewEvent(kind=EventKind.USER_INPUT, name=EventName.USER_ANSWER, input=details),
        )
