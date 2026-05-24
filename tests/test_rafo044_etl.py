"""Testes ETL Rafo044."""

from pathlib import Path

import pandas as pd

from workloads.shared.rafo044_etl import (
    TRAINING_COLUMNS,
    build_monthly_panel,
    export_month_batch,
    split_initial_and_incoming,
)
from workloads.shared.target import assign_forward_target

FIXTURE = Path(__file__).parent / "fixtures" / "rafo044"


def _write_transactions() -> None:
    rows = []
    for acc, cust, base in [
        ("ACC0000001", "CUST000001", 100.0),
        ("ACC0000002", "CUST000002", 200.0),
    ]:
        for i, month in enumerate(range(1, 9)):
            rows.append({
                "transaction_id": f"TX{acc}{i}",
                "account_id": acc,
                "transaction_type": "deposit" if i % 2 == 0 else "withdrawal",
                "amount": base + i * 50,
                "currency": "AUD",
                "transaction_date": f"2015-{month:02d}-15",
                "branch_code": "BR001",
                "merchant_category": "retail",
                "status": "completed",
            })
    pd.DataFrame(rows).to_parquet(FIXTURE / "transactions.parquet", index=False)


def test_build_monthly_panel_schema():
    _write_transactions()
    panel = build_monthly_panel(FIXTURE, min_months_history=2)
    assert set(TRAINING_COLUMNS).issubset(panel.columns)
    assert panel["segmento"].isin(["VAREJO", "PRIME", "PRIVATE"]).all()
    assert len(panel) >= 2
    with_target = assign_forward_target(panel.copy())
    assert "saldo_alvo" in with_target.columns


def test_export_month_and_split():
    _write_transactions()
    panel = build_monthly_panel(FIXTURE, min_months_history=2)
    batch = export_month_batch(panel, "2015-08")
    assert not batch.empty
    initial, incoming = split_initial_and_incoming(panel, "2015-08")
    assert len(initial) + len(incoming) == len(panel)
