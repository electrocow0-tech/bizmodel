from itertools import product

import pytest
from pydantic import ValidationError

from bizmodel.forest import Tree, overall, walk
from bizmodel.schemas import TreeResult


def tree(settings, tree_id):
    return next(tree for tree in settings.forest.trees if tree.id == tree_id)


def answers(**by_node):
    return lambda question_id: by_node[question_id.split(".")[1]]


def test_owner_has_five_criteria(settings):
    assert len(settings.forest.trees) == 5


def test_subscription_passes_without_asking_about_commission(settings):
    result = walk(tree(settings, "recurring"), answers(subscription="yes"))
    assert result.outcome == "pass"
    assert result.path == ["recurring.subscription"]


def test_commission_is_asked_only_when_there_is_no_subscription(settings):
    result = walk(tree(settings, "recurring"), answers(subscription="no", commission="yes"))
    assert result.outcome == "pass"
    assert result.path == ["recurring.subscription", "recurring.commission"]


def test_one_time_sales_are_rejected_with_a_reason(settings):
    result = walk(tree(settings, "recurring"), answers(subscription="no", commission="no"))
    assert result.outcome == "fail"
    assert "разовые" in result.reason.lower()


def test_unanswered_question_is_not_a_rejection(settings):
    result = walk(tree(settings, "online_legal"), answers(illegal="no", online="unknown"))
    assert result.outcome == "unknown"
    assert result.reason.startswith("Не удалось проверить")


def test_absence_of_a_large_company_cannot_be_proven_so_it_never_fails(settings):
    scale = tree(settings, "proven_at_scale")
    for named, size in product(("yes", "no", "unknown"), repeat=2):
        assert walk(scale, answers(named=named, size=size)).outcome in ("pass", "unknown")


def test_every_tree_ends_on_any_answers(settings):
    for one in settings.forest.trees:
        for reply in ("yes", "no", "unknown"):
            assert walk(one, lambda _, reply=reply: reply).outcome in ("pass", "fail", "unknown")


def test_model_passes_only_when_every_criterion_passes():
    def result(outcome):
        return TreeResult(tree_id="t", title="t", outcome=outcome, path=[], reason="")

    assert overall([result("pass"), result("pass")]) == "pass"
    assert overall([result("pass"), result("unknown")]) == "unknown"
    assert overall([result("unknown"), result("fail")]) == "fail"


def test_branch_to_a_missing_node_is_a_config_error():
    with pytest.raises(ValidationError):
        Tree(
            id="broken",
            title="broken",
            root="first",
            nodes={"first": {"label": "x", "ask": "x?", "yes": "nowhere", "no": {"fail": "x"}}},
        )


def test_version_changes_with_the_trees(settings):
    version = settings.forest.version
    changed = settings.forest.model_copy(deep=True)
    changed.trees[0].nodes["illegal"].ask += " "
    assert len(version) == 12
    assert changed.version != version
