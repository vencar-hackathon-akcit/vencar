def split_csv(text: str) -> list[str]:
    """Split comma-separated text, dropping surrounding spaces and empty items."""
    return [item.strip() for item in text.split(",") if item.strip()]
