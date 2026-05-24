"""Modelo XGBoost — bundle flat para AWS Glue Python Shell."""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


logger = logging.getLogger(__name__)

XGBOOST_PARAMS = {
    "n_estimators": 300, "max_depth": 6, "learning_rate": 0.05,
    "subsample": 0.8, "colsample_bytree": 0.8, "min_child_weight": 5,
    "gamma": 0.1, "reg_alpha": 0.1, "reg_lambda": 1.0, "random_state": 42,
    "objective": "reg:squarederror", "eval_metric": "rmse", "early_stopping_rounds": 20,
}

_INT_PARAMS = {"n_estimators", "max_depth", "min_child_weight", "early_stopping_rounds", "random_state"}
_FLOAT_PARAMS = {
    "learning_rate", "subsample", "colsample_bytree", "gamma",
    "reg_alpha", "reg_lambda", "min_split_loss",
}


def _coerce_xgboost_params(params):
    coerced = {}
    for key, value in params.items():
        if isinstance(value, str):
            if key in _INT_PARAMS:
                coerced[key] = int(float(value))
            elif key in _FLOAT_PARAMS:
                coerced[key] = float(value)
            else:
                coerced[key] = value
        else:
            coerced[key] = value
    return coerced


def mape(y_true, y_pred):
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    mask = y_true != 0
    if not mask.any():
        return 0.0
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)


def wape(y_true, y_pred):
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    denom = np.abs(y_true).sum()
    if denom <= 0:
        return 0.0
    return float(np.abs(y_true - y_pred).sum() / denom * 100)


def smape(y_true, y_pred):
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    denom = (np.abs(y_true) + np.abs(y_pred)) / 2.0
    mask = denom > 0
    if not mask.any():
        return 0.0
    return float(np.mean(np.abs(y_true[mask] - y_pred[mask]) / denom[mask]) * 100)


def calcular_metricas(y_true, y_pred):
    return {
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "r2": float(r2_score(y_true, y_pred)),
        "wape": wape(y_true, y_pred),
        "smape": smape(y_true, y_pred),
        "mape": mape(y_true, y_pred),
    }


COLUNAS_HISTORICO_SALDO = [
    "saldo_m1", "saldo_m2", "saldo_m3", "saldo_m4", "saldo_m5", "saldo_m6",
]


def calcular_baselines_holdout(meta_df, y_true):
    """
    Baselines no holdout de teste (mesmo y_true do modelo).
    - naive_saldo_m1: persiste saldo_m1 como previsão do próximo período (saldo_alvo).
    - media_saldos_m1_m6: média de saldo_m1..m6 quando disponível.
    """
    y_true = np.asarray(y_true, dtype=float)
    out = {}
    if "saldo_m1" in meta_df.columns:
        y_naive = meta_df["saldo_m1"].astype(float).values
        out["naive_saldo_m1"] = calcular_metricas(y_true, y_naive)
    hist = [c for c in meta_df.columns if c in COLUNAS_HISTORICO_SALDO]
    if hist:
        y_ma = meta_df[hist].astype(float).mean(axis=1).values
        out["media_saldos_m1_m6"] = calcular_metricas(y_true, y_ma)
    return out


def resumo_baselines_vs_modelo(metricas_modelo, baselines):
    """Compara WAPE do modelo com baselines para logs e Athena."""
    model_wape = float(metricas_modelo.get("wape", 0))
    resumo = {"modelo_wape": round(model_wape, 4), "baselines": baselines}
    naive = baselines.get("naive_saldo_m1", {})
    if naive:
        nw = float(naive.get("wape", 0))
        resumo["naive_wape"] = round(nw, 4)
        resumo["beats_naive"] = model_wape < nw - 1e-9
        resumo["wape_gain_vs_naive_pp"] = round(nw - model_wape, 4)
    media = baselines.get("media_saldos_m1_m6", {})
    if media:
        mw = float(media.get("wape", 0))
        resumo["media_saldos_wape"] = round(mw, 4)
        resumo["beats_media_saldos"] = model_wape < mw - 1e-9
    return resumo


def calcular_metricas_por_segmento(meta_df, y_true, y_pred, segment_col="segmento"):
    if segment_col not in meta_df.columns:
        return {}
    segments = meta_df[segment_col].astype(str).values
    out = {}
    for seg in sorted(set(segments)):
        mask = segments == seg
        if mask.sum() < 2:
            continue
        out[seg] = calcular_metricas(y_true[mask], y_pred[mask])
    return out


def treinar_modelo(x_train, y_train, x_val, y_val, params=None):
    cfg = _coerce_xgboost_params({**XGBOOST_PARAMS, **(params or {})})
    early_stopping = cfg.pop("early_stopping_rounds", 20)
    eval_metric = cfg.pop("eval_metric", "rmse")
    model = xgb.XGBRegressor(**cfg, eval_metric=eval_metric, early_stopping_rounds=early_stopping)
    model.fit(x_train, y_train, eval_set=[(x_val, y_val)], verbose=False)
    return model


def extrair_feature_importance(model, feature_names, top_n=10):
    ranking = sorted(zip(feature_names, model.feature_importances_), key=lambda x: x[1], reverse=True)
    return {
        "top_features": [{"feature": f, "importance": float(v)} for f, v in ranking[:top_n]],
        "all_features": {f: float(v) for f, v in ranking},
    }


def salvar_json_s3(data, bucket, key, region="us-east-1"):
    import boto3
    boto3.client("s3", region_name=region).put_object(
        Bucket=bucket, Key=key,
        Body=json.dumps(data, indent=2, ensure_ascii=False),
        ContentType="application/json",
    )


def gerar_predicoes_output(df_original, y_pred, y_real, modelo_versao, run_id="manual"):
    from columns import COL_PREDITO, COL_REALIZADO, TARGET_ALVO

    saldo_observado = (
        y_real
        if y_real is not None
        else df_original.get(TARGET_ALVO, df_original.get("saldo_previsto", pd.Series(y_pred))).values
    )
    out = pd.DataFrame({
        "cliente_id": df_original["cliente_id"].values,
        "data_referencia": df_original["data_referencia"].values,
        COL_PREDITO: y_pred,
        COL_REALIZADO: saldo_observado,
        "segmento": df_original["segmento"].values,
        "uf": df_original["uf"].values,
        "dt_processamento": datetime.now(timezone.utc).isoformat(),
        "modelo_versao": modelo_versao,
        "run_id": run_id,
    })
    out["erro_absoluto"] = (out[COL_REALIZADO] - out[COL_PREDITO]).abs()
    out["erro_percentual"] = np.where(
        out[COL_REALIZADO] != 0, out["erro_absoluto"] / out[COL_REALIZADO].abs() * 100, 0
    )
    out["ano"] = df_original["ano"].values
    out["mes"] = df_original["mes"].values
    return out
