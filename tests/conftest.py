import pytest

from support.harness import Harness


@pytest.fixture
def harness(tmp_path) -> Harness:
    """Provide a fresh test API."""
    return Harness(tmp_path)
