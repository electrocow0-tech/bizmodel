from bizmodel.search import Page


class FakeLLM:
    """Отвечает заготовками по типу ответа и запоминает, что у него спрашивали."""

    def __init__(self):
        self.replies = {}
        self.asked = []
        self.schema_retries = 0
        self.schema_failures = 0

    def ask(self, role, chain, system, sections, answer, slug=""):
        self.asked.append((role, sections))
        reply = self.replies[answer.__name__]
        if isinstance(reply, Exception):
            raise reply
        return reply


class FakeSearch:
    def __init__(self, pages: list[Page]):
        self.pages = {page.url: page for page in pages}

    def find(self, query):
        return list(self.pages.values())

    def fetch(self, url):
        return self.pages.get(url)


def page(url: str, text: str) -> Page:
    return Page(url=url, title=url, snippet=text, text=text, published=None, accessed="2026-11-26")
