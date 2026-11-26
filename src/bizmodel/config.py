from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, model_validator

from bizmodel import forest
from bizmodel.schemas import Confidence, Verdict


class Provider(BaseModel):
    kind: Literal["anthropic", "openai_compatible"]
    key_env: str
    base_url: str | None = None
    budget_usd: float | None = None


class Chain(BaseModel):
    routes: list[str]
    effort: Literal["low", "medium", "high"] = "low"


class Roles(BaseModel):
    prescreen: Chain
    planner: Chain
    voters: list[Chain]
    arbiter: Chain
    critic: Chain
    verifier: Chain
    card: Chain
    advisor: Chain


class Models(BaseModel):
    providers: dict[str, Provider]
    prices: dict[str, tuple[float, float]]
    profiles: dict[str, Roles]


class Source(BaseModel):
    url: str
    sample_size: int
    seed: int
    min_description_chars: int
    excluded_regions: list[str]


class Funnel(BaseModel):
    deep_check: int
    per_industry_cap: int
    control_sample: int


class GateSettings(BaseModel):
    quorum: int
    search_queries: int


class CriticSettings(BaseModel):
    search_queries: int
    objections_to_verify: int


class SearchSettings(BaseModel):
    results_per_query: int
    snippet_chars: int
    page_chars: int


class Assumptions(BaseModel):
    team: str
    test_budget_usd: int
    horizon_weeks: int
    market: str


class RubricSpec(BaseModel):
    id: str
    title: str
    weight: int
    levels: dict[int, str]
    computed: bool = False


class Scoring(BaseModel):
    rubrics: list[RubricSpec]
    objection_weight: dict[Verdict, float]
    confidence: dict[Confidence, str]
    trust: dict[Literal["high", "medium"], float]

    @model_validator(mode="after")
    def weights_add_up(self):
        total = sum(rubric.weight for rubric in self.rubrics)
        if total != 100:
            raise ValueError(f"rubric weights add up to {total}, expected 100")
        return self


class HoldingCompany(BaseModel):
    name: str
    customers: str


class Settings(BaseModel):
    root: Path
    profile: str
    source: Source
    funnel: Funnel
    gate: GateSettings
    critic: CriticSettings
    search: SearchSettings
    assumptions: Assumptions
    concurrency: int
    models: Models
    scoring: Scoring
    forest: forest.Forest
    holding: list[HoldingCompany]

    @property
    def roles(self) -> Roles:
        return self.models.profiles[self.profile]

    def prompt(self, name: str) -> str:
        return (self.root / "prompts" / f"{name}.md").read_text(encoding="utf-8")


def load(root: Path, profile: str | None = None) -> Settings:
    def read(name: str) -> dict:
        return yaml.safe_load((root / "config" / name).read_text(encoding="utf-8"))

    pipeline = read("pipeline.yaml")
    if profile:
        pipeline["profile"] = profile
    return Settings(
        root=root,
        models=read("models.yaml"),
        scoring=read("scoring.yaml"),
        forest=forest.load(root / "config" / "criteria.yaml"),
        holding=read("holding.yaml")["companies"],
        **pipeline,
    )
