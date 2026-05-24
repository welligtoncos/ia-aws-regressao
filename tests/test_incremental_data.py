"""Testes de ingestão incremental simulada."""

import pandas as pd

from workloads.shared.incremental_data import bootstrap_dataset, gerar_lote_diario, ingest_daily_simulated
from workloads.shared.target import assign_forward_target


def test_bootstrap_dataset_shape():
    df = assign_forward_target(bootstrap_dataset(n_clientes=100, n_meses=3, seed=1))
    assert len(df) == 200
    assert "saldo_alvo" in df.columns


def test_gerar_lote_diario_com_ids_cust():
    from pathlib import Path
    from datetime import datetime

    from workloads.shared.rafo044_etl import build_monthly_panel

    panel = build_monthly_panel(Path("tests/fixtures/rafo044"), min_months_history=2)
    lote = gerar_lote_diario(panel, datetime(2015, 8, 1), new_clients=2, seed=3)
    n_clientes = panel["cliente_id"].nunique()
    assert len(lote) == n_clientes + 2
    assert all(str(c).startswith("CUST") for c in lote["cliente_id"].tail(2))


def test_gerar_lote_diario_incrementa_linhas():
    base = bootstrap_dataset(n_clientes=50, n_meses=2, seed=2)
    ultima = pd.to_datetime(base["data_referencia"]).max().to_pydatetime()
    from datetime import timedelta
    lote = gerar_lote_diario(base, ultima + timedelta(days=1), new_clients=5, seed=2)
    assert len(lote) == 55
    assert lote["data_referencia"].nunique() == 1


def test_ingest_daily_simulated_local_logic(monkeypatch):
    store = {"df": pd.DataFrame()}

    def fake_read(bucket, key, region):
        return store["df"].copy()

    def fake_write(df, bucket, key, region):
        store["df"] = df.copy()

    monkeypatch.setattr("workloads.shared.incremental_data.read_csv_s3", fake_read)
    monkeypatch.setattr("workloads.shared.incremental_data.write_csv_s3", fake_write)

    first = ingest_daily_simulated("b", "k", run_id="r1", seed_clientes=20, seed_meses=3)
    assert first["total_rows"] == 40
    second = ingest_daily_simulated("b", "k", run_id="r2", new_clients=2)
    assert second["rows_added"] == 22
    assert second["rows_before"] == first["total_rows"]
    assert second["total_rows"] >= first["total_rows"]
