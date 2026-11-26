"""Учебный сбой провайдера: основной маршрут выключен, запрос должен дойти по запасному."""

import tempfile
import time
from pathlib import Path

from bizmodel import prescreen, source
from bizmodel.config import Settings
from bizmodel.context import Context
from bizmodel.journal import Journal
from bizmodel.llm import LLM
from bizmodel.schemas import OutageDrill


def run(settings: Settings) -> OutageDrill:
    """Настоящий запрос дешёвого слоя при выключенном основном провайдере, без кеша."""
    chain = settings.roles.prescreen
    primary = chain.routes[0].split(":", 1)[0]
    company = source.load(settings.source, settings.root / "data" / "source" / "sample.json")[0]

    with tempfile.TemporaryDirectory() as scratch:
        journal = Journal(Path(scratch) / "calls.jsonl")
        llm = LLM(settings.models, journal, Path(scratch) / "llm", down=frozenset({primary}))
        ctx = Context(settings=settings, llm=llm, journal=journal, cache=Path(scratch))
        started = time.monotonic()
        prescreen.screen(company, ctx)
        seconds = time.monotonic() - started
        failure = journal.read("llm_failure")[0]
        served = journal.read("llm_call")[0]

    return OutageDrill(
        role="prescreen",
        failed_route=failure["route"],
        error=failure["error"],
        served_by=served["route"],
        seconds=round(seconds, 1),
    )
