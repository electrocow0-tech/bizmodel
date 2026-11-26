"""Задел под дообучение: каждый прогон дописывает примеры в формате диалога."""

import json
import threading
from pathlib import Path

_lock = threading.Lock()


def remember(path: Path, system: str, user: str, answer: dict, meta: dict) -> None:
    example = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": json.dumps(answer, ensure_ascii=False)},
        ],
        "meta": meta,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock, path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(example, ensure_ascii=False) + "\n")
