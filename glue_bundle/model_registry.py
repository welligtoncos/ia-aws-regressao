"""Promoção de modelo campeão (champion) com base em métricas de holdout."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

CHAMPION_PREFIX = "champion"
CHAMPION_MIN_RMSE_IMPROVEMENT = 0.02


def _s3():
    return boto3.client("s3")


def load_champion_metrics(bucket: str, model_path: str, region: str = "us-east-1") -> Optional[Dict[str, Any]]:
    key = f"{model_path.rstrip('/')}/{CHAMPION_PREFIX}/metrics.json"
    try:
        obj = _s3().get_object(Bucket=bucket, Key=key)
        return json.loads(obj["Body"].read().decode("utf-8"))
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return None
        raise


def is_better_than_champion(
    new_metrics: Dict[str, float],
    champion_metrics: Optional[Dict[str, Any]],
    min_rmse_improvement: float = CHAMPION_MIN_RMSE_IMPROVEMENT,
) -> bool:
    """Promove se RMSE melhorar pelo menos min_rmse_improvement (padrão 2%)."""
    if not champion_metrics:
        return True
    new_rmse = float(new_metrics["rmse"])
    champ_rmse = float(champion_metrics.get("rmse", float("inf")))
    if champ_rmse <= 0:
        return new_rmse < champ_rmse - 1e-9
    threshold = champ_rmse * (1.0 - min_rmse_improvement)
    return new_rmse < threshold - 1e-9


def _put_json(bucket: str, key: str, data: Dict[str, Any], region: str) -> None:
    _s3().put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(data, indent=2, ensure_ascii=False),
        ContentType="application/json",
    )


def save_model_s3(model, bucket: str, key: str, region: str = "us-east-1") -> None:
    with tempfile.NamedTemporaryFile(suffix=".ubj", delete=False) as tmp:
        path = tmp.name
    try:
        model.save_model(path)
        _s3().upload_file(path, bucket, key)
    finally:
        if os.path.exists(path):
            os.unlink(path)


def maybe_promote_champion(
    model,
    metricas: Dict[str, float],
    feature_importance: Dict[str, Any],
    meta: Dict[str, Any],
    bucket: str,
    model_path: str,
    region: str = "us-east-1",
) -> Dict[str, Any]:
    """Promove run atual a campeão se RMSE melhorar >= 2% vs champion atual."""
    base = model_path.rstrip("/")
    champion_prefix = f"{base}/{CHAMPION_PREFIX}"
    run_id = meta.get("run_id", "manual")
    modelo_versao = meta.get("modelo_versao", "")

    current = load_champion_metrics(bucket, model_path, region)
    if not is_better_than_champion(metricas, current):
        logger.info(
            "Sem promoção: rmse=%s wape=%s (champion rmse=%s wape=%s)",
            metricas["rmse"],
            metricas.get("wape"),
            current.get("rmse") if current else None,
            current.get("wape") if current else None,
        )
        return {
            "promoted": False,
            "is_champion": False,
            "champion_modelo_versao": current.get("modelo_versao") if current else None,
            "champion_rmse": current.get("rmse") if current else None,
            "champion_wape": current.get("wape") if current else None,
        }

    save_model_s3(model, bucket, f"{champion_prefix}/model.ubj", region)
    _put_json(bucket, f"{champion_prefix}/metrics.json", metricas, region)
    _put_json(bucket, f"{champion_prefix}/feature_importance.json", feature_importance, region)

    promotion = {
        "modelo_versao": modelo_versao,
        "run_id": run_id,
        "promoted_at": datetime.now(timezone.utc).isoformat(),
        **metricas,
        **{k: meta[k] for k in ("total_linhas", "linhas_adicionadas", "data_referencia_lote") if k in meta},
    }
    _put_json(bucket, f"{champion_prefix}/champion_meta.json", promotion, region)
    _put_json(bucket, f"{champion_prefix}/history/{run_id}.json", promotion, region)

    logger.info(
        "Modelo promovido a champion: %s run_id=%s rmse=%s wape=%s",
        modelo_versao,
        run_id,
        metricas["rmse"],
        metricas.get("wape"),
    )
    return {
        "promoted": True,
        "is_champion": True,
        "champion_modelo_versao": modelo_versao,
        "champion_rmse": metricas["rmse"],
        "champion_wape": metricas.get("wape"),
    }
