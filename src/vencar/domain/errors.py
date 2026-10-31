class AssessmentNotFoundError(Exception):
    """Raised when an assessment does not exist or belongs to someone else."""


class AssessmentBusyError(Exception):
    """Raised when an assessment is already being processed."""


class InvalidPhotoError(Exception):
    """Raised when an upload is not a readable image of acceptable size."""


class TooManyPhotosError(Exception):
    """Raised when an assessment would exceed the photo limit."""


class AgentFailureError(Exception):
    """Raised when the agent cannot finish its work."""
