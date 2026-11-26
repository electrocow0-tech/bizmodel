"""Два способа дойти до модели: API Anthropic и всё, что говорит по протоколу OpenAI."""

from dataclasses import dataclass

import anthropic
import openai
from pydantic import BaseModel


class ProviderError(Exception):
    """Провайдер не ответил. Вызывающий может попробовать следующий маршрут."""


@dataclass
class Completion:
    text: str
    input_tokens: int
    output_tokens: int
    usd: float | None = None


class Anthropic:
    def __init__(self, key: str):
        self.client = anthropic.Anthropic(api_key=key)

    def complete(
        self, model: str, system: str, user: str, answer: type[BaseModel], effort: str
    ) -> Completion:
        try:
            response = self.client.messages.parse(
                model=model,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"effort": effort},
                output_format=answer,
            )
        except anthropic.BadRequestError:
            raise
        except anthropic.APIError as error:
            raise ProviderError(f"{type(error).__name__}: {error}") from error

        if response.stop_reason == "refusal":
            raise ProviderError("model refused the request")
        if response.parsed_output is None:
            raise ProviderError(f"no structured answer, stop_reason={response.stop_reason}")
        return Completion(
            text=response.parsed_output.model_dump_json(),
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )


class OpenAICompatible:
    def __init__(self, key: str, base_url: str):
        self.client = openai.OpenAI(api_key=key, base_url=base_url)

    def complete(
        self, model: str, system: str, user: str, answer: type[BaseModel], effort: str
    ) -> Completion:
        try:
            response = self.client.chat.completions.create(
                model=model,
                max_tokens=8000,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": answer.__name__,
                        "strict": True,
                        "schema": strict_schema(answer),
                    },
                },
            )
        except (openai.BadRequestError, openai.UnprocessableEntityError):
            raise
        except openai.APIError as error:
            raise ProviderError(f"{type(error).__name__}: {error}") from error

        if not response.choices or not response.choices[0].message.content:
            raise ProviderError("empty answer")
        usage = response.usage
        return Completion(
            text=response.choices[0].message.content,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            usd=(usage.model_extra or {}).get("cost"),
        )


def strict_schema(answer: type[BaseModel]) -> dict:
    """Строгий режим OpenAI требует закрытых объектов и всех свойств в required."""
    schema = answer.model_json_schema()

    def close(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}))
            for child in node.values():
                close(child)
        elif isinstance(node, list):
            for child in node:
                close(child)

    close(schema)
    return schema
