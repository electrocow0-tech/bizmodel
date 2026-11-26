"""Конвейер целиком, сверху вниз: источник, дешёвый слой, лес, критик, проверяющий, карточка, советник."""

from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from bizmodel import advisor, card, config, critic, gate, prescreen, source, verifier
from bizmodel.context import Context
from bizmodel.journal import Journal
from bizmodel.llm import LLM, StepFailed
from bizmodel.schemas import (
    AgentCall,
    Card,
    Company,
    ControlSample,
    Cost,
    Failure,
    Funnel,
    Isolation,
    Run,
)


def run(root: Path, profile: str | None = None, report: Callable[[str], None] = print) -> Run:
    settings = config.load(root, profile)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = root / "runs" / run_id
    journal = Journal(folder / "calls.jsonl")
    ctx = Context(
        settings=settings,
        llm=LLM(settings.models, journal, root / "cache" / "llm"),
        journal=journal,
        cache=root / "cache",
    )
    started = datetime.now().isoformat(timespec="seconds")
    failures: list[Failure] = []

    companies = source.load(settings.source, root / "data" / "source" / "sample.json")
    by_slug = {company.slug: company for company in companies}
    report(f"Источник: {len(companies)} компаний")

    prescreens = attempt(
        "prescreen", companies, lambda one: prescreen.screen(one, ctx), ctx, failures
    )
    selected, control = prescreen.select(
        list(prescreens.values()),
        {company.slug: company.industry for company in companies},
        settings.funnel,
        settings.source.seed,
    )
    rejected = sum(screened.status == "rejected" for screened in prescreens.values())
    report(f"Дешёвый слой: отсеяно {rejected}, в глубокую проверку {len(selected)}")

    checked = [by_slug[slug] for slug in selected + control]
    gates = attempt("gate", checked, lambda one: gate.check(one, ctx), ctx, failures)
    passed = [by_slug[slug] for slug in selected if slug in gates and gates[slug].outcome == "pass"]
    report(f"Лес: прошли {len(passed)} из {len(selected)}")

    def examine(company: Company) -> Card:
        screened = prescreens[company.slug]
        objections = critic.attack(company, screened.business_model, ctx)
        passports = verifier.check(objections, company.slug, ctx)
        return card.build(company, screened, gates[company.slug], objections, passports, ctx)

    cards = list(attempt("card", passed, examine, ctx, failures).values())
    cards.sort(key=lambda one: (-one.score, one.slug))
    for rank, one in enumerate(cards, 1):
        one.rank = rank

    advice = attempt("advice", cards, lambda one: advisor.advise(one, ctx), ctx, failures)
    for one in cards:
        one.advice = advice.get(one.slug)
    try:
        memo = advisor.portfolio(cards, ctx) if cards else ""
    except StepFailed as error:
        memo = ""
        failures.append(Failure(slug="", stage="portfolio", error=str(error)))
    report(f"Карточек: {len(cards)}, не проверено из-за сбоев: {len({f.slug for f in failures})}")

    outcomes = [gates[slug].outcome for slug in selected if slug in gates]
    result = Run(
        id=run_id,
        started=started,
        finished=datetime.now().isoformat(timespec="seconds"),
        profile=settings.profile,
        funnel=Funnel(
            sourced=len(companies),
            prescreen_rejected=rejected,
            queued=sum(screened.status == "queued" for screened in prescreens.values()),
            deep_checked=len(selected),
            gate_passed=outcomes.count("pass"),
            gate_failed=outcomes.count("fail"),
            gate_unknown=outcomes.count("unknown"),
            carded=len(cards),
            unverified=len({failure.slug for failure in failures if failure.slug}),
        ),
        companies=by_slug,
        prescreens=list(prescreens.values()),
        gates=list(gates.values()),
        cards=cards,
        memo=memo,
        control=ControlSample(
            slugs=control,
            wrongly_rejected=[
                slug for slug in control if slug in gates and gates[slug].outcome == "pass"
            ],
        ),
        costs=costs(journal),
        validators=ctx.stats.model_copy(
            update={
                "schema_retries": ctx.llm.schema_retries,
                "schema_failures": ctx.llm.schema_failures,
            }
        ),
        isolation=isolation(journal, [one.slug for one in cards]),
        failures=failures,
    )
    (folder / "run.json").write_text(result.model_dump_json(indent=1), encoding="utf-8")
    return result


def attempt(stage: str, items: list, work: Callable, ctx: Context, failures: list[Failure]) -> dict:
    """Шаг для каждой компании. Сбой одной не останавливает остальных: она помечается непроверенной."""

    def one(item):
        try:
            return work(item)
        except StepFailed as error:
            return error

    with ThreadPoolExecutor(ctx.settings.concurrency) as pool:
        results = list(pool.map(one, items))

    done = {}
    for item, result in zip(items, results):
        if isinstance(result, StepFailed):
            failures.append(Failure(slug=item.slug, stage=stage, error=str(result)))
        else:
            done[item.slug] = result
    return done


def costs(journal: Journal) -> list[Cost]:
    totals = defaultdict(lambda: defaultdict(float))
    for call in journal.read("llm_call"):
        provider, model = call["route"].split(":", 1)
        total = totals[provider, call["role"], model]
        total["calls"] += 1
        total["cached"] += call["cached"]
        total["input_tokens"] += call["input_tokens"]
        total["output_tokens"] += call["output_tokens"]
        total["usd"] += call["usd"]
    return [
        Cost(
            provider=provider,
            role=role,
            model=model,
            calls=int(total["calls"]),
            cached=int(total["cached"]),
            input_tokens=int(total["input_tokens"]),
            output_tokens=int(total["output_tokens"]),
            usd=round(total["usd"], 4),
        )
        for (provider, role, model), total in sorted(totals.items())
    ]


def isolation(journal: Journal, slugs: list[str]) -> list[Isolation]:
    """Что на самом деле получили на вход критик и проверяющий: названия разделов и хеши."""

    def calls(slug: str, role: str) -> list[AgentCall]:
        return [
            AgentCall(
                role=role,
                model=call["route"],
                input_sha=call["input_sha"],
                inputs=[f"{title} ({digest})" for title, digest in call["inputs"].items()],
            )
            for call in journal.read("llm_call")
            if call["slug"] == slug and call["role"] == role
        ]

    checks = journal.read("isolation_check")
    return [
        Isolation(
            slug=slug,
            critic=calls(slug, "critic")[-1],
            verifier=calls(slug, "verifier"),
            leaked=[leak for check in checks if check["slug"] == slug for leak in check["leaked"]],
        )
        for slug in slugs
    ]
