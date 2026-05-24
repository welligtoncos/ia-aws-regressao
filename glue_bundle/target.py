"""Alvo futuro (saldo do próximo período) e split temporal sem vazamento."""

from __future__ import annotations

from typing import Tuple

import pandas as pd

TARGET = "saldo_previsto"
META_AUX_COL = "_proxima_data"


def assign_forward_target(df: pd.DataFrame, target_col: str = TARGET) -> pd.DataFrame:
    required = {"cliente_id", "data_referencia", "saldo_m1"}
    if not required.issubset(df.columns):
        return df

    out = df.sort_values(["cliente_id", "data_referencia"]).copy()
    out[target_col] = out.groupby("cliente_id", sort=False)["saldo_m1"].shift(-1)
    out[META_AUX_COL] = out.groupby("cliente_id", sort=False)["data_referencia"].shift(-1)
    return out.dropna(subset=[target_col]).reset_index(drop=True)


def temporal_train_val_test_split(
    x: pd.DataFrame,
    y: pd.Series,
    meta_df: pd.DataFrame,
    test_frac: float = 0.2,
    val_frac: float = 0.15,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, pd.Series]:
    meta = meta_df.loc[x.index].copy()
    meta["data_referencia"] = pd.to_datetime(meta["data_referencia"])
    if META_AUX_COL in meta.columns:
        meta[META_AUX_COL] = pd.to_datetime(meta[META_AUX_COL])

    ordered_idx = meta["data_referencia"].sort_values().index
    n = len(ordered_idx)
    if n < 10:
        split_at = max(1, int(n * (1 - test_frac)))
        train_idx = ordered_idx[:split_at]
        test_idx = ordered_idx[split_at:]
        val_cut = max(1, int(len(train_idx) * (1 - val_frac)))
        return (
            x.loc[train_idx[:val_cut]],
            x.loc[train_idx[val_cut:]],
            x.loc[test_idx],
            y.loc[train_idx[:val_cut]],
            y.loc[train_idx[val_cut:]],
            y.loc[test_idx],
        )

    cutoff_test = meta.loc[ordered_idx, "data_referencia"].quantile(1 - test_frac)
    trainval_mask = meta["data_referencia"] < cutoff_test
    if META_AUX_COL in meta.columns:
        trainval_mask &= meta[META_AUX_COL] < cutoff_test
    test_mask = meta["data_referencia"] >= cutoff_test

    trainval_idx = meta.index[trainval_mask]
    test_idx = meta.index[test_mask]

    tv_dates = meta.loc[trainval_idx, "data_referencia"].sort_values()
    cutoff_val = tv_dates.quantile(1 - val_frac) if len(tv_dates) > 1 else tv_dates.iloc[0]
    train_idx = meta.loc[trainval_idx].index[meta.loc[trainval_idx, "data_referencia"] < cutoff_val]
    val_idx = meta.loc[trainval_idx].index[meta.loc[trainval_idx, "data_referencia"] >= cutoff_val]

    if len(train_idx) == 0 or len(val_idx) == 0:
        split_at = max(1, int(n * (1 - test_frac)))
        train_idx = ordered_idx[:split_at]
        test_idx = ordered_idx[split_at:]
        val_cut = max(1, int(len(train_idx) * (1 - val_frac)))
        return (
            x.loc[train_idx[:val_cut]],
            x.loc[train_idx[val_cut:]],
            x.loc[test_idx],
            y.loc[train_idx[:val_cut]],
            y.loc[train_idx[val_cut:]],
            y.loc[test_idx],
        )

    return (
        x.loc[train_idx],
        x.loc[val_idx],
        x.loc[test_idx],
        y.loc[train_idx],
        y.loc[val_idx],
        y.loc[test_idx],
    )
