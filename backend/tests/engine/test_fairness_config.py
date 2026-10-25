"""FairnessConfig: the confirmed defaults, the three environment overrides, and clear errors."""

from __future__ import annotations

import dataclasses
from decimal import Decimal as D

import pytest

from crossroads.config import FairnessConfig, load_fairness_config


def test_defaults():
    c = FairnessConfig()
    assert (c.population_size, c.population_seed) == (500, 20261024)
    assert c.band_edges == (D(4500), D(6500))
    assert (c.gap_threshold_points, c.min_choice, c.resamples) == (D(15), 30, 1000)
    assert (c.bootstrap_seed, c.confidence, c.min_band_population) == (20261025, 95, 100)


def test_it_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        FairnessConfig().min_choice = 5  # type: ignore[misc]


def test_environment_overrides_are_read():
    c = load_fairness_config(
        {"FAIRNESS_BAND_EDGES": "4000,7000", "FAIRNESS_GAP_THRESHOLD": "12.5", "FAIRNESS_MIN_CHOICE": "40"}
    )
    assert (c.band_edges, c.gap_threshold_points, c.min_choice) == ((D(4000), D(7000)), D("12.5"), 40)


def test_empty_or_missing_values_mean_the_default():
    # docker compose passes ${VAR:-} to the container, so an unset variable arrives as ""
    env = {"FAIRNESS_BAND_EDGES": "", "FAIRNESS_GAP_THRESHOLD": " ", "FAIRNESS_MIN_CHOICE": ""}
    assert load_fairness_config(env) == FairnessConfig()
    assert load_fairness_config({}) == FairnessConfig()


def test_seeds_resamples_and_size_cannot_be_overridden_by_environment():
    env = {"FAIRNESS_POPULATION_SEED": "1", "FAIRNESS_BOOTSTRAP_SEED": "2", "FAIRNESS_RESAMPLES": "3",
           "FAIRNESS_POPULATION_SIZE": "4"}
    assert load_fairness_config(env) == FairnessConfig()


@pytest.mark.parametrize(
    "name,value",
    [
        ("FAIRNESS_BAND_EDGES", "6500,4500"),  # not increasing
        ("FAIRNESS_BAND_EDGES", "4500,4500"),
        ("FAIRNESS_BAND_EDGES", "4500"),  # not two values
        ("FAIRNESS_BAND_EDGES", "4500,6500,9000"),
        ("FAIRNESS_BAND_EDGES", "low,high"),
        ("FAIRNESS_GAP_THRESHOLD", "0"),
        ("FAIRNESS_GAP_THRESHOLD", "-3"),
        ("FAIRNESS_GAP_THRESHOLD", "abc"),
        ("FAIRNESS_MIN_CHOICE", "0"),
        ("FAIRNESS_MIN_CHOICE", "2.5"),
        ("FAIRNESS_MIN_CHOICE", "many"),
    ],
)
def test_an_invalid_value_names_the_setting(name, value):
    with pytest.raises(ValueError, match=name):
        load_fairness_config({name: value})
