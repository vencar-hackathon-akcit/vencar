import json

from pydantic import BaseModel


def to_json(data: object) -> str:
    """Serialize data keeping accents readable and converting unknown types to text."""
    return json.dumps(data, ensure_ascii=False, default=str)


def to_plain_data(value: object) -> object:
    """Convert a Pydantic model to plain data, leaving anything else unchanged."""
    return value.model_dump(mode="json") if isinstance(value, BaseModel) else value
