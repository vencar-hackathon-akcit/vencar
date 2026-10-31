from collections.abc import Callable
from typing import Protocol

from vencar.domain.models import (
    AgentEvent,
    AgentRequest,
    Assessment,
    Dossier,
    NewEvent,
    Photo,
    PhotoUpload,
    VehicleData,
)

EventSink = Callable[[NewEvent], None]


class AssessmentRepository(Protocol):
    """Outbound port for persisting assessments and their history."""

    def create(self, owner: str, vehicle: VehicleData, description: str) -> Assessment:
        """Create an assessment in the processing state."""

    def get(self, assessment_id: str, owner: str) -> Assessment | None:
        """Return an assessment only if it belongs to the owner."""

    def list_by_owner(self, owner: str) -> list[Assessment]:
        """Return the owner's assessments, newest first."""

    def add_photo(self, assessment_id: str, photo: Photo) -> None:
        """Attach a stored photo to an assessment."""

    def list_photos(self, assessment_id: str) -> list[Photo]:
        """Return the photos of an assessment in upload order."""

    def append_event(self, assessment_id: str, run: int, event: NewEvent) -> None:
        """Append an event to the tamper-evident history."""

    def list_events(self, assessment_id: str) -> list[AgentEvent]:
        """Return the history of an assessment, oldest first."""

    def history_is_intact(self, assessment_id: str) -> bool:
        """Tell whether the history hash chain is still valid."""

    def next_run(self, assessment_id: str) -> int:
        """Return the number of the next agent run."""

    def latest_run(self, assessment_id: str) -> int:
        """Return the number of the most recent agent run."""

    def begin_rerun(self, assessment_id: str, vehicle: VehicleData) -> bool:
        """Atomically move an idle assessment back to processing."""

    def finish(self, assessment_id: str, dossier: Dossier) -> None:
        """Store a dossier and move the assessment to its status."""

    def fail(self, assessment_id: str, error: str) -> None:
        """Mark an assessment as failed."""

    def fail_interrupted(self) -> None:
        """Fail assessments left in processing by a previous shutdown."""

    def previous_dossiers(self, plate: str, owner: str, exclude_id: str) -> list[Assessment]:
        """Return the owner's earlier finished assessments of the same plate."""


class PhotoStorage(Protocol):
    """Outbound port for validating and storing photos."""

    def validate(self, upload: PhotoUpload) -> None:
        """Reject an upload that is not an acceptable image."""

    def save(self, assessment_id: str, evidence_id: str, upload: PhotoUpload) -> Photo:
        """Store a normalized copy of an upload."""


class AssessmentAgent(Protocol):
    """Outbound port for the intelligent agent that assesses a vehicle."""

    def run(self, request: AgentRequest, sink: EventSink) -> Dossier:
        """Run the agent, reporting every step to the sink."""
