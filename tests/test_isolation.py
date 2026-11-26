"""Критик и проверяющий не видят выводов друг друга. Здесь это доказывается на их реальных запросах."""

from fakes import FakeSearch, page

from bizmodel import critic, verifier
from bizmodel.llm import render
from bizmodel.schemas import BusinessModel

SOURCE = "https://report.example/churn"
QUOTE = "Median monthly churn for SMB tools is 4 percent."
REASONING = "SECRET-REASONING: при таком оттоке тест не окупится"
OTHER_CLAIM = "SECRET-OTHER-CLAIM: крупные игроки отдают это бесплатно"
MODEL = BusinessModel(
    payer="Фрилансеры", pays_for="Счета", frequency="Ежемесячно", revenue_type="subscription"
)


def run_both_agents(ctx, company):
    ctx._searches = {
        agent: FakeSearch([page(SOURCE, f"Churn report 2026. {QUOTE}")])
        for agent in ("critic", "verifier")
    }
    ctx.llm.replies = {
        "Plan": critic.Plan(queries=["smb saas churn"]),
        "Critique": critic.Critique(
            objections=[
                critic.Point(
                    text="Медианный месячный отток у таких сервисов 4%",
                    reasoning=REASONING,
                    strength=5,
                    evidence_id="S0",
                    quote=QUOTE,
                    source_date="2026",
                ),
                critic.Point(
                    text=OTHER_CLAIM,
                    reasoning="SECRET-REASONING-2",
                    strength=4,
                    evidence_id="",
                    quote="",
                    source_date="",
                ),
            ]
        ),
        "Finding": verifier.Finding(
            verdict="supported", quote=QUOTE, source_date="2026", note="Страница это утверждает"
        ),
    }
    objections = critic.attack(company, MODEL, ctx)
    passports = verifier.check(objections, company.slug, ctx)
    return objections, passports


def prompts(ctx, role):
    return [render(sections) for asked, sections in ctx.llm.asked if asked == role]


def test_verifier_gets_the_claim_and_the_page_and_nothing_else(ctx, company):
    run_both_agents(ctx, company)
    (prompt,) = prompts(ctx, "verifier")
    (_, sections) = next(call for call in ctx.llm.asked if call[0] == "verifier")
    assert list(sections) == ["Claim", "Source", "Page text"]
    assert "SECRET" not in prompt
    assert "strength" not in prompt.lower()


def test_critic_finishes_before_the_verifier_says_anything(ctx, company):
    run_both_agents(ctx, company)
    roles = [role for role, _ in ctx.llm.asked]
    assert roles == ["critic", "critic", "verifier"]
    assert all("Страница это утверждает" not in prompt for prompt in prompts(ctx, "critic"))


def test_every_verifier_call_is_checked_for_leaks_and_logged(ctx, company):
    run_both_agents(ctx, company)
    checks = ctx.journal.read("isolation_check")
    assert [check["leaked"] for check in checks] == [[]]


def test_a_leak_would_be_caught(ctx, company):
    objections, _ = run_both_agents(ctx, company)
    first, second = objections
    leaking = {"Claim": first.text + " " + first.reasoning, "Source": SOURCE, "Page text": ""}
    assert verifier.leaks(leaking, first, [second]) == ["reasoning"]


def test_agents_read_pages_from_separate_caches(ctx, company):
    run_both_agents(ctx, company)
    assert ctx.search("critic") is not ctx.search("verifier")


def test_objection_without_a_source_is_marked_not_sent_to_a_model(ctx, company):
    objections, passports = run_both_agents(ctx, company)
    sourced, unsourced = objections
    assert (sourced.verdict, sourced.verifier_quote) == ("supported", QUOTE)
    assert unsourced.verdict == "no_source"
    assert [passport.method for passport in passports] == ["primary_source", "model_judgment"]
