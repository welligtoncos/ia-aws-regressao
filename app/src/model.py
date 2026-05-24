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
    """Erro percentual absoluto médio."""
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    mask = y_true != 0
    if not mask.any():
        return 0.0
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)


def calcular_metricas(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    return {
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "r2": float(r2_score(y_true, y_pred)),
        "mape": mape(y_true, y_pred),
    }


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
        from src.preprocessor import TARGET
    except ImportError:
        from app.src.preprocessor import TARGET

    saldo_real = y_real if y_real is not None else df_original.get(TARGET, pd.Series(y_pred)).values

    out = pd.DataFrame({
        "cliente_id": df_original["cliente_id"].values,
        "data_referencia": df_original["data_referencia"].values,
        "saldo_previsto": y_pred,
        "saldo_real": saldo_real,
        "segmento": df_original["segmento"].values,
        "uf": df_original["uf"].values,
        "dt_processamento": datetime.now(timezone.utc).isoformat(),
        "modelo_versao": modelo_versao,
    })
    out["erro_absoluto"] = (out["saldo_real"] - out["saldo_previsto"]).abs()
    out["erro_percentual"] = np.where(
        out["saldo_real"] != 0,
        out["erro_absoluto"] / out["saldo_real"].abs() * 100,
        0,
    )
    out["ano"] = df_original["ano"].values
    out["mes"] = df_original["mes"].values
    return out
