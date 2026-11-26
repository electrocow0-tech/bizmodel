"""Проверки, которые делает код, а не ещё одна модель."""

import re

from bizmodel.schemas import Card

MIN_FRAGMENT = 10
_SPACES = re.compile(r"\s+")
_ELLIPSIS = re.compile(r"\.{3,}|…|\[\.\.\.\]")
_LOOKALIKES = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-", " ": " "})
_MONEY_OR_SHARE = re.compile(
    r"[$€£]\s?\d[\d\s.,]*\s?(?:[kKmMbB]|тыс|млн|млрд)?"
    r"|\d[\d\s.,]*\s?(?:%|тыс|млн|млрд|долларов|долл|usd|руб)",
    re.IGNORECASE,
)
_DIGITS = re.compile(r"\d+(?:[.,]\d+)?")


def normalize(text: str) -> str:
    return _SPACES.sub(" ", text.translate(_LOOKALIKES)).strip().lower()


def quoted_in(quote: str, text: str) -> bool:
    """Цитата засчитывается, только если каждый её фрагмент дословно есть на странице."""
    page = normalize(text)
    fragments = [normalize(part) for part in _ELLIPSIS.split(quote)]
    fragments = [part.strip(" \"'") for part in fragments if part.strip(" \"'")]
    if not fragments or max(len(part) for part in fragments) < MIN_FRAGMENT:
        return False
    return all(part in page for part in fragments)


def foreign_numbers(advice: str, allowed: str) -> list[str]:
    """Суммы и проценты из совета, которых нет ни в карточке, ни в конфиге."""
    known = set(_DIGITS.findall(_plain_numbers(allowed)))
    return [
        figure.strip()
        for figure in _MONEY_OR_SHARE.findall(advice)
        if not set(_DIGITS.findall(_plain_numbers(figure))) <= known
    ]


def _plain_numbers(text: str) -> str:
    return re.sub(r"(?<=\d)[\s ,](?=\d{3}\b)", "", text)


def card_problems(card: Card, weights: dict[str, int]) -> list[str]:
    problems = []
    if [rubric.id for rubric in card.rubrics] != list(weights):
        problems.append("rubrics differ from the configured ones")
    if any(rubric.level not in range(1, 6) for rubric in card.rubrics):
        problems.append("a rubric level is outside 1-5")
    expected = sum(
        weights[rubric.id] * (rubric.level - 1) / 4
        for rubric in card.rubrics
        if rubric.id in weights
    )
    if abs(card.score - expected) > 0.01:
        problems.append(f"score {card.score} does not match the rubric arithmetic {expected}")
    empty = [name for name in ("anchor", "upsell") if not getattr(card, name).strip()]
    empty += [
        f"test_sketch.{name}"
        for name, value in card.test_sketch.model_dump().items()
        if not value.strip()
    ]
    if empty:
        problems.append(f"empty fields: {', '.join(empty)}")
    return problems
