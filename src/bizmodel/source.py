"""Источник бизнес-моделей: открытый каталог компаний Y Combinator."""

import json
import random
from collections import defaultdict
from pathlib import Path

import httpx

from bizmodel.config import Source
from bizmodel.schemas import Company


def load(settings: Source, snapshot: Path) -> list[Company]:
    """Выборка фиксируется снимком: каталог меняется каждый день, а прогон должен повторяться."""
    if snapshot.exists():
        saved = json.loads(snapshot.read_text(encoding="utf-8"))
        return [Company(**entry) for entry in saved]

    catalog = httpx.get(settings.url, timeout=120).raise_for_status().json()
    companies = sample(catalog, settings)
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text(
        json.dumps([company.model_dump() for company in companies], ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    return companies


def sample(catalog: list[dict], settings: Source) -> list[Company]:
    """Поровну из каждой отрасли: так фильтру достаются и финтех, и железо, и госсектор."""
    by_industry = defaultdict(list)
    for entry in catalog:
        if eligible(entry, settings):
            by_industry[entry["industry"]].append(entry)

    rng = random.Random(settings.seed)
    quota = settings.sample_size // len(by_industry)
    picked, spare = [], []
    for industry in sorted(by_industry):
        entries = sorted(by_industry[industry], key=lambda entry: entry["slug"])
        rng.shuffle(entries)
        picked += entries[:quota]
        spare += entries[quota:]
    rng.shuffle(spare)
    picked += spare[: settings.sample_size - len(picked)]

    return [
        Company(
            slug=entry["slug"],
            name=entry["name"],
            one_liner=entry.get("one_liner") or "",
            description=entry["long_description"],
            industry=entry["industry"],
            subindustry=entry.get("subindustry") or "",
            tags=entry.get("tags") or [],
            batch=entry.get("batch") or "",
            team_size=entry.get("team_size"),
            website=entry.get("website") or "",
            yc_url=entry["url"],
        )
        for entry in sorted(picked, key=lambda entry: entry["slug"])
    ]


def eligible(entry: dict, settings: Source) -> bool:
    return (
        entry.get("status") == "Active"
        and not entry.get("nonprofit")
        and entry.get("industry") not in (None, "Unspecified")
        and len(entry.get("long_description") or "") >= settings.min_description_chars
        and not set(entry.get("regions") or []) & set(settings.excluded_regions)
    )
