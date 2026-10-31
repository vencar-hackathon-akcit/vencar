from enum import StrEnum


class ErrorCode(StrEnum):
    """Every expected failure of the application."""

    UNAUTHORIZED = "unauthorized"
    ASSESSMENT_NOT_FOUND = "assessment_not_found"
    ASSESSMENT_BUSY = "assessment_busy"
    INVALID_PHOTO = "invalid_photo"
    TOO_MANY_PHOTOS = "too_many_photos"
    AGENT_FAILURE = "agent_failure"


DEFAULT_MESSAGES = {
    ErrorCode.UNAUTHORIZED: "Token invalido.",
    ErrorCode.ASSESSMENT_NOT_FOUND: "Avaliacao nao encontrada.",
    ErrorCode.ASSESSMENT_BUSY: "A avaliacao ainda esta em processamento.",
    ErrorCode.INVALID_PHOTO: "Arquivo nao e uma imagem valida.",
    ErrorCode.TOO_MANY_PHOTOS: "Limite de fotos excedido.",
    ErrorCode.AGENT_FAILURE: "O agente nao conseguiu concluir o trabalho.",
}


class VencarError(Exception):
    """The application's single error type, identified by its code."""

    def __init__(self, code: ErrorCode, message: str | None = None) -> None:
        """Use the code's default message unless a specific one is given."""
        self.code = code
        self.message = message or DEFAULT_MESSAGES[code]
        super().__init__(self.message)
