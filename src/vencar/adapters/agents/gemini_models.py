from langchain_google_genai import ChatGoogleGenerativeAI

MAX_OUTPUT_TOKENS = 16000
REQUEST_TIMEOUT_SECONDS = 90
MAX_RETRIES = 2


def create_gemini_model(model_name: str, api_key: str | None) -> ChatGoogleGenerativeAI:
    """Create the Gemini chat model used by the orchestrator and the specialists."""
    options = {"google_api_key": api_key} if api_key else {}

    return ChatGoogleGenerativeAI(
        model=model_name,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        include_thoughts=True,
        timeout=REQUEST_TIMEOUT_SECONDS,
        max_retries=MAX_RETRIES,
        **options,
    )
