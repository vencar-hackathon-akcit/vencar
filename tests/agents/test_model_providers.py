from langchain_core.messages import HumanMessage

from vencar.adapters.agents.claude_models import create_claude_model
from vencar.adapters.agents.gemini_models import create_gemini_model
from vencar.adapters.agents.specialists import CaseContentBuilder
from vencar.config import ModelProvider, Settings
from vencar.domain.models import Photo
from vencar.main import MODEL_PROVIDERS


def sample_message(tmp_path) -> HumanMessage:
    """Build a message containing one photo, as the agents send it."""
    path = tmp_path / "foto.jpg"
    path.write_bytes(b"jpeg")
    photo = Photo(id="1", evidence_id="P1", filename="foto.jpg", path=str(path))

    return HumanMessage(content=CaseContentBuilder.build_case_content([photo], {"a": 1}))


def test_photos_reach_claude_in_its_format(tmp_path) -> None:
    """The shared photo block becomes Claude's image format."""
    model = create_claude_model("claude-opus-5-5", "chave-falsa")
    content = model._get_request_payload([sample_message(tmp_path)])["messages"][0]["content"]

    assert any(block["type"] == "image" for block in content)


def test_photos_reach_gemini_in_its_format(tmp_path) -> None:
    """The shared photo block becomes Gemini's inline image data."""
    model = create_gemini_model("gemini-3.5-flash-lite", "chave-falsa")
    parts = model._prepare_request([sample_message(tmp_path)])["contents"][0].parts

    assert any(part.inline_data and part.inline_data.data == b"jpeg" for part in parts)


def test_settings_use_the_default_model_of_the_selected_provider() -> None:
    """Choosing a provider is enough, and an explicit model still wins."""
    google = Settings(_env_file=None, vencar_provider=ModelProvider.GOOGLE)
    anthropic = Settings(_env_file=None, vencar_provider=ModelProvider.ANTHROPIC)
    explicit = Settings(
        _env_file=None, vencar_provider=ModelProvider.GOOGLE, vencar_model="outro-modelo"
    )

    assert google.model_name() == "gemini-3.5-flash-lite"
    assert anthropic.model_name() == "claude-opus-5-5"
    assert explicit.model_name() == "outro-modelo"


def test_only_claude_requests_strict_tool_schemas() -> None:
    """Strict schemas are a Claude option and are not sent to Gemini."""
    assert MODEL_PROVIDERS[ModelProvider.ANTHROPIC].tool_options == {"strict": True}
    assert MODEL_PROVIDERS[ModelProvider.GOOGLE].tool_options == {}
