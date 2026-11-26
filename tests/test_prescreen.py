from bizmodel import prescreen
from bizmodel.pipeline import confirmed
from bizmodel.schemas import BusinessModel, Gate, Prescreen, TreeResult, Violation


def screening(*checks):
    return prescreen.Screening(
        payer="x",
        pays_for="x",
        frequency="x",
        revenue_type="subscription",
        checks=[prescreen.Check(criterion=id, violated=hit, reason="x") for id, hit in checks],
        speed=4,
        speed_reason="x",
    )


def test_criterion_marked_as_not_violated_does_not_reject(ctx, company):
    ctx.llm.replies["Screening"] = screening(("recurring", False), ("online_legal", False))
    assert prescreen.screen(company, ctx).status == "queued"


def test_explicit_violation_rejects_with_its_reason(ctx, company):
    ctx.llm.replies["Screening"] = screening(("recurring", True), ("online_legal", False))
    result = prescreen.screen(company, ctx)
    assert result.status == "rejected"
    assert [violation.criterion for violation in result.violations] == ["recurring"]


def test_large_comparable_is_never_judged_from_a_description(ctx, company):
    ctx.llm.replies["Screening"] = screening(("proven_at_scale", True))
    assert prescreen.screen(company, ctx).status == "queued"
    _, sections = ctx.llm.asked[0]
    assert "proven_at_scale" not in sections["Owner's criteria"]


def rejected_for(*criteria):
    return Prescreen(
        slug="acme",
        business_model=BusinessModel(payer="x", pays_for="x", frequency="x", revenue_type="other"),
        violations=[Violation(criterion=criterion, reason="x") for criterion in criteria],
        speed=1,
        speed_reason="x",
        status="rejected",
    )


def checked(**outcomes):
    trees = [
        TreeResult(tree_id=id, title=id, outcome=outcome, path=[], reason="")
        for id, outcome in outcomes.items()
    ]
    return Gate(
        slug="acme",
        outcome="fail",
        trees=trees,
        decisions=[],
        evidence=[],
        passports=[],
        forest_version="x",
    )


def test_rejection_is_confirmed_only_by_the_same_criterion():
    assert confirmed(rejected_for("recurring"), checked(recurring="fail", online_legal="pass"))
    assert not confirmed(rejected_for("recurring"), checked(recurring="pass", online_legal="fail"))
    assert not confirmed(rejected_for("recurring"), checked(recurring="unknown"))
