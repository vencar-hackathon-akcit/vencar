from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from langchain_core.language_models.chat_models import BaseChatModel

from vencar.adapters.agents.assessment_graph import LangGraphAssessmentAgent
from vencar.adapters.agents.claude_models import create_claude_model
from vencar.adapters.agents.gemini_models import create_gemini_model
from vencar.adapters.agents.specialist_catalog import SpecialistCatalog
from vencar.adapters.agents.specialists import Specialist
from vencar.adapters.api.assessments_controller import create_assessments_router
from vencar.adapters.api.error_handlers import register_error_handlers
from vencar.adapters.database.sqlite_assessment_repository import (
    SqliteAssessmentRepository,
)
from vencar.adapters.storage.local_photo_storage import LocalPhotoStorage
from vencar.application.ports import AssessmentAgent
from vencar.application.use_cases.answer_assessment import AnswerAssessment
from vencar.application.use_cases.create_assessment import CreateAssessment
from vencar.application.use_cases.read_assessments import ReadAssessments
from vencar.application.use_cases.run_assessment import RunAssessment
from vencar.config import ModelProvider, Settings
from vencar.domain.models import SpecialistName


@dataclass(frozen=True)
class ProviderConfig:
    """How to create a provider's model and bind tools to it."""

    create_model: Callable[[str, str | None], BaseChatModel]
    tool_options: dict


MODEL_PROVIDERS = {
    ModelProvider.GOOGLE: ProviderConfig(create_gemini_model, {}),
    ModelProvider.ANTHROPIC: ProviderConfig(create_claude_model, {"strict": True}),
}
TEST_UI_DIR = Path(__file__).resolve().parents[2] / "test_ui"


def create_real_agent(
    settings: Settings, repository: SqliteAssessmentRepository
) -> AssessmentAgent:
    """Wire the LangGraph agent to Claude."""

    provider = MODEL_PROVIDERS[settings.vencar_provider]

    def model_factory() -> BaseChatModel:
        """Create the chat model when a run starts."""
        return provider.create_model(settings.model_name(), settings.provider_api_key())

    def specialist_factory() -> dict[SpecialistName, Specialist]:
        """Create the specialist agents when a run starts."""
        return SpecialistCatalog.create_specialists(model_factory)

    return LangGraphAssessmentAgent(
        model_factory, specialist_factory, repository, provider.tool_options
    )


def create_app(settings: Settings | None = None, agent: AssessmentAgent | None = None) -> FastAPI:
    """Composition root: connect adapters, use cases and controllers."""
    settings = settings or Settings()
    settings.vencar_data_dir.mkdir(parents=True, exist_ok=True)
    repository = SqliteAssessmentRepository(settings.vencar_data_dir / "vencar.db")
    repository.fail_interrupted()
    storage = LocalPhotoStorage(settings.vencar_data_dir / "photos")
    selected_agent = agent or create_real_agent(settings, repository)
    app = FastAPI(title="Vencar API")
    register_error_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins(),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(
        create_assessments_router(
            settings.tokens(),
            CreateAssessment(repository, storage),
            AnswerAssessment(repository, storage),
            ReadAssessments(repository),
            RunAssessment(repository, selected_agent),
        )
    )

    if TEST_UI_DIR.is_dir():
        app.mount("/test-ui", StaticFiles(directory=TEST_UI_DIR, html=True), name="test-ui")

    @app.get("/health")
    def health() -> dict[str, str]:
        """Report that the API is running."""
        return {"status": "ok"}

    return app
