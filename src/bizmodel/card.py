"""Карточка: одна структура на все модели. Уровни по шкалам выставляет модель, балл считает код."""

from collections import Counter
from typing import Literal

from pydantic import BaseModel

from bizmodel.config import Scoring
from bizmodel.context import Context
from bizmodel.llm import StepFailed
from bizmodel.prescreen import describe
from bizmodel.schemas import (
    Card,
    Company,
    Gate,
    Objection,
    Passport,
    Prescreen,
    Rubric,
    TestSketch,
    Trust,
)
from bizmodel.validate import card_problems


class Scored(BaseModel):
    rubric: str
    level: Literal[1, 2, 3, 4, 5]
    why: str


class Draft(BaseModel):
    anchor: str
    scores: list[Scored]
    channel: str
    offer: str
    success_sign: str
    upsell: str
    needs_human: list[str]


def build(
    company: Company,
    prescreen: Prescreen,
    gate: Gate,
    objections: list[Objection],
    objection_passports: list[Passport],
    ctx: Context,
) -> Card:
    scoring = ctx.settings.scoring
    draft = ctx.llm.ask(
        "card",
        ctx.settings.roles.card,
        ctx.settings.prompt("card"),
        brief(company, prescreen, gate, objections, ctx),
        Draft,
        slug=company.slug,
    )
    by_model = {scored.rubric: scored for scored in draft.scores}
    rubrics = []
    for spec in scoring.rubrics:
        if spec.computed:
            level, why = objections_level(objections, scoring)
        elif spec.id in by_model:
            level, why = by_model[spec.id].level, by_model[spec.id].why
        else:
            ctx.count("cards_rejected")
            raise StepFailed(f"card: scale {spec.id} was left unscored")
        rubrics.append(
            Rubric(id=spec.id, title=spec.title, weight=spec.weight, level=level, why=why)
        )

    score = total(rubrics)
    passports = gate.passports + objection_passports
    passports.append(
        Passport(
            id="score",
            claim=f"Итоговый балл {score:g} из 100",
            origin="card",
            method="calculation",
            confidence="medium",
            note="Сумма по шкалам: вес * (уровень - 1) / 4",
        )
    )
    card = Card(
        slug=company.slug,
        name=company.name,
        one_liner=company.one_liner,
        website=company.website,
        yc_url=company.yc_url,
        business_model=prescreen.business_model,
        anchor=draft.anchor,
        score=score,
        rank=0,
        rubrics=rubrics,
        objections=objections,
        test_sketch=TestSketch(
            channel=draft.channel, offer=draft.offer, success_sign=draft.success_sign
        ),
        upsell=draft.upsell,
        needs_human=draft.needs_human,
        passports=passports,
        trust=trust_in(passports, scoring),
    )
    problems = card_problems(card, {spec.id: spec.weight for spec in scoring.rubrics})
    if problems:
        ctx.count("cards_rejected")
        raise StepFailed(f"card: {'; '.join(problems)}")
    return card


def total(rubrics: list[Rubric]) -> float:
    return sum(rubric.weight * (rubric.level - 1) / 4 for rubric in rubrics)


def objections_level(objections: list[Objection], scoring: Scoring) -> tuple[int, str]:
    """Чем сильнее возражения, пережившие проверку, тем ниже уровень. Считается без модели."""
    checked = [objection for objection in objections if objection.sent_to_verifier]
    if not checked:
        return 5, "Критик не выдвинул возражений"
    burden = sum(
        objection.strength / 5 * scoring.objection_weight[objection.verdict or "source_unavailable"]
        for objection in checked
    )
    verdicts = Counter(objection.verdict for objection in checked)
    open_questions = (
        len(checked) - verdicts["supported"] - verdicts["not_supported"] - verdicts["contradicts"]
    )
    why = (
        f"Из {len(checked)} сильнейших возражений источником подтверждено {verdicts['supported']}, "
        f"без проверяемого источника осталось {open_questions}"
    )
    return 5 - round(4 * burden / len(checked)), why


def trust_in(passports: list[Passport], scoring: Scoring) -> Trust:
    facts = [passport for passport in passports if passport.origin in ("gate", "critic")]
    backed = sum(passport.method == "primary_source" for passport in facts)
    share = backed / len(facts) if facts else 0.0
    if share >= scoring.trust["high"]:
        level = "high"
    elif share >= scoring.trust["medium"]:
        level = "medium"
    else:
        level = "low"
    return Trust(
        by_method=Counter(passport.method for passport in passports),
        by_confidence=Counter(passport.confidence for passport in passports),
        level=level,
    )


def brief(
    company: Company, prescreen: Prescreen, gate: Gate, objections: list[Objection], ctx: Context
) -> dict[str, str]:
    settings = ctx.settings
    model = prescreen.business_model
    scales = [spec for spec in settings.scoring.rubrics if not spec.computed]
    return {
        "Company": describe(company),
        "Business model": (
            f"Payer: {model.payer}\nPays for: {model.pays_for}\n"
            f"Frequency: {model.frequency}\nRevenue type: {model.revenue_type}"
        ),
        "Screening facts": "\n".join(
            f"- {passport.claim} [{passport.method}, {passport.confidence}]"
            + (f' "{passport.quote}" ({passport.source_url})' if passport.quote else "")
            for passport in gate.passports
        ),
        "Critic's objections": "\n".join(
            f"- strength {objection.strength}/5, verdict {objection.verdict or 'not_checked'}: "
            f"{objection.text} {objection.verifier_note}"
            for objection in objections
        ),
        "Team assumptions": (
            f"Team: {settings.assumptions.team}\n"
            f"Test budget: {settings.assumptions.test_budget_usd} USD\n"
            f"Horizon: {settings.assumptions.horizon_weeks} weeks\n"
            f"Market: {settings.assumptions.market}"
        ),
        "Holding companies": "\n".join(
            f"- {company.name}: {company.customers}" for company in settings.holding
        )
        or "none listed",
        "Scales to score": "\n\n".join(
            f"{spec.id} ({spec.title})\n"
            + "\n".join(f"  {level}: {text}" for level, text in sorted(spec.levels.items()))
            for spec in scales
        ),
    }
