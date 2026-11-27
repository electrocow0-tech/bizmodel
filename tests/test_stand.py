import json
import re
from pathlib import Path

import pytest

from bizmodel.schemas import Run
from bizmodel.stand import build

FIXTURE = Path(__file__).parent / "fixtures" / "run.json"
CARD_SECTIONS = [
    "advice",
    "risk",
    "test",
    "scores",
    "objections",
    "human",
    "upsell",
    "trust",
    "anchor",
    "passports",
]


@pytest.fixture(scope="module")
def run() -> Run:
    return Run.model_validate_json(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def site(run: Run, tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("stand")
    build(
        run,
        out,
        {
            "decisions": "# Почему так\n\nВеса лежат в конфиге.",
            "limitations": "",
            "full_version": "",
        },
    )
    return out


@pytest.fixture(scope="module")
def page(site: Path) -> str:
    return (site / "index.html").read_text(encoding="utf-8")


def card_blocks(page: str) -> dict[str, str]:
    rating = page[page.index('id="panel-rating"') : page.index('id="panel-compare"')]
    blocks = rating.split('<li class="card foldable"')[1:]
    return {re.search(r'data-slug="([^"]+)"', block).group(1): block for block in blocks}


def test_every_card_is_on_the_page(run: Run, page: str):
    blocks = card_blocks(page)

    assert set(blocks) == {card.slug for card in run.cards}
    for card in run.cards:
        assert card.name in blocks[card.slug]
        assert f'data-col="{card.slug}"' in page


def test_cards_share_one_structure(run: Run, page: str):
    rubric_titles = [rubric.title for rubric in run.cards[0].rubrics]

    for block in card_blocks(page).values():
        assert re.findall(r'data-section="(\w+)"', block) == CARD_SECTIONS
        assert re.findall(r'class="rubric__name">([^<]+)</span>', block) == rubric_titles


def test_rating_runs_from_weak_to_promising(run: Run, page: str):
    weakest_first = [card.slug for card in sorted(run.cards, key=lambda card: card.score)]

    assert list(card_blocks(page)) == weakest_first


def test_compare_columns_have_equal_rows(run: Run, page: str):
    compare = page[page.index('id="panel-compare"') : page.index('id="panel-forest"')]
    columns = compare.split('<div class="cmp__col')[1:]

    assert len(columns) == len(run.cards) + 1
    assert len({column.count('class="cmp__cell') for column in columns}) == 1


def test_every_checked_company_has_its_path(run: Run, page: str):
    for gate in run.gates:
        assert f'id="gate-{gate.slug}"' in page


def test_documents_are_rendered_or_announced(page: str):
    decisions = page[page.index('id="panel-decisions"') : page.index('id="panel-improve"')]
    improve = page[page.index('id="panel-improve"') :]

    assert "Веса лежат в конфиге." in decisions
    assert "<h1>Почему так</h1>" not in decisions
    assert "Список появится здесь после финального прогона." in improve
    assert "Полная версия" in improve


def test_page_loads_nothing_from_outside(site: Path, page: str):
    linked = re.findall(r'<(?:link|script)[^>]+(?:href|src)="([^"]+)"', page)

    assert linked
    for address in linked:
        path, _, version = address.partition("?v=")
        assert (site / path).is_file()
        assert version
    assert (site / ".nojekyll").exists()


def test_model_text_cannot_inject_markup(tmp_path):
    run = Run.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    run.memo = "Первый абзац.\n\n<script>alert(1)</script> **не разметка**"
    build(run, tmp_path, {"decisions": "", "limitations": ""})
    page = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt; **не разметка**" in page


def test_only_web_addresses_become_links(tmp_path):
    run = Run.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    run.cards[0].yc_url = "javascript:alert(1)"
    build(run, tmp_path, {"decisions": "", "limitations": ""})
    assert "javascript:alert(1)" not in (tmp_path / "index.html").read_text(encoding="utf-8")


def test_partial_source_dates_are_shown_as_given(tmp_path):
    run = Run.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    run.cards[0].objections[0].source_date = "2026-01"
    run.cards[0].passports[0].source_date = "2025"
    build(run, tmp_path, {"decisions": "", "limitations": ""})
    page = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "январь 2026" in page
    assert "2025 год" in page


def tour_steps(page: str) -> list[dict]:
    found = re.search(
        r'<script type="application/json" id="tour-steps">(.*?)</script>', page, re.DOTALL
    )
    return json.loads(found.group(1))


def test_tour_targets_exist_in_the_page(page: str):
    steps = tour_steps(page)

    assert steps[-1]["final"] is True
    assert sum(not step.get("final") for step in steps) == 12
    for step in steps:
        for element in [step["target"], *step["open"]]:
            assert f'id="{element}"' in page, (step["title"], element)


def test_tour_uses_voters_and_quorum_of_the_run(run: Run, page: str):
    votes = next(step for step in tour_steps(page) if step["title"] == "Голоса моделей")

    assert f"согласны {run.quorum} из {len(run.voters)}" in votes["text"]


def test_tour_skips_examples_the_run_does_not_have(tmp_path):
    run = Run.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    run.gates = [gate for gate in run.gates if gate.outcome != "fail"]
    for gate in run.gates:
        for decision in gate.decisions:
            decision.decided_by = "vote"
    build(run, tmp_path, {"decisions": "", "limitations": ""})
    page = (tmp_path / "index.html").read_text(encoding="utf-8")
    steps = tour_steps(page)

    assert "Отказ с причиной" not in [step["title"] for step in steps]
    assert "решал арбитр" not in next(s for s in steps if s["title"] == "Голоса моделей")["text"]
    for step in steps:
        assert f'id="{step["target"]}"' in page


def test_settings_speak_plainly(run: Run, page: str):
    settings = page[page.index('id="panel-settings"') : page.index('id="panel-decisions"')]
    unresolved = sum(
        tree.outcome == "unknown"
        for g in run.gates
        if g.outcome == "unknown" and g.slug not in run.control.slugs
        for tree in g.trees
    )

    assert settings.count('class="box__title"') == len(run.config["criteria"]["trees"])
    assert f"Открытые вопросы этого прогона: {unresolved}" in settings
    assert "API_KEY" not in page
    assert "key_env" not in page
    for role in run.prompts:
        assert '<pre class="prompt">' in settings, role
