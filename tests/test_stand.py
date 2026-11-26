import re
from pathlib import Path

import pytest

from bizmodel.schemas import Run
from bizmodel.stand import build

FIXTURE = Path(__file__).parent / "fixtures" / "run.json"
CARD_SECTIONS = [
    "scores",
    "objections",
    "advice",
    "test",
    "upsell",
    "human",
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
    build(run, out, {"decisions": "# Почему так\n\nВеса лежат в конфиге.", "limitations": ""})
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
        assert re.findall(r'class="rubric__top"><b>([^<]+)</b>', block) == rubric_titles


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
    assert "<h1>Почему так</h1>" in page
    assert "Список появится здесь после финального прогона." in page


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
