"""Testes do model registry (champion)."""

from workloads.shared.model_registry import (
    CHAMPION_MAX_R2_REGRESSION,
    CHAMPION_MIN_WAPE_IMPROVEMENT_PP,
    evaluate_champion_promotion,
    is_better_than_champion,
)


def test_first_run_always_promotes():
    ok, reason = evaluate_champion_promotion({"wape": 20.0, "r2": 0.84}, None)
    assert ok is True
    assert reason == "primeiro_champion"
    assert is_better_than_champion({"wape": 20.0, "r2": 0.84}, None) is True


def test_reconcile_case_promotes():
    """Caso prod: champion parcial vs candidato painel completo."""
    champ = {
        "wape": 24.29,
        "r2": 0.8368,
        "rmse": 1473.74,
        "total_linhas": 6819,
    }
    new = {"wape": 20.45, "r2": 0.8453, "rmse": 1543.32}
    ok, reason = evaluate_champion_promotion(new, champ, new_total_linhas=12168)
    assert ok is True
    assert reason == "criterios_atendidos"


def test_wape_improvement_below_threshold_does_not_promote():
    champ = {"wape": 20.0, "r2": 0.84, "total_linhas": 10000}
    new = {"wape": 19.5, "r2": 0.85}  # só 0,5 p.p.
    ok, reason = evaluate_champion_promotion(new, champ, new_total_linhas=12000)
    assert ok is False
    assert "wape" in reason


def test_r2_regression_blocks_promotion():
    champ = {"wape": 30.0, "r2": 0.90, "total_linhas": 5000}
    new = {"wape": 20.0, "r2": 0.88}  # WAPE ok, R² caiu 0,02
    ok, reason = evaluate_champion_promotion(
        new, champ, new_total_linhas=6000, max_r2_regression=CHAMPION_MAX_R2_REGRESSION
    )
    assert ok is False
    assert "r2" in reason


def test_fewer_training_rows_blocks_promotion():
    champ = {"wape": 30.0, "r2": 0.80, "total_linhas": 12000}
    new = {"wape": 15.0, "r2": 0.90}
    ok, reason = evaluate_champion_promotion(new, champ, new_total_linhas=8000)
    assert ok is False
    assert "total_linhas" in reason


def test_wape_improvement_exactly_one_pp_promotes():
    champ = {"wape": 25.0, "r2": 0.84, "total_linhas": 1000}
    new = {"wape": 24.0, "r2": 0.84}
    ok, _ = evaluate_champion_promotion(
        new, champ, new_total_linhas=1000, min_wape_improvement_pp=CHAMPION_MIN_WAPE_IMPROVEMENT_PP
    )
    assert ok is True
