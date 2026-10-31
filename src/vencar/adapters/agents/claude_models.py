from langchain_anthropic import ChatAnthropic

MAX_TOKENS = 16000
REQUEST_TIMEOUT_SECONDS = 300
EFFORT = "high"
REFUSAL_FALLBACK_BETA = "server-side-fallback-2026-07-01"


def create_claude_model(model_name: str, api_key: str | None) -> ChatAnthropic:
    """Create the Claude chat model used by the orchestrator and the specialists."""
    options = {"api_key": api_key} if api_key else {}

    return ChatAnthropic(
        model=model_name,
        max_tokens=MAX_TOKENS,
        thinking={"type": "adaptive", "display": "summarized"},
        effort=EFFORT,
        betas=[REFUSAL_FALLBACK_BETA],
        model_kwargs={"fallbacks": "default"},
        timeout=REQUEST_TIMEOUT_SECONDS,
        **options,
    )
