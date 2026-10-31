from enum import StrEnum
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from vencar.utils.text import split_csv


class ModelProvider(StrEnum):
    """Companies whose models can power the agents."""

    GOOGLE = "google"
    ANTHROPIC = "anthropic"


DEFAULT_MODELS = {
    ModelProvider.GOOGLE: "gemini-3.5-flash-lite",
    ModelProvider.ANTHROPIC: "claude-opus-5-5",
}


class Settings(BaseSettings):
    """Application settings read from the environment or a .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    anthropic_api_key: str | None = None
    google_api_key: str | None = None
    vencar_provider: ModelProvider = ModelProvider.GOOGLE
    vencar_model: str = ""
    vencar_data_dir: Path = Path("data")
    vencar_api_tokens: str = "teste-usuario-a:usuario_a,teste-usuario-b:usuario_b"
    vencar_cors_origins: str = "http://localhost:3000"

    def model_name(self) -> str:
        """Return the configured model, or the default of the selected provider."""
        return self.vencar_model or DEFAULT_MODELS[self.vencar_provider]

    def provider_api_key(self) -> str | None:
        """Return the API key of the selected provider."""
        if self.vencar_provider == ModelProvider.GOOGLE:
            return self.google_api_key

        return self.anthropic_api_key

    def tokens(self) -> dict[str, str]:
        """Parse the token:user pairs allowed to access the API."""
        return dict(pair.split(":", 1) for pair in split_csv(self.vencar_api_tokens) if ":" in pair)

    def cors_origins(self) -> list[str]:
        """Parse the origins allowed to call the API from a browser."""
        return split_csv(self.vencar_cors_origins)
