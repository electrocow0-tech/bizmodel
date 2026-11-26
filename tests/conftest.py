from pathlib import Path

import pytest

from bizmodel import config

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def settings() -> config.Settings:
    return config.load(ROOT)
