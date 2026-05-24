"""Testes do model registry (champion)."""

from workloads.shared.model_registry import (
    CHAMPION_MIN_RMSE_IMPROVEMENT,
    is_better_than_champion,
)


def test_first_run_always_promotes():
    assert is_better_than_champion({"rmse": 100.0, "wape": 5.0}, None) is True


def test_rmse_improvement_above_threshold_promotes():
    champ = {"rmse": 1400.0, "wape": 10.0}
    new = {"rmse": 1350.0, "wape": 12.0}
    assert is_better_than_champion(new, champ) is True


def test_rmse_improvement_below_threshold_does_not_promote():
    champ = {"rmse": 1400.0, "wape": 4.5}
    new = {"rmse": 1390.0, "wape": 3.0}
    assert is_better_than_champion(new, champ) is False


def test_worse_rmse_does_not_promote():
    champ = {"rmse": 1400.0, "wape": 4.5}
    assert is_better_than_champion({"rmse": 1410.0, "wape": 3.0}, champ) is False


def test_same_metrics_does_not_promote():
    champ = {"rmse": 1400.0, "wape": 4.5}
    assert is_better_than_champion({"rmse": 1400.0, "wape": 4.5}, champ) is False


def test_custom_threshold():
    champ = {"rmse": 1000.0}
    small_gain = {"rmse": 990.0}
    large_gain = {"rmse": 940.0}
    assert is_better_than_champion(large_gain, champ, min_rmse_improvement=0.05) is True
    assert is_better_than_champion(small_gain, champ, min_rmse_improvement=CHAMPION_MIN_RMSE_IMPROVEMENT) is False
    assert is_better_than_champion(large_gain, champ, min_rmse_improvement=CHAMPION_MIN_RMSE_IMPROVEMENT) is True
