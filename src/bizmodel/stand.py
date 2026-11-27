"""Собирает из готового прогона статический стенд в папку docs/."""

import hashlib
import shutil
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import markdown
import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup

from bizmodel.schemas import Card, Decision, Gate, Isolation, Objection, Run, TreeResult

STAND = Path(__file__).resolve().parents[2] / "stand"
NO_DATE = '<span class="quiet">нет</span>'
VOTE_EXAMPLE_ORDER = {"arbiter": 0, "human": 1, "unresolved": 1}
VERDICT_EXAMPLE_ORDER = {"supported": 0, "contradicts": 1, "not_supported": 2}
ROLE_ORDER = ["prescreen", "planner", "voters", "arbiter", "critic", "verifier", "card", "advisor"]
BRANCH_ORDER = ("yes", "no", "unknown")
PROMPT_ORDER = [
    "prescreen", "planner", "voter", "arbiter", "critic_plan", "critic", "verifier", "card",
    "advisor", "portfolio",
]  # fmt: skip
VERDICT_ORDER = [
    "supported", "contradicts", "not_supported", "source_unavailable", "no_source", "failed", "unchecked",
]  # fmt: skip
MONTHS = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]  # fmt: skip
MONTHS_ALONE = [
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
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
            tour=_tour(run),
            settings=_settings(run),
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
    env.policies["json.dumps_kwargs"] = {"ensure_ascii": False}
    labels, tones = wording["labels"], wording["tones"]
    env.filters["label"] = lambda value, group: labels[group].get(value, value)
    env.filters["tone"] = lambda value, group: tones[group].get(value, "plain")
    env.filters["plural"] = _plural
    env.filters["merged"] = lambda base, extra: base | extra
    env.filters["verdict_key"] = _verdict_key
    env.filters["verdict_counts"] = _verdict_counts
    env.filters["md"] = _markdown
    env.filters["paragraphs"] = _paragraphs
    env.filters["web"] = _web_address
    env.filters["host"] = lambda url: urlparse(url).netloc.removeprefix("www.")
    env.filters["day"] = _day
    env.filters["day_or_none"] = lambda moment: _day(moment) if moment else Markup(NO_DATE)
    env.filters["usd"] = lambda amount: f"{amount:.2f}".replace(".", ",")
    env.filters["thousands"] = lambda number: f"{number:,}".replace(",", " ")
    return env


def _verdict_key(objection: Objection) -> str:
    """Возражение без отправки проверяющему не проверялось, отправленное без вердикта сорвалось."""
    if not objection.sent_to_verifier:
        return "unchecked"
    return objection.verdict or "failed"


def _verdict_counts(card: Card) -> list[tuple[str, int]]:
    counts = Counter(_verdict_key(objection) for objection in card.objections)
    return [(key, counts[key]) for key in VERDICT_ORDER if counts[key]]


def _plural(number: int, one: str, few: str, many: str) -> str:
    if number % 10 == 1 and number % 100 != 11:
        return one
    if number % 10 in (2, 3, 4) and number % 100 not in (12, 13, 14):
        return few
    return many


def _markdown(text: str) -> Markup:
    """Только для документов из репозитория: их разметка считается доверенной.

    Заголовок первого уровня снимается: его место занимает заголовок вкладки.
    """
    lines = text.strip().splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    return Markup(markdown.markdown("\n".join(lines), extensions=["tables"]))


def _paragraphs(text: str) -> Markup:
    """Текст от модели выводится экранированными абзацами, без разметки."""
    parts = [part.strip() for part in text.split("\n\n") if part.strip()]
    return Markup("").join(Markup("<p>{}</p>").format(part) for part in parts)


def _web_address(url: str | None) -> str:
    """Адреса приходят из каталога и поиска: в ссылку идут только http и https."""
    return url if url and urlparse(url).scheme in ("http", "https") else "#"


def _day(moment: str) -> str:
    """Источники дают дату целиком, только месяц или только год: показываем столько, сколько есть."""
    try:
        numbers = [int(part) for part in moment[:10].split("-")]
    except ValueError:
        return moment
    if len(numbers) == 1:
        return f"{numbers[0]} год"
    if not 1 <= numbers[1] <= 12:
        return moment
    if len(numbers) == 2:
        return f"{MONTHS_ALONE[numbers[1] - 1]} {numbers[0]}"
    return f"{numbers[2]} {MONTHS[numbers[1] - 1]} {numbers[0]}"


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


def _tour(run: Run) -> dict:
    """Примеры для демонстрации берутся из данных прогона: имена компаний заранее не известны."""
    control = set(run.control.slugs)
    checked = [gate for gate in run.gates if gate.slug not in control]
    ranked = sorted(run.cards, key=lambda card: card.rank)
    top = ranked[0] if ranked else None
    return {
        "refusal": _refusal_example(checked),
        "vote": _vote_example(checked),
        "top": top,
        "objection": _objection_example(top),
        "isolation": _isolation_example(run.isolation, top),
        "best": ranked[:3],
    }


def _refusal_example(gates: list[Gate]) -> dict | None:
    for gate in gates:
        tree = next((tree for tree in gate.trees if tree.outcome == "fail"), None)
        if gate.outcome == "fail" and tree:
            return {"gate": gate, "tree": tree}
    return None


def _vote_example(gates: list[Gate]) -> dict | None:
    """Лучше всего механизм видно на вопросе, где решал арбитр, хуже всего на единогласном."""
    candidates = [
        (gate, decision)
        for gate in gates
        for decision in gate.decisions
        if decision.votes and decision.question_id in {q for t in gate.trees for q in t.path}
    ]
    if not candidates:
        return None
    gate, decision = min(candidates, key=lambda pair: _vote_example_rank(pair[1]))
    return {"gate": gate, "decision": decision, "agreed": _agreed(decision)}


def _vote_example_rank(decision: Decision) -> int:
    if decision.decided_by in VOTE_EXAMPLE_ORDER:
        return VOTE_EXAMPLE_ORDER[decision.decided_by]
    if decision.answer == "unknown":
        return 4
    return 2 if decision.agreement < 1 else 3


def _agreed(decision: Decision) -> int:
    return round(decision.agreement * len(decision.votes))


def _objection_example(card: Card | None) -> Objection | None:
    checked = (
        [objection for objection in card.objections if objection.sent_to_verifier] if card else []
    )
    return min(
        checked,
        key=lambda objection: (
            VERDICT_EXAMPLE_ORDER.get(objection.verdict, 3),
            -objection.strength,
        ),
        default=None,
    )


def _isolation_example(checks: list[Isolation], card: Card | None) -> Isolation | None:
    usable = [check for check in checks if check.verifier]
    own = [check for check in usable if card and check.slug == card.slug]
    return (own or usable or [None])[0]


def _settings(run: Run) -> dict:
    """Конфиг прогона в том виде, в каком его читает человек: без имён полей и ключей доступа."""
    config = run.config
    pipeline = config.get("pipeline", {})
    profiles = config.get("models", {}).get("profiles", {})
    profile = run.profile if run.profile in profiles else pipeline.get("profile", "")
    overrides = config.get("overrides") or {}
    return {
        "trees": [_tree_map(tree) for tree in config.get("criteria", {}).get("trees", [])],
        "scoring": config.get("scoring", {}),
        "pipeline": pipeline,
        "profile": profile,
        "roles": _roles(profiles.get(profile, {})),
        "other_profiles": {
            name: _roles(spec) for name, spec in profiles.items() if name != profile
        },
        "budgets": {
            name: provider.get("budget_usd")
            for name, provider in config.get("models", {}).get("providers", {}).items()
        },
        "prices": config.get("models", {}).get("prices", {}),
        "overrides": sum(len(answers) for answers in overrides.values()),
        "open_questions": _open_questions(run),
        "holding": (config.get("holding") or {}).get("companies") or [],
        "prompts": dict(
            sorted(run.prompts.items(), key=lambda item: _position(PROMPT_ORDER, item[0]))
        ),
    }


def _open_questions(run: Run) -> list[dict]:
    """Вопросы, от которых зависит исход компании со статусом «не удалось проверить»."""
    questions = []
    for gate in run.gates:
        if gate.outcome != "unknown" or gate.slug in run.control.slugs:
            continue
        decisions = {decision.question_id: decision for decision in gate.decisions}
        for tree in gate.trees:
            if tree.outcome == "unknown":
                questions.append(
                    {
                        "slug": gate.slug,
                        "company": run.companies[gate.slug].name,
                        "question": decisions[tree.path[-1]].question,
                    }
                )
    return questions


def _tree_map(tree: dict) -> dict:
    """Дерево критерия как список вопросов по порядку обхода, у каждого ответа куда он ведёт."""
    nodes = tree["nodes"]
    order: list[str] = []

    def visit(node_id: str) -> None:
        if node_id in order or node_id not in nodes:
            return
        order.append(node_id)
        for answer in BRANCH_ORDER:
            if isinstance(nodes[node_id].get(answer), str):
                visit(nodes[node_id][answer])

    visit(tree["root"])
    number = {node_id: position for position, node_id in enumerate(order, start=1)}
    questions = []
    for node_id in order:
        branches = []
        for answer in BRANCH_ORDER:
            target = nodes[node_id].get(answer)
            if isinstance(target, str):
                branches.append(
                    {"answer": answer, "next": number[target], "text": nodes[target]["label"]}
                )
            elif isinstance(target, dict):
                [(outcome, reason)] = target.items()
                branches.append({"answer": answer, "outcome": outcome, "text": reason})
        questions.append(
            {"number": number[node_id], "label": nodes[node_id]["label"], "branches": branches}
        )
    return {"title": tree["title"], "questions": questions}


def _roles(profile: dict) -> list[dict]:
    """Строка на каждое место: у голосующих их несколько, подпись роли стоит только у первого."""
    rows = []
    for role in ROLE_ORDER:
        spec = profile.get(role)
        if not spec:
            continue
        seats = spec if role == "voters" else [spec]
        for position, seat in enumerate(seats):
            routes = [_route(route) for route in seat.get("routes", [])]
            rows.append(
                {
                    "role": role if position == 0 else None,
                    "main": routes[0],
                    "fallbacks": routes[1:],
                    "effort": seat.get("effort"),
                }
            )
    return rows


def _position(order: list[str], key: str) -> int:
    return order.index(key) if key in order else len(order)


def _route(route: str) -> dict:
    provider, _, model = route.partition(":")
    return {"provider": provider, "model": model}
