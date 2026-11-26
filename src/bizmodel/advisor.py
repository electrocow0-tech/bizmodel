"""Финансовый советник читает готовую карточку и говорит собственнику, что делать.

На балл и место он не влияет. Каждая сумма и каждый процент в совете должны быть
в карточке или в допущениях из конфига: это проверяет код.
"""

from pydantic import BaseModel

from bizmodel.context import Context
from bizmodel.schemas import Advice, AdviceVerdict, Card
from bizmodel.validate import foreign_numbers


class Counsel(BaseModel):
    verdict: AdviceVerdict
    test_budget: str
    first_step: str
    main_risk: str
    stop_signal: str


class Memo(BaseModel):
    memo: str


def advise(card: Card, ctx: Context) -> Advice:
    sections = {"Card": card.model_dump_json(exclude={"passports"}), **assumptions(ctx)}
    known = card.model_dump_json() + " ".join(sections.values())
    counsel, flagged = within_facts("advisor", sections, known, Counsel, card.slug, ctx)
    return Advice(**counsel.model_dump(), flagged_numbers=flagged)


def portfolio(cards: list[Card], ctx: Context) -> str:
    summaries = "\n\n".join(
        f"{card.name}: rank {card.rank} of {len(cards)}, score {card.score:g}\n"
        f"Model: {card.business_model.payer} / {card.business_model.pays_for}\n"
        f"Scales: {', '.join(f'{rubric.title} {rubric.level}/5' for rubric in card.rubrics)}\n"
        f"Adviser verdict: {card.advice.verdict if card.advice else 'none'}\n"
        f"Main risk: {card.advice.main_risk if card.advice else 'unknown'}\n"
        f"Open questions: {'; '.join(card.needs_human) or 'none'}"
        for card in sorted(cards, key=lambda card: card.rank)
    )
    sections = {"Cards": summaries, **assumptions(ctx)}
    memo, _ = within_facts("portfolio", sections, " ".join(sections.values()), Memo, "", ctx)
    return memo.memo


def within_facts(
    prompt: str, sections: dict[str, str], known: str, answer, slug: str, ctx: Context
):
    """Ответ с числами не из входных данных отправляется на одну переделку."""
    system = ctx.settings.prompt(prompt)
    chain = ctx.settings.roles.advisor
    reply = ctx.llm.ask("advisor", chain, system, sections, answer, slug=slug)
    flagged = foreign_numbers(" ".join(reply.model_dump().values()), known)
    if not flagged:
        return reply, []

    redo = {**sections, "Rejected figures": "Not in the input, remove them: " + ", ".join(flagged)}
    reply = ctx.llm.ask("advisor", chain, system, redo, answer, slug=slug)
    flagged = foreign_numbers(" ".join(reply.model_dump().values()), known)
    if flagged:
        ctx.count("advice_numbers_flagged")
    return reply, flagged


def assumptions(ctx: Context) -> dict[str, str]:
    given = ctx.settings.assumptions
    holding = "\n".join(
        f"- {company.name}: {company.customers}" for company in ctx.settings.holding
    )
    return {
        "Assumptions": (
            f"Team: {given.team}\nTest budget: {given.test_budget_usd} USD\n"
            f"Horizon: {given.horizon_weeks} weeks\nMarket: {given.market}"
        ),
        "Holding companies": holding or "none listed",
    }
