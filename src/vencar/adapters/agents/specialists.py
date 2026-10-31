import base64
from pathlib import Path
from typing import Protocol

from langchain_core.exceptions import OutputParserException
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from vencar.domain.errors import ErrorCode, VencarError
from vencar.domain.models import (
    Category,
    Photo,
    SpecialistFindings,
    SpecialistName,
    SpecialistReport,
    VehicleData,
)
from vencar.utils.media import JPEG_MEDIA_TYPE
from vencar.utils.serialization import to_json

MAX_ATTEMPTS = 2


class Specialist(Protocol):
    """Agent that inspects photos within one area of expertise."""

    def inspect(
        self, vehicle: VehicleData, description: str, photos: list[Photo], focus: str
    ) -> SpecialistReport:
        """Inspect the photos and return structured findings."""


class ChatSpecialist:
    """Specialist agent backed by a multimodal chat model with structured output."""

    def __init__(
        self,
        name: SpecialistName,
        model: BaseChatModel,
        prompt: str,
        allowed_categories: set[Category],
    ) -> None:
        """Configure the specialist's identity, model, instructions and scope."""
        self.name = name
        self.model = model.with_structured_output(SpecialistFindings, method="json_schema")
        self.prompt = prompt
        self.allowed_categories = allowed_categories

    def restrict_scope(self, findings: SpecialistFindings) -> SpecialistFindings:
        """Remove anything outside the categories this specialist may evaluate."""
        return findings.model_copy(
            update={
                "damages": [
                    item for item in findings.damages if item.category in self.allowed_categories
                ],
                "evaluated_categories": [
                    item
                    for item in findings.evaluated_categories
                    if item in self.allowed_categories
                ],
            }
        )

    def inspect(
        self, vehicle: VehicleData, description: str, photos: list[Photo], focus: str
    ) -> SpecialistReport:
        """Call the model, retrying once when the output is not valid."""
        case = {"vehicle": vehicle.model_dump(), "E1_description": description, "focus": focus}

        content = CaseContentBuilder.build_case_content(photos, case)

        messages = [SystemMessage(content=self.prompt), HumanMessage(content=content)]
        problem = ""

        for _ in range(MAX_ATTEMPTS):
            try:
                findings = self.model.invoke(messages)
            except (OutputParserException, ValidationError) as error:
                problem = str(error)
                continue

            if findings is not None:
                return SpecialistReport(
                    specialist=self.name, findings=self.restrict_scope(findings)
                )

            problem = "resposta vazia"

        raise VencarError(
            ErrorCode.AGENT_FAILURE, f"{self.name} nao produziu uma saida valida: {problem}"
        )


class CaseContentBuilder:
    """Build the labelled evidence content sent to a model."""

    @staticmethod
    def photo_blocks(photos: list[Photo]) -> list[dict]:
        """Build labelled image blocks so each photo can be cited by its evidence id."""
        blocks: list[dict] = []

        for photo in photos:
            data = base64.standard_b64encode(Path(photo.path).read_bytes()).decode("utf-8")
            blocks.append({"type": "text", "text": f"Evidencia {photo.evidence_id} (foto):"})

            blocks.append({"type": "image", "base64": data, "mime_type": JPEG_MEDIA_TYPE})

        return blocks

    @staticmethod
    def build_case_content(photos: list[Photo], case: dict) -> list[dict]:
        """Combine the photos and the case data into one message for a model."""
        case_text = "Dados do caso:\n" + to_json(case)

        return [*CaseContentBuilder.photo_blocks(photos), {"type": "text", "text": case_text}]
