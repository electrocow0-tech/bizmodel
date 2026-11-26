"""Поиск и загрузка страниц. У каждого агента свой кеш: никто не читает чужие страницы."""

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx

from bizmodel.config import SearchSettings
from bizmodel.journal import Journal
from bizmodel.schemas import Evidence

API = "https://api.tavily.com"


@dataclass(frozen=True)
class Page:
    url: str
    title: str
    snippet: str
    text: str
    published: str | None
    accessed: str

    def evidence(self, id: str) -> Evidence:
        return Evidence(
            id=id,
            url=self.url,
            title=self.title,
            published=self.published,
            accessed=self.accessed,
            sha256=hashlib.sha256(self.text.encode()).hexdigest(),
        )


class Search:
    def __init__(self, agent: str, settings: SearchSettings, journal: Journal, cache: Path):
        self.agent = agent
        self.settings = settings
        self.journal = journal
        self.cache = cache / agent
        self.cache.mkdir(parents=True, exist_ok=True)

    def find(self, query: str) -> list[Page]:
        def search() -> list[dict]:
            body = self._post(
                "search",
                {
                    "query": query,
                    "max_results": self.settings.results_per_query,
                    "include_raw_content": True,
                },
            )
            return [
                {
                    "url": result["url"],
                    "title": result.get("title") or result["url"],
                    "snippet": (result.get("content") or "")[: self.settings.snippet_chars],
                    "text": result.get("raw_content") or result.get("content") or "",
                    "published": result.get("published_date"),
                    "accessed": date.today().isoformat(),
                }
                for result in body.get("results", [])
            ]

        return [Page(**page) for page in self._cached("find", query, search)]

    def fetch(self, url: str) -> Page | None:
        def extract() -> list[dict]:
            results = self._post("extract", {"urls": [url]}).get("results", [])
            return [
                {
                    "url": url,
                    "title": result.get("title") or url,
                    "snippet": (result.get("raw_content") or "")[: self.settings.page_chars],
                    "text": result.get("raw_content") or "",
                    "published": None,
                    "accessed": date.today().isoformat(),
                }
                for result in results
                if result.get("raw_content")
            ]

        pages = self._cached("fetch", url, extract)
        return Page(**pages[0]) if pages else None

    def _cached(self, kind: str, request: str, load) -> list[dict]:
        key = hashlib.sha256(f"{kind}:{request}".encode()).hexdigest()[:16]
        stored = self.cache / f"{key}.json"
        cached = stored.exists()
        if cached:
            pages = json.loads(stored.read_text(encoding="utf-8"))
        else:
            try:
                pages = load()
            except httpx.HTTPError as error:
                self.journal.write(
                    "search_failure", agent=self.agent, kind=kind, request=request, error=str(error)
                )
                return []
            stored.write_text(json.dumps(pages, ensure_ascii=False), encoding="utf-8")
        self.journal.write(
            "search", agent=self.agent, kind=kind, request=request, pages=len(pages), cached=cached
        )
        return pages

    def _post(self, path: str, body: dict) -> dict:
        response = httpx.post(
            f"{API}/{path}",
            headers={"Authorization": f"Bearer {os.environ.get('TAVILY_API_KEY', '')}"},
            json=body,
            timeout=60,
        )
        response.raise_for_status()
        return response.json()


def window(text: str, around: str | None, size: int) -> str:
    """Часть длинной страницы, которую стоит показать: вокруг известной цитаты, иначе начало."""
    position = text.find(around[:60]) if around else -1
    if position < 0:
        return text[:size]
    start = max(0, position - size // 2)
    return text[start : start + size]
