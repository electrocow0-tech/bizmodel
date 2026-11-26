"""Дешёвый слой: одна недорогая модель читает описание и решает, кого проверять глубоко."""

import random
from collections import Counter
from typing import Literal

from pydantic import BaseModel

from bizmodel.config import Funnel
from bizmodel.context import Context
from bizmodel.schemas import BusinessModel, Company, Prescreen, RevenueType, Violation

UNCHECKABLE_FROM_DESCRIPTION = "proven_at_scale"


class Check(BaseModel):
    criterion: str
    violated: bool
    reason: str


class Screening(BaseModel):
    payer: str
    pays_for: str
    frequency: str
    revenue_type: RevenueType
    checks: list[Check]
    speed: Literal[1, 2, 3, 4, 5]
    speed_reason: str


def screen(company: Company, ctx: Context) -> Prescreen:
    checkable = [
        tree for tree in ctx.settings.forest.trees if tree.id != UNCHECKABLE_FROM_DESCRIPTION
    ]
    answer = ctx.llm.ask(
        "prescreen",
        ctx.settings.roles.prescreen,
        ctx.settings.prompt("prescreen"),
        {
            "Owner's criteria": "\n".join(f"- {tree.id}: {tree.title}" for tree in checkable),
            "Company": describe(company),
        },
        Screening,
        slug=company.slug,
    )
    ids = {tree.id for tree in checkable}
    violations = [
        Violation(criterion=check.criterion, reason=check.reason)
        for check in answer.checks
        if check.violated and check.criterion in ids
    ]
    return Prescreen(
        slug=company.slug,
        business_model=BusinessModel(
            payer=answer.payer,
            pays_for=answer.pays_for,
            frequency=answer.frequency,
            revenue_type=answer.revenue_type,
        ),
        violations=violations,
        speed=answer.speed,
        speed_reason=answer.speed_reason,
        status="rejected" if violations else "queued",
    )


def describe(company: Company) -> str:
    return (
        f"Name: {company.name}\n"
        f"One-liner: {company.one_liner}\n"
        f"Industry: {company.industry} / {company.subindustry}\n"
        f"Tags: {', '.join(company.tags)}\n"
        f"Team size: {company.team_size}\n"
        f"Website: {company.website}\n"
        f"Description: {company.description}"
    )


def select(
    prescreens: list[Prescreen], industries: dict[str, str], funnel: Funnel, seed: int
) -> tuple[list[str], list[str]]:
    """Лучшие по скорости идут в глубокую проверку, часть отсеянных - в контрольную выборку."""
    rng = random.Random(seed)
    tiebreak = {prescreen.slug: rng.random() for prescreen in sorted(prescreens, key=_slug)}

    queued = [prescreen for prescreen in prescreens if prescreen.status == "queued"]
    queued.sort(key=lambda prescreen: (-prescreen.speed, tiebreak[prescreen.slug]))
    taken = Counter()
    selected = []
    for prescreen in queued:
        industry = industries[prescreen.slug]
        if len(selected) < funnel.deep_check and taken[industry] < funnel.per_industry_cap:
            prescreen.status = "selected"
            taken[industry] += 1
            selected.append(prescreen.slug)

    rejected = sorted(prescreen.slug for prescreen in prescreens if prescreen.status == "rejected")
    control = rng.sample(rejected, min(funnel.control_sample, len(rejected)))
    return selected, control


def _slug(prescreen: Prescreen) -> str:
    return prescreen.slug
