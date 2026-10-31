from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from vencar.utils.text import split_csv


class Settings(BaseSettings):
    """Application settings read from the environment or a .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    anthropic_api_key: str | None = None
    vencar_model: str = "claude-opus-5-5"
    vencar_data_dir: Path = Path("data")
    vencar_api_tokens: str = "teste-usuario-a:usuario_a,teste-usuario-b:usuario_b"
    vencar_cors_origins: str = "http://localhost:3000"

    def tokens(self) -> dict[str, str]:
        """Parse the token:user pairs allowed to access the API."""
        return dict(pair.split(":", 1) for pair in split_csv(self.vencar_api_tokens) if ":" in pair)

    def cors_origins(self) -> list[str]:
        """Parse the origins allowed to call the API from a browser."""
        return split_csv(self.vencar_cors_origins)
