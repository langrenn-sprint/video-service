"""Conftest module."""

from pathlib import Path
from typing import Any

import pytest
from aiohttp.test_utils import TestClient as _TestClient
from dotenv import load_dotenv


@pytest.fixture(scope="session")
def docker_compose_file(pytestconfig: Any) -> Any:
    """Override default location of docker-compose.yml file."""
    return Path(str(pytestconfig.rootdir)) / "docker-compose.yml"
