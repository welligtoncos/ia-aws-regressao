"""Treinamento e avaliação XGBoost para previsão de saldo."""

import json
import logging
import time
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

logger = logging.getLogger(__name__)

XGBOOST_PARAMS = {
    "n_estimators": 300,
    "max_depth": 6,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 5,
    "gamma": 0.1,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "random_state": 42,
    "objective": "reg:squarederror",
    "eval_metric": "rmse",
    "early_stopping_rounds": 20,
}

_INT_PARAMS = {"n_estimators", "max_depth", "min_child_weight", "early_stopping_rounds", "random_state"}
_FLOAT_PARAMS = {
    "learning_rate", "subsample", "colsample_bytree", "gamma",
    "reg_alpha", "reg_lambda", "min_split_loss",
}


def _coerce_xgboost_params(params: Dict[str, Any]) -> Dict[str, Any]:
    coerced: Dict[str, Any] = {}
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


def mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Erro percentual absoluto médio (diagnóstico; instável com saldos baixos)."""
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    mask = y_true != 0
    if not mask.any():
        return 0.0
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)


def wape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Weighted APE: sum(|erro|) / sum(|real|) * 100."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    denom = np.abs(y_true).sum()
    if denom <= 0:
        return 0.0
    return float(np.abs(y_true - y_pred).sum() / denom * 100)


def smape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Symmetric MAPE (%)."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    denom = (np.abs(y_true) + np.abs(y_pred)) / 2.0
    mask = denom > 0
    if not mask.any():
        return 0.0
    return float(np.mean(np.abs(y_true[mask] - y_pred[mask]) / denom[mask]) * 100)


def calcular_metricas(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    return {
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "r2": float(r2_score(y_true, y_pred)),
        "wape": wape(y_true, y_pred),
        "smape": smape(y_true, y_pred),
        "mape": mape(y_true, y_pred),
    }


def calcular_metricas_por_segmento(
    meta_df: pd.DataFrame,
    y_true: np.ndarray,
    y_pred: np.ndarray,
    segment_col: str = "segmento",
) -> Dict[str, Dict[str, float]]:
    """Métricas estratificadas por segmento no holdout de teste."""
    if segment_col not in meta_df.columns:
        return {}
    segments = meta_df[segment_col].astype(str).values
    out: Dict[str, Dict[str, float]] = {}
    for seg in sorted(set(segments)):
        mask = segments == seg
        if mask.sum() < 2:
            continue
        out[seg] = calcular_metricas(y_true[mask], y_pred[mask])
    return out


def treinar_modelo(
    x_train: pd.DataFrame,
    y_train: pd.Series,
    x_val: pd.DataFrame,
    y_val: pd.Series,
    params: Optional[Dict[str, Any]] = None,
) -> xgb.XGBRegressor:
    inicio = time.time()
    cfg = _coerce_xgboost_params({**XGBOOST_PARAMS, **(params or {})})
    early_stopping = cfg.pop("early_stopping_rounds", 20)
    eval_metric = cfg.pop("eval_metric", "rmse")

    model = xgb.XGBRegressor(**cfg, eval_metric=eval_metric, early_stopping_rounds=early_stopping)
    model.fit(
        x_train,
        y_train,
        eval_set=[(x_val, y_val)],
        verbose=False,
    )
    logger.info("Modelo treinado em %.2fs", time.time() - inicio)
    return model


def extrair_feature_importance(model: xgb.XGBRegressor, feature_names: list, top_n: int = 10) -> Dict[str, Any]:
    importances = model.feature_importances_
    ranking = sorted(
        zip(feature_names, importances),
        key=lambda x: x[1],
        reverse=True,
    )
    top = ranking[:top_n]
    return {
        "top_features": [{"feature": f, "importance": float(v)} for f, v in top],
        "all_features": {f: float(v) for f, v in ranking},
    }


def salvar_json_s3(data: dict, bucket: str, key: str, region: str = "us-east-1") -> None:
    import boto3

    client = boto3.client("s3", region_name=region)
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(data, indent=2, ensure_ascii=False),
        ContentType="application/json",
    )
    logger.info("JSON salvo em s3://%s/%s", bucket, key)


def gerar_predicoes_output(
    df_original: pd.DataFrame,
    y_pred: np.ndarray,
    y_real: Optional[np.ndarray],
    modelo_versao: str,
) -> pd.DataFrame:
    """Monta DataFrame de saída no formato da tabela Glue."""
    from datetime import datetime, timezone

    try:
        from workloads.shared.columns import COL_PREDITO, COL_REALIZADO, TARGET_ALVO
    except ImportError:
        from app.src.preprocessor import TARGET as TARGET_ALVO
        COL_PREDITO = "saldo_predito"
        COL_REALIZADO = "saldo_realizado"

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
    })
    out["erro_absoluto"] = (out[COL_REALIZADO] - out[COL_PREDITO]).abs()
    out["erro_percentual"] = np.where(
        out[COL_REALIZADO] != 0,
        out["erro_absoluto"] / out[COL_REALIZADO].abs() * 100,
        0,
    )
    out["ano"] = df_original["ano"].values
    out["mes"] = df_original["mes"].values
    return out
