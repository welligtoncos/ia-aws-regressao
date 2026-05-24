"""Testes de baselines de holdout."""

import pandas as pd

from app.src.model import calcular_baselines_holdout, resumo_baselines_vs_modelo


def test_naive_baseline_metrics():
    meta = pd.DataFrame({"saldo_m1": [100.0, 200.0, 300.0]})
    y_true = [110.0, 190.0, 280.0]
    baselines = calcular_baselines_holdout(meta, y_true)
    assert "naive_saldo_m1" in baselines
    assert baselines["naive_saldo_m1"]["wape"] > 0


def test_model_beats_naive_when_better():
    baselines = {
        "naive_saldo_m1": {"wape": 25.0, "rmse": 100.0},
        "media_saldos_m1_m6": {"wape": 22.0, "rmse": 90.0},
    }
    modelo = {"wape": 20.0, "rmse": 80.0}
    resumo = resumo_baselines_vs_modelo(modelo, baselines)
    assert resumo["beats_naive"] is True
    assert resumo["wape_gain_vs_naive_pp"] == 5.0
