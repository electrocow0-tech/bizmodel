from pathlib import Path

import pytest
from fakes import FakeLLM

from bizmodel import config
from bizmodel.context import Context
from bizmodel.journal import Journal
from bizmodel.schemas import Company

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def settings() -> config.Settings:
    return config.load(ROOT)


@pytest.fixture
def ctx(settings, tmp_path) -> Context:
    return Context(
        settings=settings,
        llm=FakeLLM(),
        journal=Journal(tmp_path / "calls.jsonl"),
        cache=tmp_path,
    )


@pytest.fixture
def company() -> Company:
    return Company(
        slug="acme",
        name="Acme",
        one_liner="Invoicing for freelancers",
        description="Acme sends invoices for freelancers. Teams pay $20 per seat every month.",
        industry="B2B",
        subindustry="Finance",
        tags=["SaaS"],
        batch="Winter 2026",
        team_size=3,
        website="https://acme.example",
        yc_url="https://www.ycombinator.com/companies/acme",
    )
