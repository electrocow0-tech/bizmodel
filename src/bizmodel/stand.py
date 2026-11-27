"""Собирает из готового прогона статический стенд в папку docs/."""

import hashlib
import re
import shutil
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import markdown
import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup

from bizmodel.schemas import Card, Cost, Decision, Gate, Objection, Run, TreeResult

STAND = Path(__file__).resolve().parents[2] / "stand"
NO_DATE = '<span class="quiet">нет</span>'
VOTE_EXAMPLE_ORDER = {"arbiter": 0, "human": 1, "unresolved": 1}
BRANCH_ORDER = ("yes", "no", "unknown")
PROFILES = ("showcase", "dev")
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
            how=_how(run),
            launch=_launch(run),
            dropped=_dropped(run),
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


def _how(run: Run) -> dict:
    """Схема конвейера: числа над этапами и факты, которые открываются по нажатию на этап."""
    funnel = run.funnel
    pipeline = run.config.get("pipeline", {})
    checked = _checked(run)
    advised = sum(1 for card in run.cards if card.advice)
    counts = [
        funnel.sourced,
        funnel.queued + funnel.deep_checked,
        funnel.deep_checked,
        funnel.gate_passed,
        funnel.carded,
        advised,
        funnel.carded,
    ]
    voters = len(run.voters)
    stages = [
        ("catalog", "Каталог", "код"),
        ("filter", "Дешёвый фильтр", "дешёвая модель"),
        (
            "gate",
            "Проверка по критериям",
            f"{voters} моделей, решение при {run.quorum} из {voters}",
        ),
        ("agents", "Критик и проверяющий", "два агента, не видят друг друга"),
        ("card", "Карточка", "код считает балл"),
        ("advisor", "Советник", "модель, на балл не влияет"),
        ("rating", "Рейтинг", "код"),
    ]
    vote = _vote_example(checked)
    top = min(run.cards, key=lambda card: card.rank, default=None)
    return {
        "stages": [
            {
                "key": key,
                "title": title,
                "who": who,
                "count": count if index == 0 or count != counts[index - 1] else None,
            }
            for index, ((key, title, who), count) in enumerate(zip(stages, counts, strict=True))
        ],
        "source": pipeline.get("source") or {},
        "funnel": pipeline.get("funnel") or {},
        "reasons": _rejection_reasons(run)[:3],
        "path": _example_path(run, vote),
        "refusals": _refusals(run),
        "open_questions": _open_questions(run),
        "isolation": _isolation_example(run, top),
        "verdicts": Counter(_verdict_key(o) for card in run.cards for o in card.objections),
        "rubrics": run.config.get("scoring", {}).get("rubrics", []),
        "advice": Counter(card.advice.verdict for card in run.cards if card.advice),
        "best": sorted(run.cards, key=lambda card: card.rank)[:3],
        "top": top,
        "flow": {
            "sourced": funnel.sourced,
            "filtered": funnel.queued + funnel.deep_checked,
            "deep": funnel.deep_checked,
            "passed": funnel.gate_passed,
            "carded": funnel.carded,
        },
    }


def _rejection_reasons(run: Run) -> list[dict]:
    titles = {
        tree["id"]: tree["title"] for tree in run.config.get("criteria", {}).get("trees", [])
    } | {tree.tree_id: tree.title for gate in run.gates for tree in gate.trees}
    counts = Counter(
        prescreen.violations[0].criterion
        for prescreen in run.prescreens
        if prescreen.status == "rejected" and prescreen.violations
    )
    return [
        {"title": titles.get(criterion, criterion), "count": count}
        for criterion, count in counts.most_common()
    ]


def _checked(run: Run) -> list[Gate]:
    """Компании глубокой проверки, без контрольной выборки отказов."""
    return [gate for gate in run.gates if gate.slug not in run.control.slugs]


def _refusals(run: Run) -> list[dict]:
    return [
        {"company": run.companies[gate.slug].name, "tree": tree}
        for gate in _checked(run)
        if gate.outcome == "fail"
        for tree in gate.trees
        if tree.outcome == "fail"
    ]


def _dropped(run: Run) -> dict:
    """Кто не дошёл до карточки и почему: коротко, для свёрнутой строки под рейтингом."""
    funnel = run.funnel
    return {
        "total": funnel.prescreen_rejected + funnel.gate_failed + funnel.gate_unknown,
        "by_description": funnel.prescreen_rejected,
        "reasons": _rejection_reasons(run)[:3],
        "refusals": _refusals(run),
        "unknown": [
            run.companies[gate.slug].name for gate in _checked(run) if gate.outcome == "unknown"
        ],
        "queued": funnel.queued,
        "deep": funnel.deep_checked,
    }


def _example_path(run: Run, vote: dict | None) -> dict | None:
    if not vote:
        return None
    gate, decision = vote["gate"], vote["decision"]
    tree = next(tree for tree in gate.trees if decision.question_id in tree.path)
    passports = {passport.id: passport for passport in gate.passports}
    answers = {
        item.question_id: {"decision": item, "passport": passports.get(item.passport_id)}
        for item in gate.decisions
    }
    return {"company": run.companies[gate.slug].name, "tree": tree, "steps": _steps(tree, answers)}


def _steps(tree: TreeResult, answers: dict[str, dict]) -> list[dict]:
    """Исход дерева несёт последний пройденный узел, узлы до него пройдены без замечаний."""
    closing = {"pass": "ok", "fail": "hit", "unknown": "part"}[tree.outcome]
    last = len(tree.path) - 1
    return [
        answers[question] | {"state": closing if index == last else "ok"}
        for index, question in enumerate(tree.path)
        if question in answers
    ]


def _open_questions(run: Run) -> list[dict]:
    """По компании со статусом «не удалось проверить»: вопросы, от которых зависит её исход."""
    companies = []
    for gate in _checked(run):
        if gate.outcome != "unknown":
            continue
        decisions = {decision.question_id: decision for decision in gate.decisions}
        questions = [
            decisions[tree.path[-1]].question for tree in gate.trees if tree.outcome == "unknown"
        ]
        companies.append({"company": run.companies[gate.slug].name, "questions": questions})
    return companies


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


def _isolation_example(run: Run, card: Card | None) -> dict | None:
    usable = [check for check in run.isolation if check.verifier]
    own = [check for check in usable if card and check.slug == card.slug]
    check = (own or usable or [None])[0]
    if not check:
        return None
    return {
        "company": run.companies[check.slug].name,
        "critic": [_input_name(part) for part in check.critic.inputs],
        "verifier": [_input_name(part) for part in check.verifier[0].inputs],
        "leaks": sum(1 for item in run.isolation if item.leaked),
        "checks": len(run.isolation),
    }


def _input_name(part: str) -> str:
    """Во входах записан отпечаток каждой части запроса: человеку он не нужен."""
    return re.sub(r"\s*\([0-9a-f]{8,}\)$", "", part)


def _launch(run: Run) -> dict:
    """Значения формы запуска берутся из конфига этого прогона."""
    config = run.config
    pipeline = config.get("pipeline", {})
    source = pipeline.get("source") or {}
    funnel = pipeline.get("funnel") or {}
    assumptions = pipeline.get("assumptions") or {}
    rubrics = config.get("scoring", {}).get("rubrics", [])
    providers = config.get("models", {}).get("providers", {})
    profiles = config.get("models", {}).get("profiles", {})
    stand = pipeline.get("stand") or {}
    budgets = stand.get("budget_usd") or {
        name: provider["budget_usd"]
        for name, provider in providers.items()
        if provider.get("budget_usd") is not None
    }
    industries = Counter(company.industry for company in run.companies.values()).most_common()
    return {
        "industries": industries,
        "rubrics": [{"id": rubric["id"], "title": rubric["title"]} for rubric in rubrics],
        "profiles": [
            {"key": key, "voters": len(profiles[key].get("voters", []))}
            for key in PROFILES
            if key in profiles
        ],
        "trees": [_tree_map(tree) for tree in config.get("criteria", {}).get("trees", [])],
        "data": {
            "runId": run.id,
            "liveUrl": stand.get("live_url"),
            "lastCost": round(sum(run.spent.values()) or sum(cost.usd for cost in run.costs), 2),
            "budgets": budgets,
            "costs": _cost_shares(run.costs),
            "measured": {"sample": run.funnel.sourced, "deep": run.funnel.deep_checked},
            "defaults": {
                "sample_size": source.get("sample_size", run.funnel.sourced),
                "deep_check": funnel.get("deep_check", run.funnel.deep_checked),
                "industries": [name for name, _ in industries],
                "weights": {rubric["id"]: rubric["weight"] for rubric in rubrics},
                "assumptions": {
                    "team": assumptions.get("team", ""),
                    "test_budget_usd": assumptions.get("test_budget_usd", 0),
                    "horizon_weeks": assumptions.get("horizon_weeks", 0),
                },
                "profile": run.profile if run.profile in profiles else pipeline.get("profile"),
                "max_usd": min(stand.get("run_usd", 5), sum(budgets.values())),
            },
        },
    }


def _cost_shares(costs: list[Cost]) -> dict:
    """Расход прогона по провайдерам: отдельно дешёвый слой, отдельно всё после него."""
    shares: dict[str, dict[str, float]] = {}
    for cost in costs:
        stage = "prescreen" if cost.role == "prescreen" else "deep"
        provider = shares.setdefault(cost.provider, {"prescreen": 0.0, "deep": 0.0})
        provider[stage] = round(provider[stage] + cost.usd, 4)
    return shares


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
