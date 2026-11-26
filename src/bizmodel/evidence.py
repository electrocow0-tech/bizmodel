"""Свидетельства: пронумерованные страницы, которые видит модель, и проверка цитат по ним."""

from bizmodel.context import Context
from bizmodel.search import Page
from bizmodel.validate import quoted_in


def numbered(pages: list[Page], prefix: str) -> dict[str, Page]:
    unique = {}
    for page in pages:
        unique.setdefault(page.url, page)
    return {f"{prefix}{number}": page for number, page in enumerate(unique.values())}


def show(pages: dict[str, Page]) -> str:
    return "\n\n".join(
        f"[{id}] {page.title} | {page.url}\n{page.snippet}" for id, page in pages.items()
    )


def checked_quote(quote: str, evidence_id: str, pages: dict[str, Page], ctx: Context) -> str:
    """Цитата, которой нет на странице, снимается: утверждение остаётся без источника."""
    if not quote:
        return ""
    ctx.count("quotes_checked")
    if evidence_id in pages and quoted_in(quote, pages[evidence_id].text):
        return quote
    ctx.count("quotes_dropped")
    return ""
