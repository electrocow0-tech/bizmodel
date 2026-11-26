from bizmodel.card import objections_level, total, trust_in
from bizmodel.prescreen import select
from bizmodel.schemas import BusinessModel, Objection, Passport, Prescreen, Rubric, Violation


def objection(strength, verdict):
    return Objection(
        id="O", text="x", reasoning="x", strength=strength, sent_to_verifier=True, verdict=verdict
    )


def rubrics(settings, level):
    return [
        Rubric(id=spec.id, title=spec.title, weight=spec.weight, level=level, why="x")
        for spec in settings.scoring.rubrics
    ]


def test_score_runs_from_zero_to_a_hundred(settings):
    assert total(rubrics(settings, 1)) == 0
    assert total(rubrics(settings, 3)) == 50
    assert total(rubrics(settings, 5)) == 100


def test_speed_and_access_carry_most_of_the_score(settings):
    weights = {spec.id: spec.weight for spec in settings.scoring.rubrics}
    assert weights["time_to_test"] + weights["customer_access"] + weights["time_to_payment"] == 70


def test_confirmed_strong_objections_sink_the_level(settings):
    level, _ = objections_level([objection(5, "supported")] * 3, settings.scoring)
    assert level == 1


def test_refuted_objections_cost_nothing(settings):
    level, _ = objections_level(
        [objection(5, "not_supported"), objection(5, "contradicts")], settings.scoring
    )
    assert level == 5


def test_unverifiable_objection_counts_as_half(settings):
    confirmed, _ = objections_level([objection(5, "supported")], settings.scoring)
    unverifiable, _ = objections_level([objection(5, "source_unavailable")], settings.scoring)
    assert confirmed < unverifiable < 5


def passport(method, origin="gate"):
    return Passport(id="p", claim="x", origin=origin, method=method, confidence="low")


def test_trust_is_the_share_of_facts_backed_by_a_quote(settings):
    backed, guessed = passport("primary_source"), passport("model_judgment")
    assert trust_in([backed] * 7 + [guessed] * 3, settings.scoring).level == "high"
    assert trust_in([backed] * 4 + [guessed] * 6, settings.scoring).level == "medium"
    assert trust_in([backed] * 1 + [guessed] * 9, settings.scoring).level == "low"


def test_score_passport_does_not_inflate_trust(settings):
    arithmetic = passport("calculation", origin="card")
    assert trust_in([passport("model_judgment"), arithmetic], settings.scoring).level == "low"


def screened(slug, speed, violations=()):
    return Prescreen(
        slug=slug,
        business_model=BusinessModel(
            payer="x", pays_for="x", frequency="x", revenue_type="subscription"
        ),
        violations=[Violation(criterion="recurring", reason="x") for _ in violations],
        speed=speed,
        speed_reason="x",
        status="rejected" if violations else "queued",
    )


def test_fastest_models_go_deep_but_no_industry_takes_over(settings):
    funnel = settings.funnel.model_copy(update={"deep_check": 4, "per_industry_cap": 2})
    prescreens = [screened(f"b2b-{n}", 5) for n in range(5)] + [screened("edu-1", 3)]
    prescreens += [screened("bank", 5, violations=["lending"])]
    industries = {one.slug: "Education" if one.slug == "edu-1" else "B2B" for one in prescreens}

    selected, control = select(prescreens, industries, funnel, seed=1)

    assert len(selected) == 3
    assert sum(slug.startswith("b2b") for slug in selected) == 2
    assert "edu-1" in selected
    assert control == ["bank"]


def test_selection_is_reproducible(settings):
    def pick():
        prescreens = [screened(f"co-{n}", 4) for n in range(40)]
        industries = {one.slug: f"industry-{n % 8}" for n, one in enumerate(prescreens)}
        return select(prescreens, industries, settings.funnel, seed=settings.source.seed)

    assert pick() == pick()
