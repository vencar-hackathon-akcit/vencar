from vencar.application.ports import AssessmentRepository, PhotoStorage
from vencar.domain.errors import ErrorCode, VencarError
from vencar.domain.models import Assessment, PhotoUpload, VehicleData

MAX_PHOTOS = 10


class CreateAssessment:
    """Open an assessment from vehicle data, a description and photos."""

    def __init__(self, repository: AssessmentRepository, storage: PhotoStorage) -> None:
        """Receive the ports this use case depends on."""
        self.repository = repository
        self.storage = storage

    def execute(
        self, owner: str, vehicle: VehicleData, description: str, uploads: list[PhotoUpload]
    ) -> Assessment:
        """Validate the uploads first so that a rejected request creates nothing."""
        if len(uploads) > MAX_PHOTOS:
            raise VencarError(ErrorCode.TOO_MANY_PHOTOS, f"Envie no maximo {MAX_PHOTOS} fotos.")

        for upload in uploads:
            self.storage.validate(upload)

        vehicle = vehicle.model_copy(update={"plate": vehicle.plate.strip().upper()})
        assessment = self.repository.create(owner, vehicle, description)

        for index, upload in enumerate(uploads, start=1):
            self.repository.add_photo(
                assessment.id, self.storage.save(assessment.id, f"P{index}", upload)
            )

        return assessment
