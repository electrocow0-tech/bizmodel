"""Всё, что прогон записывает на диск. Стенд строится только из этих моделей."""

from typing import Any, Literal

from pydantic import BaseModel

Answer = Literal["yes", "no", "unknown"]
Outcome = Literal["pass", "fail", "unknown"]
Method = Literal["primary_source", "calculation", "model_judgment", "needs_human"]
Confidence = Literal["high", "medium", "low"]
Verdict = Literal["supported", "not_supported", "contradicts", "source_unavailable", "no_source"]
RevenueType = Literal[
    "subscription", "usage_fee", "transaction_commission", "one_time", "advertising", "other"
]
PrescreenStatus = Literal["rejected", "queued", "selected", "failed"]
DecidedBy = Literal["vote", "arbiter", "human", "unresolved"]
AdviceVerdict = Literal["launch", "postpone", "needs_human"]


class Company(BaseModel):
    slug: str
    name: str
    one_liner: str
    description: str
    industry: str
    subindustry: str
    tags: list[str]
    batch: str
    team_size: int | None
    website: str
    yc_url: str


class BusinessModel(BaseModel):
    payer: str
    pays_for: str
    frequency: str
    revenue_type: RevenueType


class Violation(BaseModel):
    criterion: str
    reason: str


class Prescreen(BaseModel):
    slug: str
    business_model: BusinessModel
    violations: list[Violation]
    speed: int
    speed_reason: str
    status: PrescreenStatus


class Evidence(BaseModel):
    id: str
    url: str
    title: str
    published: str | None
    accessed: str
    sha256: str


class Passport(BaseModel):
    id: str
    claim: str
    origin: Literal["gate", "critic", "card", "advisor"]
    method: Method
    confidence: Confidence
    source_url: str | None = None
    quote: str | None = None
    source_date: str | None = None
    accessed: str | None = None
    note: str = ""


class Vote(BaseModel):
    voter: str
    answer: Answer
    quote: str = ""
    evidence_id: str = ""


class Decision(BaseModel):
    question_id: str
    question: str
    votes: list[Vote]
    answer: Answer
    agreement: float
    decided_by: DecidedBy
    passport_id: str | None = None


class TreeResult(BaseModel):
    tree_id: str
    title: str
    outcome: Outcome
    path: list[str]
    reason: str


class Gate(BaseModel):
    slug: str
    outcome: Outcome
    trees: list[TreeResult]
    decisions: list[Decision]
    evidence: list[Evidence]
    passports: list[Passport]
    forest_version: str


class Objection(BaseModel):
    id: str
    text: str
    reasoning: str
    strength: int
    source_url: str | None = None
    quote: str | None = None
    source_date: str | None = None
    sent_to_verifier: bool = False
    verdict: Verdict | None = None
    verifier_quote: str | None = None
    verifier_note: str = ""
    passport_id: str | None = None


class Rubric(BaseModel):
    id: str
    title: str
    weight: int
    level: int
    why: str


class TestSketch(BaseModel):
    channel: str
    offer: str
    success_sign: str


class Advice(BaseModel):
    verdict: AdviceVerdict
    test_budget: str
    first_step: str
    main_risk: str
    stop_signal: str
    flagged_numbers: list[str] = []


class Trust(BaseModel):
    by_method: dict[Method, int]
    by_confidence: dict[Confidence, int]
    level: Confidence


class Card(BaseModel):
    slug: str
    name: str
    one_liner: str
    website: str
    yc_url: str
    business_model: BusinessModel
    anchor: str
    score: float
    rank: int
    rubrics: list[Rubric]
    objections: list[Objection]
    test_sketch: TestSketch
    upsell: str
    needs_human: list[str]
    passports: list[Passport]
    trust: Trust
    advice: Advice | None = None


class Funnel(BaseModel):
    sourced: int
    prescreen_rejected: int
    queued: int
    deep_checked: int
    gate_passed: int
    gate_failed: int
    gate_unknown: int
    carded: int
    unverified: int


class ControlSample(BaseModel):
    """Отказы дешёвого слоя, перепроверенные глубокой проверкой.

    Ложный отказ: глубокая проверка не подтвердила ни один критерий, по которому отсеял дешёвый слой.
    """

    slugs: list[str]
    wrongly_rejected: list[str]


class Cost(BaseModel):
    provider: str
    role: str
    model: str
    calls: int
    cached: int
    input_tokens: int
    output_tokens: int
    usd: float


class ValidatorStats(BaseModel):
    schema_retries: int = 0
    schema_failures: int = 0
    quotes_checked: int = 0
    quotes_dropped: int = 0
    advice_numbers_flagged: int = 0
    cards_rejected: int = 0


class AgentCall(BaseModel):
    role: str
    model: str
    input_sha: str
    inputs: list[str]


class Isolation(BaseModel):
    slug: str
    critic: AgentCall
    verifier: list[AgentCall]
    leaked: list[str]


class Failure(BaseModel):
    slug: str
    stage: str
    error: str


class OutageDrill(BaseModel):
    role: str
    failed_route: str
    error: str
    served_by: str
    seconds: float


class GoldenScore(BaseModel):
    labelled: int
    agreed: int
    disagreements: list[str]


class Run(BaseModel):
    id: str
    started: str
    finished: str
    profile: str
    voters: list[str]
    quorum: int
    config: dict[str, Any]
    prompts: dict[str, str]
    funnel: Funnel
    companies: dict[str, Company]
    prescreens: list[Prescreen]
    gates: list[Gate]
    cards: list[Card]
    memo: str
    control: ControlSample
    costs: list[Cost]
    validators: ValidatorStats
    isolation: list[Isolation]
    failures: list[Failure]
    outage_drill: OutageDrill | None = None
    golden: GoldenScore | None = None
