from bizmodel.validate import foreign_numbers, quoted_in

PAGE = """
Acme raised a $150 million Series C at a $1.2 billion valuation,
the company said on Tuesday.   Teams pay “$20 per seat” every month.
"""


def test_verbatim_quote_is_found_despite_spacing_and_typography():
    assert quoted_in('Teams pay "$20 per seat" every month', PAGE)
    assert quoted_in("raised a $150 million Series C\nat a $1.2 billion valuation", PAGE)


def test_quote_stitched_with_an_ellipsis_needs_every_fragment():
    assert quoted_in("Acme raised a $150 million Series C ... Teams pay", PAGE)
    assert not quoted_in("Acme raised a $150 million Series C ... customers love it", PAGE)


def test_invented_quote_is_rejected():
    assert not quoted_in("Acme raised a $900 million Series C", PAGE)


def test_too_short_to_prove_anything():
    assert not quoted_in("$20", PAGE)
    assert not quoted_in("", PAGE)


def test_advice_may_only_use_figures_from_the_card():
    card = "Бюджет теста 10000 долларов, цена $20 в месяц, отток 5%"
    assert foreign_numbers("Вложить $10 000, цена $20, отток 5%", card) == []
    assert foreign_numbers("Рынок $40 млрд, отток 5%", card) == ["$40 млрд"]
    assert foreign_numbers("Конверсия 12% за 3 недели", card) == ["12%"]


def test_plan_numbers_without_money_or_percent_are_fine():
    assert foreign_numbers("Провести 15 интервью за 2 недели", "ничего") == []
