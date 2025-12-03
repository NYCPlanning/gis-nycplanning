from pathlib import Path
import pytest

RESOURCES = Path(__file__).parent / "resources"


@pytest.fixture()
def resources_path():
    return RESOURCES
