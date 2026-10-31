from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Header,
    UploadFile,
)
from fastapi.responses import FileResponse

from vencar.adapters.api.schemas import AssessmentAccepted, AssessmentDetail
from vencar.application.use_cases.answer_assessment import AnswerAssessment
from vencar.application.use_cases.create_assessment import CreateAssessment
from vencar.application.use_cases.read_assessments import ReadAssessments
from vencar.application.use_cases.run_assessment import RunAssessment
from vencar.domain.errors import ErrorCode, VencarError
from vencar.domain.models import Assessment, AssessmentStatus, PhotoUpload, VehicleData

JPEG_MEDIA_TYPE = "image/jpeg"


async def read_uploads(files: list[UploadFile]) -> list[PhotoUpload]:
    """Read uploaded files into the shape the use cases expect."""
    return [
        PhotoUpload(filename=file.filename or "foto", content=await file.read()) for file in files
    ]


def create_assessments_router(
    tokens: dict[str, str],
    create: CreateAssessment,
    answer: AnswerAssessment,
    read: ReadAssessments,
    run: RunAssessment,
) -> APIRouter:
    """Build the controllers, which only translate HTTP to use cases."""
    router = APIRouter(prefix="/api/v1/assessments", tags=["assessments"])

    def current_user(authorization: str = Header(default="")) -> str:
        """Resolve the bearer token into a user or reject the request."""
        user = tokens.get(authorization.removeprefix("Bearer ").strip())

        if user is None:
            raise VencarError(ErrorCode.UNAUTHORIZED)

        return user

    @router.post("", status_code=202, response_model=AssessmentAccepted)
    async def create_assessment(
        background: BackgroundTasks,
        make: str = Form(""),
        model: str = Form(""),
        year: str = Form(""),
        plate: str = Form(""),
        mileage: str = Form(""),
        region: str = Form(""),
        usage: str = Form(""),
        description: str = Form(""),
        photos: list[UploadFile] = File(default=[]),
        user: str = Depends(current_user),
    ) -> AssessmentAccepted:
        """Open an assessment and start the agent in the background."""
        vehicle = VehicleData(
            make=make,
            model=model,
            year=year,
            plate=plate,
            mileage=mileage,
            region=region,
            usage=usage,
        )

        assessment = create.execute(user, vehicle, description, await read_uploads(photos))
        background.add_task(run.execute, assessment.id, user)

        return AssessmentAccepted(id=assessment.id, status=assessment.status)

    @router.post("/{assessment_id}/answers", status_code=202, response_model=AssessmentAccepted)
    async def answer_assessment(
        assessment_id: str,
        background: BackgroundTasks,
        answer_text: str = Form("", alias="answer"),
        make: str = Form(""),
        model: str = Form(""),
        year: str = Form(""),
        plate: str = Form(""),
        photos: list[UploadFile] = File(default=[]),
        user: str = Depends(current_user),
    ) -> AssessmentAccepted:
        """Record the user's answer and start a new agent run."""
        updates = {"make": make, "model": model, "year": year, "plate": plate}
        answer.execute(assessment_id, user, answer_text, updates, await read_uploads(photos))
        background.add_task(run.execute, assessment_id, user)

        return AssessmentAccepted(id=assessment_id, status=AssessmentStatus.PROCESSING)

    @router.get("", response_model=list[Assessment])
    def list_assessments(user: str = Depends(current_user)) -> list[Assessment]:
        """List the authenticated user's assessments."""
        return read.list_for(user)

    @router.get("/{assessment_id}", response_model=AssessmentDetail)
    def get_assessment(assessment_id: str, user: str = Depends(current_user)) -> AssessmentDetail:
        """Return an assessment with its history and integrity verdict."""
        return AssessmentDetail.from_details(read.detail(assessment_id, user))

    @router.get("/{assessment_id}/photos/{photo_id}")
    def get_photo(
        assessment_id: str, photo_id: str, user: str = Depends(current_user)
    ) -> FileResponse:
        """Serve a photo to the owner of its assessment."""
        return FileResponse(
            read.photo(assessment_id, photo_id, user).path, media_type=JPEG_MEDIA_TYPE
        )

    return router
