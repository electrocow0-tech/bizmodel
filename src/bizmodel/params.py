"""Что собственник задаёт на стенде перед запуском и сколько это примерно стоит."""

import copy
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from bizmodel.schemas import Run

CHEAP_PROFILE_SHARE = {"anthropic": 0.2, "openrouter": 0.6}


class Assumptions(BaseModel):
    team: str = Field(min_length=1, max_length=200)
    test_budget_usd: int = Field(ge=0, le=10_000_000)
    horizon_weeks: int = Field(ge=1, le=52)


class Params(BaseModel):
    sample_size: int = Field(ge=50, le=300)
    deep_check: int = Field(ge=5, le=20)
    industries: list[str] = Field(min_length=1)
    weights: dict[str, int]
    assumptions: Assumptions
    profile: Literal["showcase", "dev"]
    max_usd: float = Field(gt=0, le=15)

    @model_validator(mode="after")
    def weights_add_up(self):
        if sum(self.weights.values()) != 100:
            raise ValueError("веса шкал должны давать в сумме 100")
        if any(weight < 0 for weight in self.weights.values()):
            raise ValueError("вес шкалы не может быть отрицательным")
        return self

    def apply(self, raw: dict[str, dict]) -> dict[str, dict]:
        """Те же файлы настроек, но с выбором собственника. Исходные файлы не меняются."""
        raw = copy.deepcopy(raw)
        pipeline = raw["pipeline"]
        pipeline["profile"] = self.profile
        pipeline["source"]["sample_size"] = self.sample_size
        pipeline["source"]["industries"] = self.industries
        pipeline["funnel"]["deep_check"] = self.deep_check
        pipeline["assumptions"].update(self.assumptions.model_dump())

        rubrics = raw["scoring"]["rubrics"]
        unknown = set(self.weights) - {rubric["id"] for rubric in rubrics}
        if unknown or len(self.weights) != len(rubrics):
            raise ValueError(f"веса заданы не для тех шкал: {sorted(unknown)}")
        for rubric in rubrics:
            rubric["weight"] = self.weights[rubric["id"]]
        return raw


def estimate(params: Params, reference: Run) -> dict:
    """Оценка сверху по настоящему прогону: стоимость шага на одну компанию, умноженная на число компаний.

    Кеш не учитывается, поэтому повтор с теми же компаниями обойдётся дешевле.
    """
    funnel = reference.funnel
    checked = funnel.deep_checked + len(reference.control.slugs)
    per_company = {
        "prescreen": funnel.sourced,
        "planner": checked,
        "voter": checked,
        "arbiter": checked,
        "critic": funnel.carded,
        "verifier": funnel.carded,
        "card": funnel.carded,
        "advisor": funnel.carded,
    }
    pass_share = funnel.carded / funnel.deep_checked if funnel.deep_checked else 0.5
    control = round(len(reference.control.slugs) * params.deep_check / funnel.deep_checked)
    planned = {
        "prescreen": params.sample_size,
        "planner": params.deep_check + control,
        "voter": params.deep_check + control,
        "arbiter": params.deep_check + control,
        "critic": params.deep_check * pass_share,
        "verifier": params.deep_check * pass_share,
        "card": params.deep_check * pass_share,
        "advisor": params.deep_check * pass_share,
    }

    usd = {"anthropic": 0.0, "openrouter": 0.0}
    for cost in reference.costs:
        done = per_company.get(cost.role) or 1
        usd[cost.provider] += cost.usd / done * planned.get(cost.role, 1)
    if params.profile == "dev":
        usd = {provider: amount * CHEAP_PROFILE_SHARE[provider] for provider, amount in usd.items()}

    minutes = 1 + params.sample_size / 200 + (params.deep_check + control) * 0.3
    return {
        "usd": {provider: round(amount, 2) for provider, amount in usd.items()},
        "minutes": round(minutes),
    }
