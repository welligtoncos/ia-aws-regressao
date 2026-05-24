"""Testes do model registry (champion)."""

from workloads.shared.model_registry import is_better_than_champion


def test_first_run_always_promotes():
    assert is_better_than_champion({"rmse": 100.0, "mape": 5.0}, None) is True


def test_both_improve_promotes():
    champ = {"rmse": 1400.0, "mape": 4.5}
    assert is_better_than_champion({"rmse": 1390.0, "mape": 4.4}, champ) is True


def test_lower_rmse_only_does_not_promote():
    champ = {"rmse": 1400.0, "mape": 4.5}
    assert is_better_than_champion({"rmse": 1390.0, "mape": 5.0}, champ) is False


def test_lower_mape_only_does_not_promote():
    champ = {"rmse": 1400.0, "mape": 4.5}
    assert is_better_than_champion({"rmse": 1410.0, "mape": 4.0}, champ) is False


def test_worse_rmse_does_not_promote():
    champ = {"rmse": 1400.0, "mape": 4.5}
    assert is_better_than_champion({"rmse": 1410.0, "mape": 3.0}, champ) is False


def test_same_metrics_does_not_promote():
    champ = {"rmse": 1400.0, "mape": 4.5}
    assert is_better_than_champion({"rmse": 1400.0, "mape": 4.5}, champ) is False
