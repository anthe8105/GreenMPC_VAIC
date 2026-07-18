from __future__ import annotations

import pytest

from tests._simulation_helpers import config


@pytest.fixture
def sim_config():
    return config()
