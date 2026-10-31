from pathlib import Path

from fastapi.testclient import TestClient

from support.builders import UNO, USER_A, findings, photo
from support.fakes import FakeSpecialist, ScriptedChatModel
from vencar.adapters.agents.assessment_graph import LangGraphAssessmentAgent
from vencar.adapters.database.sqlite_assessment_repository import (
    SqliteAssessmentRepository,
)
from vencar.config import Settings
from vencar.domain.models import SpecialistName
from vencar.main import create_app


class Harness:
    """Test API wired to the real graph with a scripted orchestrator."""

    def __init__(self, tmp_path: Path) -> None:
        """Create the API, database and fake agents."""
        self.path = tmp_path / "vencar.db"
        self.model = ScriptedChatModel(script=[], received=[])
        self.bodywork = FakeSpecialist(SpecialistName.BODYWORK, findings())
        self.interior = FakeSpecialist(SpecialistName.INTERIOR, findings())
        settings = Settings(_env_file=None, vencar_data_dir=tmp_path)
        repository = SqliteAssessmentRepository(self.path)

        agent = LangGraphAssessmentAgent(
            lambda: self.model,
            lambda: {
                SpecialistName.BODYWORK: self.bodywork,
                SpecialistName.INTERIOR: self.interior,
            },
            repository,
        )

        self.client = TestClient(create_app(settings, agent))

    def submit(self, script: list, data: dict = UNO, files: list | None = None) -> dict:
        """Create an assessment and return it once the agent finished."""
        self.model.script[:] = script
        uploads = [photo()] if files is None else files
        response = self.client.post("/api/v1/assessments", data=data, files=uploads, headers=USER_A)
        assert response.status_code == 202

        return self.client.get(
            f"/api/v1/assessments/{response.json()['id']}", headers=USER_A
        ).json()
