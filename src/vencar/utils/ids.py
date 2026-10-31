import uuid


def new_id() -> str:
    """Create a random unique identifier."""
    return uuid.uuid4().hex
