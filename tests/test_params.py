import pytest
from test_server import PARAMS

from bizmodel import config
from bizmodel.params import Params


def test_owner_choices_land_in_the_settings_without_touching_the_files(settings):
    raw = config.read(settings.root)
    changed = Params(**PARAMS).apply(raw)
    built = config.build(settings.root, changed)

    assert built.profile == "dev"
    assert built.source.sample_size == 100 and built.source.industries == ["B2B", "Consumer"]
    assert built.funnel.deep_check == 8
    assert built.assumptions.horizon_weeks == 8
    assert {rubric.id: rubric.weight for rubric in built.scoring.rubrics}["time_to_test"] == 30
    assert config.load(settings.root).source.industries is None


def test_weights_for_unknown_scales_are_rejected(settings):
    weights = {"speed": 100}
    with pytest.raises(ValueError):
        Params(**PARAMS | {"weights": weights}).apply(config.read(settings.root))
