"""Критик ищет, почему модель не сработает. Выводов проверяющего он не видит никогда."""

from typing import Literal

from pydantic import BaseModel

from bizmodel.context import Context
from bizmodel.evidence import checked_quote, numbered, show
from bizmodel.prescreen import describe
from bizmodel.schemas import BusinessModel, Company, Objection


class Plan(BaseModel):
    queries: list[str]


class Point(BaseModel):
    text: str
    reasoning: str
    strength: Literal[1, 2, 3, 4, 5]
    evidence_id: str
    quote: str
    source_date: str


class Critique(BaseModel):
    objections: list[Point]


def attack(company: Company, business_model: BusinessModel, ctx: Context) -> list[Objection]:
    settings = ctx.settings
    brief = {
        "Company": describe(company),
        "Business model": (
            f"Payer: {business_model.payer}\n"
            f"Pays for: {business_model.pays_for}\n"
            f"Frequency: {business_model.frequency}"
        ),
        "Team": (
            f"{settings.assumptions.team}; {settings.assumptions.horizon_weeks} weeks; "
            f"market: {settings.assumptions.market}"
        ),
    }
    plan = ctx.llm.ask(
        "critic",
        settings.roles.critic,
        settings.prompt("critic_plan"),
        {**brief, "Limit": f"{settings.critic.search_queries} queries"},
        Plan,
        slug=company.slug,
    )
    search = ctx.search("critic")
    found = [
        page
        for query in plan.queries[: settings.critic.search_queries]
        for page in search.find(query)
    ]
    pages = numbered(found, "S")

    critique = ctx.llm.ask(
        "critic",
        settings.roles.critic,
        settings.prompt("critic"),
        {**brief, "Evidence": show(pages)},
        Critique,
        slug=company.slug,
    )
    strongest_first = sorted(critique.objections, key=lambda point: -point.strength)
    return [
        Objection(
            id=f"O{number}",
            text=point.text,
            reasoning=point.reasoning,
            strength=point.strength,
            source_url=pages[point.evidence_id].url if point.evidence_id in pages else None,
            quote=checked_quote(point.quote, point.evidence_id, pages, ctx) or None,
            source_date=point.source_date or None,
        )
        for number, point in enumerate(strongest_first, 1)
    ]
