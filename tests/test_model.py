"""Testes do modelo XGBoost."""

import pandas as pd

from app.src.model import calcular_metricas, treinar_modelo
from app.src.preprocessor import Preprocessor
from scripts.generate_dataset import gerar_dataset


def test_calcular_metricas():
    y_true = pd.Series([100.0, 200.0, 300.0])
    y_pred = [110.0, 190.0, 280.0]
    m = calcular_metricas(y_true.values, y_pred)
    assert "rmse" in m and "mae" in m and "r2" in m and "mape" in m


def test_treinar_modelo_smoke():
    df = gerar_dataset(n_clientes=100, n_meses=2)
    prep = Preprocessor()
    x, y = prep.fit_transform(df)
    split = int(len(x) * 0.8)
    model = treinar_modelo(
        x.iloc[:split], y.iloc[:split],
        x.iloc[split:], y.iloc[split:],
        params={"n_estimators": 10, "max_depth": 3},
    )
    assert model is not None
