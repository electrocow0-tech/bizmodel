"""Одна дверь ко всем моделям: маршруты с запасными, кеш на диске, бюджеты и журнал."""

import hashlib
import json
import os
import threading
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from bizmodel.config import Chain, Models
from bizmodel.journal import Journal
from bizmodel.providers import Anthropic, Completion, OpenAICompatible, ProviderError

T = TypeVar("T", bound=BaseModel)


class StepFailed(Exception):
    """Ни один маршрут цепочки не ответил. Шаг остаётся непроверенным, ничего не выдумывается."""


class BudgetExceeded(Exception):
    pass


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def render(sections: dict[str, str]) -> str:
    return "\n\n".join(f"## {title}\n{body}" for title, body in sections.items())


@dataclass
class _Request:
    role: str
    slug: str
    effort: str
    system: str
    user: str
    answer: type[BaseModel]
    inputs: dict[str, str]


class LLM:
    def __init__(
        self,
        models: Models,
        journal: Journal,
        cache: Path,
        down: frozenset[str] = frozenset(),
    ):
        self.models = models
        self.journal = journal
        self.cache = cache
        self.down = down
        self.spent: dict[str, float] = defaultdict(float)
        self.schema_retries = 0
        self.schema_failures = 0
        self._clients: dict[str, Anthropic | OpenAICompatible] = {}
        self._lock = threading.Lock()
        cache.mkdir(parents=True, exist_ok=True)

    def ask(
        self,
        role: str,
        chain: Chain,
        system: str,
        sections: dict[str, str],
        answer: type[T],
        slug: str = "",
    ) -> T:
        request = _Request(
            role=role,
            slug=slug,
            effort=chain.effort,
            system=system,
            user=render(sections),
            answer=answer,
            inputs={title: sha(body) for title, body in sections.items()},
        )
        failed = []
        for route in chain.routes:
            try:
                return self._answer(request, route, failed)
            except ProviderError as error:
                failed.append(route)
                self.journal.write(
                    "llm_failure", role=role, slug=slug, route=route, error=str(error)
                )
        raise StepFailed(f"{role}: no route answered ({', '.join(failed)})")

    def _answer(self, request: _Request, route: str, failed: list[str]) -> BaseModel:
        text = self._complete(request, route, request.user, failed)
        try:
            return request.answer.model_validate_json(text)
        except ValidationError as error:
            with self._lock:
                self.schema_retries += 1
            again = (
                f"{request.user}\n\n## Previous reply rejected\n"
                f"It did not match the required JSON schema:\n{error}\n"
                "Reply again with valid JSON only."
            )
        text = self._complete(request, route, again, failed)
        try:
            return request.answer.model_validate_json(text)
        except ValidationError as error:
            with self._lock:
                self.schema_failures += 1
            raise ProviderError(f"answer does not match the schema: {error.errors()[0]['msg']}")

    def _complete(self, request: _Request, route: str, user: str, failed: list[str]) -> str:
        provider, model = route.split(":", 1)
        if provider in self.down:
            raise ProviderError("simulated outage")

        key = sha(
            json.dumps(
                [route, request.effort, request.system, user, request.answer.model_json_schema()],
                sort_keys=True,
            )
        )
        stored = self.cache / f"{key}.json"
        cached = stored.exists()
        if cached:
            completion = Completion(**json.loads(stored.read_text(encoding="utf-8")))
        else:
            self._check_budget(provider)
            completion = self._client(provider).complete(
                model, request.system, user, request.answer, request.effort
            )
            if completion.usd is None:
                completion.usd = self._price(model, completion)
            stored.write_text(json.dumps(asdict(completion), ensure_ascii=False), encoding="utf-8")
            with self._lock:
                self.spent[provider] += completion.usd

        self.journal.write(
            "llm_call",
            role=request.role,
            slug=request.slug,
            route=route,
            input_sha=sha(request.system + user),
            inputs=request.inputs,
            input_tokens=completion.input_tokens,
            output_tokens=completion.output_tokens,
            usd=completion.usd,
            cached=cached,
            fallback_from=list(failed),
        )
        return completion.text

    def _check_budget(self, provider: str) -> None:
        budget = self.models.providers[provider].budget_usd
        if budget is not None and self.spent[provider] >= budget:
            raise BudgetExceeded(f"{provider}: spent ${self.spent[provider]:.2f} of ${budget:.2f}")

    def _price(self, model: str, completion: Completion) -> float:
        per_input, per_output = self.models.prices[model]
        return (
            completion.input_tokens * per_input + completion.output_tokens * per_output
        ) / 1_000_000

    def _client(self, name: str) -> Anthropic | OpenAICompatible:
        with self._lock:
            if name not in self._clients:
                provider = self.models.providers[name]
                key = os.environ.get(provider.key_env) or "none"
                if provider.kind == "anthropic":
                    self._clients[name] = Anthropic(key)
                else:
                    self._clients[name] = OpenAICompatible(key, provider.base_url)
            return self._clients[name]
