"""
ETL Rafo044 Synthetic Bank → schema do pipeline (dados_treino / incoming).

Fonte: https://github.com/Rafo044/Synthetic_Bank_Dataset
Arquivos esperados em ``data_dir``:
  customers.csv, accounts.csv, loans.csv, branches.csv (opcional),
  transactions.parquet
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd

SEGMENT_MAP = {
    "retail": "VAREJO",
    "corporate": "PRIME",
    "premium": "PRIVATE",
}
CITY_UF = {"Melbourne": "VIC", "Sydney": "NSW"}
TRAINING_COLUMNS = [
    "cliente_id",
    "idade",
    "renda_mensal",
    "segmento",
    "tempo_relacionamento",
    "uf",
    "genero",
    "possui_investimento",
    "possui_credito",
    "possui_seguro",
    "score_credito",
    "data_referencia",
    "saldo_m1",
    "saldo_m2",
    "saldo_m3",
    "saldo_m4",
    "saldo_m5",
    "saldo_m6",
    "qtd_transacoes_mes",
    "valor_debitos_mes",
    "valor_creditos_mes",
    "qtd_produtos_ativos",
    "mes",
    "trimestre",
    "ano",
    "is_fim_de_ano",
    "is_inicio_de_ano",
]


def _require_files(data_dir: Path) -> None:
    missing = [
        name
        for name in ("customers.csv", "accounts.csv", "transactions.parquet")
        if not (data_dir / name).exists()
    ]
    if missing:
        raise FileNotFoundError(
            f"Arquivos ausentes em {data_dir}: {missing}. "
            "Clone https://github.com/Rafo044/Synthetic_Bank_Dataset e gere transactions.parquet "
            "(scripts/synthetic_data_create.py) ou copie a pasta data/."
        )


def _signed_amount(tx_type: str, amount: float) -> float:
    if tx_type == "deposit":
        return float(amount)
    if tx_type in ("withdrawal", "payment"):
        return -float(amount)
    if tx_type == "transfer":
        return -float(amount) * 0.5
    return 0.0


def _load_tables(data_dir: Path) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    _require_files(data_dir)
    customers = pd.read_csv(data_dir / "customers.csv", parse_dates=["dob", "account_open_date"])
    accounts = pd.read_csv(data_dir / "accounts.csv", parse_dates=["created_at"], low_memory=False)
    loans_path = data_dir / "loans.csv"
    loans = pd.read_csv(loans_path, parse_dates=["start_date", "end_date"]) if loans_path.exists() else pd.DataFrame()
    branches_path = data_dir / "branches.csv"
    branches = pd.read_csv(branches_path) if branches_path.exists() else pd.DataFrame()
    transactions = pd.read_parquet(data_dir / "transactions.parquet")
    return customers, accounts, loans, branches, transactions


def _prepare_transactions(
    transactions: pd.DataFrame,
    accounts: pd.DataFrame,
    status_filter: str = "completed",
) -> pd.DataFrame:
    tx = transactions.copy()
    if status_filter and "status" in tx.columns:
        tx = tx[tx["status"] == status_filter]
    tx["transaction_date"] = pd.to_datetime(tx["transaction_date"])
    tx = tx.merge(accounts[["account_id", "customer_id"]], on="account_id", how="inner")
    tx["signed"] = [
        _signed_amount(str(t), float(a))
        for t, a in zip(tx["transaction_type"], tx["amount"])
    ]
    tx["valor_creditos"] = np.where(tx["transaction_type"] == "deposit", tx["amount"], 0.0)
    tx["valor_debitos"] = np.where(
        tx["transaction_type"].isin(["withdrawal", "payment"]),
        tx["amount"],
        0.0,
    )
    tx = tx.sort_values(["account_id", "transaction_date", "transaction_id"])
    initial = accounts.set_index("account_id")["balance"].astype(float) * 0.1
    initial = initial.clip(lower=100.0)
    tx["balance"] = tx.groupby("account_id")["signed"].cumsum() + tx["account_id"].map(initial).fillna(100.0)
    tx["period"] = tx["transaction_date"].dt.to_period("M")
    return tx


def build_monthly_panel(
    data_dir: Path,
    max_customers: Optional[int] = None,
    min_months_history: int = 6,
) -> pd.DataFrame:
    """Agrega transações em painel mensal por cliente (sem saldo_alvo)."""
    customers, accounts, loans, branches, transactions = _load_tables(data_dir)
    tx = _prepare_transactions(transactions, accounts)

    if max_customers:
        keep = customers["customer_id"].drop_duplicates().head(max_customers)
        customers = customers[customers["customer_id"].isin(keep)]
        accounts = accounts[accounts["customer_id"].isin(keep)]
        tx = tx[tx["customer_id"].isin(keep)]

    monthly_acc = (
        tx.groupby(["customer_id", "account_id", "period"], as_index=False)
        .agg(
            saldo_conta=("balance", "last"),
            valor_creditos_mes=("valor_creditos", "sum"),
            valor_debitos_mes=("valor_debitos", "sum"),
            qtd_transacoes_mes=("transaction_id", "count"),
        )
    )
    monthly = (
        monthly_acc.groupby(["customer_id", "period"], as_index=False)
        .agg(
            saldo_raw=("saldo_conta", "sum"),
            valor_creditos_mes=("valor_creditos_mes", "sum"),
            valor_debitos_mes=("valor_debitos_mes", "sum"),
            qtd_transacoes_mes=("qtd_transacoes_mes", "sum"),
        )
    )
    monthly = monthly.sort_values(["customer_id", "period"])
    for lag in range(1, 7):
        monthly[f"saldo_m{lag}"] = monthly.groupby("customer_id")["saldo_raw"].shift(lag - 1)

    need = [f"saldo_m{i}" for i in range(1, 7)]
    monthly = monthly.dropna(subset=need).copy()
    if len(monthly) == 0:
        raise ValueError(
            "Painel mensal vazio após lags. Verifique transactions.parquet e histórico mínimo."
        )

    period_end = monthly["period"].dt.to_timestamp(how="end")
    monthly["data_referencia"] = period_end.dt.strftime("%Y-%m-%d")
    monthly["mes"] = period_end.dt.month
    monthly["ano"] = period_end.dt.year
    monthly["trimestre"] = ((monthly["mes"] - 1) // 3 + 1).astype(int)
    monthly["is_fim_de_ano"] = monthly["mes"].isin([11, 12]).astype(int)
    monthly["is_inicio_de_ano"] = (monthly["mes"] == 1).astype(int)

    panel = _attach_customer_profile(monthly, customers, accounts, loans, branches)

    if min_months_history > 1:
        counts = panel.groupby("cliente_id").size()
        keep_ids = counts[counts >= min_months_history].index
        panel = panel[panel["cliente_id"].isin(keep_ids)]

    return panel[TRAINING_COLUMNS].reset_index(drop=True)


def _attach_customer_profile(
    monthly: pd.DataFrame,
    customers: pd.DataFrame,
    accounts: pd.DataFrame,
    loans: pd.DataFrame,
    branches: pd.DataFrame,
) -> pd.DataFrame:
    ref = pd.Timestamp.now().normalize()
    cust = customers.copy()
    cust["cliente_id"] = cust["customer_id"]
    cust["idade"] = ((ref - pd.to_datetime(cust["dob"])).dt.days // 365).clip(18, 90)
    cust["genero"] = cust["gender"].astype(str).str.upper().str[0]
    cust["segmento"] = (
        cust["customer_segment"].astype(str).str.lower().map(SEGMENT_MAP).fillna("VAREJO")
    )

    if not branches.empty and "branch_code" in cust.columns:
        br = branches[["branch_code", "city"]].drop_duplicates()
        cust = cust.merge(br, on="branch_code", how="left")
        cust["uf"] = cust["city"].map(CITY_UF).fillna("VIC")
    else:
        cust["uf"] = "VIC"

    open_dt = pd.to_datetime(cust["account_open_date"])
    cust["tempo_relacionamento"] = (
        (ref - open_dt).dt.days // 30
    ).clip(1, 240).astype(int)

    active_accounts = (
        accounts[accounts["account_status"] == "active"]
        .groupby("customer_id")
        .size()
        .rename("qtd_produtos_ativos")
    )
    cust = cust.merge(active_accounts, left_on="customer_id", right_index=True, how="left")
    cust["qtd_produtos_ativos"] = cust["qtd_produtos_ativos"].fillna(1).astype(int)

    if not loans.empty:
        active_loans = (
            loans[loans["loan_status"] == "active"]
            .groupby("customer_id")
            .size()
            .rename("_n_loans")
        )
        cust = cust.merge(active_loans, left_on="customer_id", right_index=True, how="left")
        cust["possui_credito"] = (cust["_n_loans"].fillna(0) > 0).astype(int)
    else:
        cust["possui_credito"] = 0

    cust["possui_investimento"] = (cust["segmento"] == "PRIVATE").astype(int)
    cust["possui_seguro"] = (cust["segmento"].isin(["PRIME", "PRIVATE"])).astype(int)
    score_map = {"VAREJO": 650, "PRIME": 750, "PRIVATE": 850}
    cust["score_credito"] = cust["segmento"].map(score_map).fillna(650).astype(int)

    med_credit = monthly.groupby("customer_id")["valor_creditos_mes"].median()
    cust = cust.merge(med_credit.rename("_med_cred"), left_on="customer_id", right_index=True, how="left")
    cust["renda_mensal"] = (cust["_med_cred"].fillna(3000) * 1.25).clip(1000, 50000).round(2)

    profile_cols = [
        "cliente_id",
        "idade",
        "renda_mensal",
        "segmento",
        "tempo_relacionamento",
        "uf",
        "genero",
        "possui_investimento",
        "possui_credito",
        "possui_seguro",
        "score_credito",
        "qtd_produtos_ativos",
    ]
    profile = cust[profile_cols].drop_duplicates("cliente_id")

    out = monthly.merge(profile, left_on="customer_id", right_on="cliente_id", how="left")
    out["cliente_id"] = out["customer_id"]
    return out


def export_month_batch(panel: pd.DataFrame, year_month: str) -> pd.DataFrame:
    """Filtra um mês (YYYY-MM) para upload em ``incoming/``."""
    period = pd.Period(year_month, freq="M")
    mask = pd.to_datetime(panel["data_referencia"]).dt.to_period("M") == period
    batch = panel.loc[mask].copy()
    if batch.empty:
        raise ValueError(f"Nenhuma linha para o mês {year_month} no painel.")
    return batch


def split_initial_and_incoming(
    panel: pd.DataFrame,
    cutoff_month: str,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Divide histórico (treino base) e lote do mês seguinte para simular ingestão."""
    cutoff = pd.Period(cutoff_month, freq="M")
    periods = pd.to_datetime(panel["data_referencia"]).dt.to_period("M")
    initial = panel[periods < cutoff].copy()
    incoming = panel[periods == cutoff].copy()
    return initial, incoming
