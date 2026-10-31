from vencar.adapters.agents.claude_models import create_claude_model
from vencar.adapters.agents.specialist_catalog import create_specialists
from vencar.domain.models import SpecialistName


def test_real_model_request_has_the_expected_shape() -> None:
    """Without calling the API, check what is sent for tools and structured output."""
    model = create_claude_model("claude-opus-5-5", "chave-falsa")
    payload = model._get_request_payload([("user", "oi")])
    assert payload["thinking"]["type"] == "adaptive" and payload["fallbacks"] == "default"
    assert payload["output_config"]["effort"] == "high"
    assert "temperature" not in payload
    specialists = create_specialists(lambda: model)
    assert set(specialists) == set(SpecialistName)
