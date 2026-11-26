import json
import threading
from datetime import UTC, datetime
from pathlib import Path


class Journal:
    """Журнал прогона: только дописывается, одна строка - одно событие в JSON."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def write(self, event: str, **fields) -> None:
        line = json.dumps(
            {"at": datetime.now(UTC).isoformat(timespec="seconds"), "event": event, **fields},
            ensure_ascii=False,
        )
        with self._lock, self.path.open("a", encoding="utf-8") as file:
            file.write(line + "\n")

    def read(self, event: str | None = None) -> list[dict]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        records = [json.loads(line) for line in lines if line]
        return [record for record in records if event in (None, record["event"])]
