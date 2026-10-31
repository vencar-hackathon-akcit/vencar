import io
import uuid
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from vencar.domain.errors import ErrorCode, VencarError
from vencar.domain.models import Photo, PhotoUpload

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_IMAGE_EDGE = 1568


class LocalPhotoStorage:
    """Store normalized JPEG copies of uploads, without metadata, on local disk."""

    def __init__(self, base_dir: Path) -> None:
        """Remember where the photos are stored."""
        self.base_dir = base_dir

    def validate(self, upload: PhotoUpload) -> None:
        """Reject uploads that are too large or are not fully readable images."""
        if len(upload.content) > MAX_UPLOAD_BYTES:
            raise VencarError(ErrorCode.INVALID_PHOTO, f"{upload.filename}: imagem acima de 15 MB.")

        try:
            Image.open(io.BytesIO(upload.content)).load()
        except (
            UnidentifiedImageError,
            OSError,
            SyntaxError,
            Image.DecompressionBombError,
        ) as error:
            raise VencarError(
                ErrorCode.INVALID_PHOTO, f"{upload.filename}: arquivo nao e uma imagem valida."
            ) from error

    def save(self, assessment_id: str, evidence_id: str, upload: PhotoUpload) -> Photo:
        """Resize, strip metadata and write the image to disk."""
        folder = self.base_dir / assessment_id
        folder.mkdir(parents=True, exist_ok=True)
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(upload.content))).convert("RGB")
        image.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE))
        photo_id = uuid.uuid4().hex
        path = folder / f"{photo_id}.jpg"
        image.save(path, "JPEG", quality=85)

        return Photo(
            id=photo_id,
            evidence_id=evidence_id,
            filename=Path(upload.filename).name,
            path=str(path),
        )
