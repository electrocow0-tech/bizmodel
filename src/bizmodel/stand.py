"""Собирает из готового прогона статический стенд в папку docs/."""

import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import markdown
import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup

from bizmodel.schemas import Run, TreeResult

STAND = Path(__file__).resolve().parents[2] / "stand"
NO_DATE = '<span class="quiet">нет</span>'
MONTHS = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]  # fmt: skip


def build(run: Run, out: Path, documents: dict[str, str]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    wording = yaml.safe_load((STAND / "labels.yaml").read_text(encoding="utf-8"))
    page = (
        _environment(wording)
        .get_template("page.html.j2")
        .render(
            run=run,
            cards=sorted(run.cards, key=lambda card: card.score),
            forest=_forest(run),
            cheap_layer=_cheap_layer(run),
            spend=_spend(run),
            documents=documents,
            assets=_publish_assets(out),
        )
    )
    (out / "index.html").write_text(page, encoding="utf-8")
    (out / ".nojekyll").touch()


def _environment(wording: dict) -> Environment:
    env = Environment(
        loader=FileSystemLoader(STAND / "templates"),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    labels, tones = wording["labels"], wording["tones"]
    env.filters["label"] = lambda value, group: labels[group].get(value, value)
    env.filters["tone"] = lambda value, group: tones[group].get(value, "plain")
    env.filters["plural"] = _plural
    env.filters["md"] = _markdown
    env.filters["paragraphs"] = _paragraphs
    env.filters["web"] = _web_address
    env.filters["host"] = lambda url: urlparse(url).netloc.removeprefix("www.")
    env.filters["day"] = _day
    env.filters["day_or_none"] = lambda moment: _day(moment) if moment else Markup(NO_DATE)
    env.filters["usd"] = lambda amount: f"{amount:.2f}".replace(".", ",")
    env.filters["thousands"] = lambda number: f"{number:,}".replace(",", " ")
    return env


def _plural(number: int, one: str, few: str, many: str) -> str:
    if number % 10 == 1 and number % 100 != 11:
        return one
    if number % 10 in (2, 3, 4) and number % 100 not in (12, 13, 14):
        return few
    return many


def _markdown(text: str) -> Markup:
    """Только для документов из репозитория: их разметка считается доверенной."""
    return Markup(markdown.markdown(text, extensions=["tables"]))


def _paragraphs(text: str) -> Markup:
    """Текст от модели выводится экранированными абзацами, без разметки."""
    parts = [part.strip() for part in text.split("\n\n") if part.strip()]
    return Markup("").join(Markup("<p>{}</p>").format(part) for part in parts)


def _web_address(url: str | None) -> str:
    """Адреса приходят из каталога и поиска: в ссылку идут только http и https."""
    return url if url and urlparse(url).scheme in ("http", "https") else "#"


def _day(moment: str) -> str:
    date = datetime.fromisoformat(moment)
    return f"{date.day} {MONTHS[date.month - 1]} {date.year}"


def _publish_assets(out: Path) -> dict[str, str]:
    target = out / "assets"
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(STAND / "static", target)
    return {
        path.name: f"assets/{path.name}?v={hashlib.sha256(path.read_bytes()).hexdigest()[:10]}"
        for path in target.iterdir()
        if path.is_file()
    }


def _forest(run: Run) -> list[dict]:
    carded = {card.slug for card in run.cards}
    control = set(run.control.slugs)
    wrongly_rejected = set(run.control.wrongly_rejected)
    companies = []
    for gate in run.gates:
        passports = {passport.id: passport for passport in gate.passports}
        answers = {
            decision.question_id: {
                "decision": decision,
                "passport": passports.get(decision.passport_id),
            }
            for decision in gate.decisions
        }
        walked = {question for tree in gate.trees for question in tree.path}
        companies.append(
            {
                "gate": gate,
                "company": run.companies[gate.slug],
                "is_control": gate.slug in control,
                "wrongly_rejected": gate.slug in wrongly_rejected,
                "has_card": gate.slug in carded,
                "voters": [vote.voter for vote in gate.decisions[0].votes]
                if gate.decisions
                else [],
                "trees": [{"tree": tree, "steps": _steps(tree, answers)} for tree in gate.trees],
                "off_path": [
                    answer for question, answer in answers.items() if question not in walked
                ],
            }
        )
    return sorted(companies, key=lambda company: company["is_control"])


def _steps(tree: TreeResult, answers: dict[str, dict]) -> list[dict]:
    """Исход дерева несёт последний пройденный узел, узлы до него пройдены без замечаний."""
    closing = {"pass": "ok", "fail": "hit", "unknown": "part"}[tree.outcome]
    last = len(tree.path) - 1
    return [
        answers[question] | {"state": closing if index == last else "ok"}
        for index, question in enumerate(tree.path)
        if question in answers
    ]


def _cheap_layer(run: Run) -> dict:
    titles = {tree.tree_id: tree.title for gate in run.gates for tree in gate.trees}
    groups: dict[str, list[dict]] = {}
    for prescreen in run.prescreens:
        if prescreen.status != "rejected" or not prescreen.violations:
            continue
        violation = prescreen.violations[0]
        groups.setdefault(violation.criterion, []).append(
            {"company": run.companies[prescreen.slug], "reason": violation.reason}
        )
    queued = [p for p in run.prescreens if p.status == "queued"]
    return {
        "rejected": [
            {"title": titles.get(criterion, criterion), "companies": rows}
            for criterion, rows in sorted(groups.items(), key=lambda group: -len(group[1]))
        ],
        "queued": [
            {"company": run.companies[p.slug], "prescreen": p}
            for p in sorted(queued, key=lambda p: -p.speed)
        ],
        "failed": [run.companies[p.slug] for p in run.prescreens if p.status == "failed"],
    }


def _spend(run: Run) -> dict:
    by_provider: dict[str, float] = {}
    for cost in run.costs:
        by_provider[cost.provider] = by_provider.get(cost.provider, 0.0) + cost.usd
    return {"by_provider": by_provider, "total": sum(by_provider.values())}
