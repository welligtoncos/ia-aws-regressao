"""Testes de alvo futuro e split temporal."""

import pandas as pd

from workloads.shared.target import assign_forward_target, temporal_train_val_test_split


def test_assign_forward_target_drops_last_period():
    df = pd.DataFrame({
        "cliente_id": ["A", "A", "B", "B"],
        "data_referencia": ["2025-01-01", "2025-02-01", "2025-01-01", "2025-02-01"],
        "saldo_m1": [100.0, 200.0, 50.0, 80.0],
        "segmento": ["VAREJO"] * 4,
    })
    out = assign_forward_target(df)
    assert len(out) == 2
    assert out.loc[out["cliente_id"] == "A", "saldo_alvo"].iloc[0] == 200.0


def test_temporal_split_no_leakage_columns():
    df = assign_forward_target(pd.DataFrame({
        "cliente_id": [f"C{i//3}" for i in range(30)],
        "data_referencia": pd.date_range("2024-01-01", periods=30, freq="MS").strftime("%Y-%m-%d").tolist(),
        "saldo_m1": range(30),
        "segmento": ["VAREJO"] * 30,
    }))
    meta = df[["cliente_id", "data_referencia", "segmento", "_proxima_data"]]
    x = pd.DataFrame({"f1": range(len(df))}, index=df.index)
    y = df["saldo_alvo"]
    x_train, x_val, x_test, y_train, y_val, y_test = temporal_train_val_test_split(x, y, meta)
    assert len(x_test) > 0
    assert len(x_train) > 0
    assert len(x_val) > 0
    used = len(x_train) + len(x_val) + len(x_test)
    assert used <= len(df)
