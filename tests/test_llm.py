import pytest
from pydantic import BaseModel

from bizmodel.config import Chain, Models
from bizmodel.journal import Journal
from bizmodel.llm import LLM, BudgetExceeded, StepFailed
from bizmodel.providers import Completion, ProviderError, strict_schema


class Reply(BaseModel):
    answer: str


class Scripted:
    """Заменяет провайдера и проигрывает заготовленные ответы."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = 0

    def complete(self, model, system, user, answer, effort):
        self.calls += 1
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return Completion(text=reply, input_tokens=1000, output_tokens=1000)


MODELS = Models(
    providers={
        "main": {"kind": "anthropic", "key_env": "X", "budget_usd": 0.5},
        "spare": {"kind": "openai_compatible", "key_env": "X", "base_url": "http://spare"},
    },
    prices={"big": (100, 100)},
    profiles={},
)
CHAIN = Chain(routes=["main:big", "spare:big"])
GOOD = '{"answer": "ok"}'


@pytest.fixture
def llm(tmp_path):
    def build(main, spare=None, **options):
        llm = LLM(MODELS, Journal(tmp_path / "calls.jsonl"), tmp_path / "cache", **options)
        llm._clients = {"main": main, "spare": spare or Scripted()}
        return llm

    return build


def ask(llm, question="q"):
    return llm.ask("critic", CHAIN, "system", {"Question": question}, Reply, slug="acme")


def test_answer_is_parsed_and_journaled(llm):
    llm = llm(Scripted(GOOD))
    assert ask(llm).answer == "ok"
    (call,) = llm.journal.read("llm_call")
    assert call["role"] == "critic" and call["slug"] == "acme" and call["route"] == "main:big"
    assert call["usd"] == pytest.approx(0.2)
    assert list(call["inputs"]) == ["Question"]


def test_provider_outage_falls_back_to_the_next_route(llm):
    llm = llm(Scripted(ProviderError("503")), Scripted(GOOD))
    assert ask(llm).answer == "ok"
    assert llm.journal.read("llm_failure")[0]["route"] == "main:big"
    assert llm.journal.read("llm_call")[0]["fallback_from"] == ["main:big"]


def test_step_fails_when_no_route_answers(llm):
    llm = llm(Scripted(ProviderError("503")), Scripted(ProviderError("timeout")))
    with pytest.raises(StepFailed):
        ask(llm)


def test_repeated_question_is_served_from_cache(llm):
    main = Scripted(GOOD)
    llm = llm(main)
    ask(llm)
    ask(llm)
    assert main.calls == 1
    assert [call["cached"] for call in llm.journal.read("llm_call")] == [False, True]
    assert llm.spent["main"] == pytest.approx(0.2)


def test_malformed_answer_gets_one_retry(llm):
    llm = llm(Scripted("not json", GOOD))
    assert ask(llm).answer == "ok"
    assert (llm.schema_retries, llm.schema_failures) == (1, 0)


def test_two_malformed_answers_move_on_to_the_next_route(llm):
    llm = llm(Scripted("not json", "still not json"), Scripted(GOOD))
    assert ask(llm).answer == "ok"
    assert (llm.schema_retries, llm.schema_failures) == (1, 1)


def test_run_stops_at_the_budget(llm):
    llm = llm(Scripted(GOOD, GOOD, GOOD, GOOD))
    for question in ("a", "b", "c"):
        ask(llm, question)
    with pytest.raises(BudgetExceeded):
        ask(llm, "d")


def test_simulated_outage_skips_the_provider(llm):
    main = Scripted(GOOD)
    llm = llm(main, Scripted(GOOD), down=frozenset({"main"}))
    ask(llm)
    assert main.calls == 0


def test_strict_schema_closes_nested_objects():
    class Outer(BaseModel):
        replies: list[Reply]

    schema = strict_schema(Outer)
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["Reply"]["additionalProperties"] is False
    assert schema["$defs"]["Reply"]["required"] == ["answer"]
