"""Глубокая проверка по критериям: свидетельства из сети, голоса моделей, арбитр при расхождении."""

from collections import Counter
from dataclasses import replace
from datetime import date

from pydantic import BaseModel

from bizmodel import dataset, forest
from bizmodel.context import Context
from bizmodel.evidence import checked_quote, numbered, show
from bizmodel.llm import StepFailed, render
from bizmodel.prescreen import describe
from bizmodel.schemas import Answer, Company, Decision, Gate, Passport, Vote
from bizmodel.search import Page

IN_RUSSIAN = {"yes": "да", "no": "нет", "unknown": "не удалось проверить"}


class SearchPlan(BaseModel):
    comparable: str
    queries: list[str]


class Reply(BaseModel):
    question_id: str
    answer: Answer
    evidence_id: str
    quote: str


class Ballot(BaseModel):
    replies: list[Reply]


class Ruling(BaseModel):
    question_id: str
    answer: Answer
    evidence_id: str
    quote: str
    why: str


class Rulings(BaseModel):
    rulings: list[Ruling]


def check(company: Company, ctx: Context) -> Gate:
    trees = ctx.settings.forest
    pages, comparable = gather(company, ctx)
    sections = {
        "Company": describe(company),
        "Comparable candidate": (
            f"{comparable or 'none proposed'}\n"
            "Proposed from memory by the search planner. A lead to check, not a fact."
        ),
        "Questions": "\n".join(f"- {id}: {node.ask}" for id, node in trees.questions.items()),
        "Evidence": show(pages),
    }
    votes = collect_votes(company, sections, pages, ctx)
    split = [id for id, cast in votes.items() if not quorum_answer(cast, ctx)]
    rulings = arbitrate(company, sections, split, pages, ctx)
    decisions, passports = {}, {}
    for id, cast in votes.items():
        decisions[id], passports[id] = decide(company, id, cast, rulings.get(id), pages, ctx)

    results = [forest.walk(tree, lambda id: decisions[id].answer) for tree in trees.trees]
    walked = [id for result in results for id in result.path]
    dataset.remember(
        ctx.cache / "dataset" / "gate.jsonl",
        system=ctx.settings.prompt("voter"),
        user=render(sections),
        answer={id: decisions[id].answer for id in walked},
        meta={"slug": company.slug, "forest": trees.version},
    )
    return Gate(
        slug=company.slug,
        outcome=forest.overall(results),
        trees=results,
        decisions=[decisions[id] for id in walked],
        evidence=[page.evidence(id) for id, page in pages.items()],
        passports=[passports[id] for id in walked],
        forest_version=trees.version,
    )


def gather(company: Company, ctx: Context) -> tuple[dict[str, Page], str]:
    search = ctx.search("gate")
    pages = [
        Page(
            url=company.yc_url,
            title=f"{company.name} in the YC directory",
            snippet=f"{company.one_liner}\n{company.description}",
            text=f"{company.one_liner}\n{company.description}",
            published=None,
            accessed=date.today().isoformat(),
        )
    ]
    site = search.fetch(company.website) if company.website else None
    if site:
        pages.append(replace(site, snippet=site.text[: ctx.settings.search.site_chars]))

    questions = ctx.settings.forest.questions.values()
    plan = ctx.llm.ask(
        "planner",
        ctx.settings.roles.planner,
        ctx.settings.prompt("planner"),
        {
            "Company": describe(company),
            "Questions": "\n".join(f"- {node.ask}" for node in questions),
            "Limit": f"{ctx.settings.gate.search_queries} queries",
        },
        SearchPlan,
        slug=company.slug,
    )
    for query in plan.queries[: ctx.settings.gate.search_queries]:
        pages += search.find(query)
    return numbered(pages, "E"), plan.comparable


def collect_votes(
    company: Company, sections: dict[str, str], pages: dict[str, Page], ctx: Context
) -> dict[str, list[Vote]]:
    votes = {question_id: [] for question_id in ctx.settings.forest.questions}
    for voter in ctx.settings.roles.voters:
        try:
            ballot = ctx.llm.ask(
                "voter", voter, ctx.settings.prompt("voter"), sections, Ballot, slug=company.slug
            )
        except StepFailed:
            continue
        name = voter.routes[0].split(":", 1)[1]
        for reply in ballot.replies:
            if reply.question_id in votes:
                votes[reply.question_id].append(
                    Vote(
                        voter=name,
                        answer=reply.answer,
                        evidence_id=reply.evidence_id if reply.evidence_id in pages else "",
                        quote=checked_quote(reply.quote, reply.evidence_id, pages, ctx),
                    )
                )
    return votes


def quorum_answer(votes: list[Vote], ctx: Context) -> Answer | None:
    needed = min(ctx.settings.gate.quorum, len(ctx.settings.roles.voters))
    tally = Counter(vote.answer for vote in votes)
    leader, count = tally.most_common(1)[0] if tally else (None, 0)
    return leader if count >= needed else None


def arbitrate(
    company: Company,
    sections: dict[str, str],
    split: list[str],
    pages: dict[str, Page],
    ctx: Context,
) -> dict[str, Ruling]:
    """Один вызов на компанию по всем спорным вопросам. Голосов арбитр не видит."""
    if not split:
        return {}
    questions = ctx.settings.forest.questions
    try:
        answer = ctx.llm.ask(
            "arbiter",
            ctx.settings.roles.arbiter,
            ctx.settings.prompt("arbiter"),
            {**sections, "Questions": "\n".join(f"- {id}: {questions[id].ask}" for id in split)},
            Rulings,
            slug=company.slug,
        )
    except StepFailed:
        return {}
    return {
        ruling.question_id: ruling.model_copy(
            update={"quote": checked_quote(ruling.quote, ruling.evidence_id, pages, ctx)}
        )
        for ruling in answer.rulings
        if ruling.question_id in split
    }


def decide(
    company: Company,
    question_id: str,
    votes: list[Vote],
    ruling: Ruling | None,
    pages: dict[str, Page],
    ctx: Context,
) -> tuple[Decision, Passport]:
    node = ctx.settings.forest.questions[question_id]
    human = ctx.settings.overrides.get(company.slug, {}).get(question_id)
    by_vote = quorum_answer(votes, ctx)
    backing = None

    if human:
        answer, decided_by = human, "human"
    elif by_vote:
        answer, decided_by = by_vote, "vote"
        backing = next((vote for vote in votes if vote.answer == by_vote and vote.quote), None)
    elif ruling and ruling.answer != "unknown":
        answer, decided_by = ruling.answer, "arbiter"
        if ruling.quote:
            backing = Vote(voter="arbiter", **ruling.model_dump(exclude={"question_id", "why"}))
    else:
        answer, decided_by = "unknown", "unresolved"

    agreement = sum(vote.answer == answer for vote in votes) / len(votes) if votes else 0.0
    if decided_by == "human" or (decided_by == "vote" and backing and agreement == 1):
        confidence = "high"
    else:
        confidence = "medium" if backing else "low"

    source = pages[backing.evidence_id] if backing else None
    passport = Passport(
        id=f"gate.{question_id}",
        claim=f"{node.label}: {IN_RUSSIAN[answer]}",
        origin="gate",
        method=method_of(answer, decided_by, backing),
        confidence=confidence,
        source_url=source.url if source else None,
        quote=backing.quote if backing else None,
        source_date=source.published if source else None,
        accessed=source.accessed if source else None,
        note="Ответ дал человек" if decided_by == "human" else "",
    )
    decision = Decision(
        question_id=question_id,
        question=node.label,
        votes=votes,
        answer=answer,
        agreement=agreement,
        decided_by=decided_by,
        passport_id=passport.id,
    )
    return decision, passport


def method_of(answer: Answer, decided_by: str, backing: Vote | None) -> str:
    if decided_by == "human" or answer == "unknown":
        return "needs_human"
    return "primary_source" if backing else "model_judgment"
