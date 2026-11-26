from fakes import page

from bizmodel import gate
from bizmodel.llm import StepFailed
from bizmodel.schemas import Vote

QUESTION = "recurring.subscription"
QUOTE = "Teams pay $20 per seat every month."
PAGES = {"E0": page("https://acme.example/pricing", f"Pricing. {QUOTE}")}
SECTIONS = {"Company": "Acme", "Comparable candidate": "none", "Questions": "", "Evidence": ""}


def votes(*answers, quote=QUOTE):
    return [
        Vote(voter=f"model-{number}", answer=answer, evidence_id="E0", quote=quote)
        for number, answer in enumerate(answers)
    ]


def ruling(answer, quote=QUOTE):
    return gate.Ruling(question_id=QUESTION, answer=answer, evidence_id="E0", quote=quote, why="x")


def decide(ctx, company, cast, ruled=None):
    return gate.decide(company, QUESTION, cast, ruled, PAGES, ctx)


def test_unanimous_vote_with_a_real_quote_is_a_confident_fact(ctx, company):
    decision, passport = decide(ctx, company, votes("yes", "yes", "yes", "yes", "yes"))
    assert (decision.answer, decision.decided_by, decision.agreement) == ("yes", "vote", 1.0)
    assert (passport.method, passport.confidence) == ("primary_source", "high")
    assert passport.quote == QUOTE and passport.source_url == "https://acme.example/pricing"


def test_four_of_five_decides_but_lowers_confidence(ctx, company):
    decision, passport = decide(ctx, company, votes("yes", "yes", "yes", "yes", "no"))
    assert (decision.answer, decision.decided_by) == ("yes", "vote")
    assert passport.confidence == "medium"


def test_split_vote_is_settled_by_the_arbiter(ctx, company):
    cast = votes("yes", "yes", "yes", "no", "no")
    decision, passport = decide(ctx, company, cast, ruling("no"))
    assert (decision.answer, decision.decided_by) == ("no", "arbiter")
    assert (passport.method, passport.confidence) == ("primary_source", "medium")


def test_arbiter_is_not_asked_when_the_vote_is_clear(ctx, company):
    cast = {QUESTION: votes("yes", "yes", "yes", "yes", "yes")}
    split = [id for id, one in cast.items() if not gate.quorum_answer(one, ctx)]
    assert gate.arbitrate(company, SECTIONS, split, PAGES, ctx) == {}
    assert ctx.llm.asked == []


def test_arbiter_rules_on_all_disputed_questions_in_one_call_without_seeing_votes(ctx, company):
    ctx.llm.replies["Rulings"] = gate.Rulings(rulings=[ruling("no")])
    rulings = gate.arbitrate(company, SECTIONS, [QUESTION, "recurring.commission"], PAGES, ctx)
    ((role, sections),) = ctx.llm.asked
    assert role == "arbiter"
    assert set(sections) == set(SECTIONS)
    assert QUESTION in sections["Questions"] and "recurring.commission" in sections["Questions"]
    assert rulings[QUESTION].answer == "no"


def test_unsure_arbiter_leaves_the_question_to_a_person(ctx, company):
    cast = votes("yes", "yes", "no", "no", "unknown")
    decision, passport = decide(ctx, company, cast, ruling("unknown", quote=""))
    assert (decision.answer, decision.decided_by) == ("unknown", "unresolved")
    assert passport.method == "needs_human"


def test_arbiter_outage_is_not_a_rejection(ctx, company):
    ctx.llm.replies["Rulings"] = StepFailed("arbiter: no route answered")
    assert gate.arbitrate(company, SECTIONS, [QUESTION], PAGES, ctx) == {}
    decision, _ = decide(ctx, company, votes("yes", "yes", "no", "no", "unknown"))
    assert (decision.answer, decision.decided_by) == ("unknown", "unresolved")


def test_answer_without_a_quote_is_only_a_model_judgment(ctx, company):
    _, passport = decide(ctx, company, votes("yes", "yes", "yes", "yes", "yes", quote=""))
    assert (passport.method, passport.confidence) == ("model_judgment", "low")
    assert passport.source_url is None


def test_person_overrules_the_models(ctx, company):
    ctx.settings = ctx.settings.model_copy(update={"overrides": {"acme": {QUESTION: "no"}}})
    decision, passport = decide(ctx, company, votes("yes", "yes", "yes", "yes", "yes"))
    assert (decision.answer, decision.decided_by) == ("no", "human")
    assert passport.note == "Ответ дал человек"


def test_invented_quote_is_dropped_before_it_can_back_anything(ctx):
    kept = gate.checked_quote(QUOTE, "E0", PAGES, ctx)
    dropped = gate.checked_quote("Teams pay $900 per seat every month.", "E0", PAGES, ctx)
    assert (kept, dropped) == (QUOTE, "")
    assert (ctx.stats.quotes_checked, ctx.stats.quotes_dropped) == (2, 1)
