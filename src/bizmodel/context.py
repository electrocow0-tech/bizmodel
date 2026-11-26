import threading
from dataclasses import dataclass, field
from pathlib import Path

from bizmodel.config import Settings
from bizmodel.journal import Journal
from bizmodel.llm import LLM
from bizmodel.schemas import ValidatorStats
from bizmodel.search import Search


@dataclass
class Context:
    """Всё, что нужно шагу конвейера, чтобы сделать свою работу."""

    settings: Settings
    llm: LLM
    journal: Journal
    cache: Path
    stats: ValidatorStats = field(default_factory=ValidatorStats)
    _searches: dict[str, Search] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def search(self, agent: str) -> Search:
        with self._lock:
            if agent not in self._searches:
                self._searches[agent] = Search(
                    agent, self.settings.search, self.journal, self.cache / "search"
                )
            return self._searches[agent]

    def count(self, counter: str, by: int = 1) -> None:
        with self._lock:
            setattr(self.stats, counter, getattr(self.stats, counter) + by)
