"""Promoção de modelo campeão (champion) com base em métricas de holdout."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

CHAMPION_PREFIX = "champion"
# WAPE primária: melhoria mínima em pontos percentuais (ex.: 24,29 → ≤ 23,29).
CHAMPION_MIN_WAPE_IMPROVEMENT_PP = 1.0
# R² não pode cair mais que este valor vs champion.
CHAMPION_MAX_R2_REGRESSION = 0.01
# Legado (documentação antiga); promoção não usa mais RMSE como gate.
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


def evaluate_champion_promotion(
    new_metrics: Dict[str, Any],
    champion_metrics: Optional[Dict[str, Any]],
    *,
    new_total_linhas: int = 0,
    min_wape_improvement_pp: float = CHAMPION_MIN_WAPE_IMPROVEMENT_PP,
    max_r2_regression: float = CHAMPION_MAX_R2_REGRESSION,
) -> Tuple[bool, str]:
    """
    Critérios para promover (todos obrigatórios se já existir champion):
      1. WAPE pelo menos min_wape_improvement_pp menor que o champion (métrica primária).
      2. R² não piora mais que max_r2_regression vs champion.
      3. total_linhas do treino >= total_linhas gravado no champion.
    """
    if not champion_metrics:
        return True, "primeiro_champion"

    new_wape = float(new_metrics.get("wape", float("inf")))
    champ_wape = float(champion_metrics.get("wape", float("inf")))
    new_r2 = float(new_metrics.get("r2", 0.0))
    champ_r2 = float(champion_metrics.get("r2", 0.0))
    champ_linhas = int(champion_metrics.get("total_linhas") or 0)

    if new_wape > champ_wape - min_wape_improvement_pp + 1e-9:
        return (
            False,
            f"wape: {new_wape:.2f}% nao melhorou >= {min_wape_improvement_pp} p.p. vs champion {champ_wape:.2f}%",
        )

    if new_r2 < champ_r2 - max_r2_regression - 1e-9:
        return (
            False,
            f"r2: {new_r2:.4f} piorou mais que {max_r2_regression} vs champion {champ_r2:.4f}",
        )

    if new_total_linhas < champ_linhas:
        return (
            False,
            f"total_linhas: {new_total_linhas} < champion {champ_linhas}",
        )

    return True, "criterios_atendidos"


def is_better_than_champion(
    new_metrics: Dict[str, float],
    champion_metrics: Optional[Dict[str, Any]],
    *,
    new_total_linhas: int = 0,
    min_wape_improvement_pp: float = CHAMPION_MIN_WAPE_IMPROVEMENT_PP,
    max_r2_regression: float = CHAMPION_MAX_R2_REGRESSION,
    min_rmse_improvement: float = CHAMPION_MIN_RMSE_IMPROVEMENT,  # noqa: ARG001 — legado
) -> bool:
    ok, _ = evaluate_champion_promotion(
        new_metrics,
        champion_metrics,
        new_total_linhas=new_total_linhas,
        min_wape_improvement_pp=min_wape_improvement_pp,
        max_r2_regression=max_r2_regression,
    )
    return ok


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


def _metrics_for_registry(
    metricas: Dict[str, float],
    meta: Dict[str, Any],
    modelo_versao: str,
) -> Dict[str, Any]:
    return {
        **metricas,
        "modelo_versao": modelo_versao,
        "total_linhas": int(meta.get("total_linhas") or 0),
        "dataset_fingerprint": meta.get("dataset_fingerprint") or "",
    }


def maybe_promote_champion(
    model,
    metricas: Dict[str, float],
    feature_importance: Dict[str, Any],
    meta: Dict[str, Any],
    bucket: str,
    model_path: str,
    region: str = "us-east-1",
) -> Dict[str, Any]:
    """Promove run atual a campeão se WAPE, R² e volume de dados atenderem aos critérios."""
    base = model_path.rstrip("/")
    champion_prefix = f"{base}/{CHAMPION_PREFIX}"
    run_id = meta.get("run_id", "manual")
    modelo_versao = meta.get("modelo_versao", "")
    total_linhas = int(meta.get("total_linhas") or 0)

    current = load_champion_metrics(bucket, model_path, region)
    ok, reason = evaluate_champion_promotion(
        metricas, current, new_total_linhas=total_linhas
    )
    if not ok:
        logger.info(
            "Sem promoção (%s): wape=%s r2=%s linhas=%s | champion wape=%s r2=%s linhas=%s",
            reason,
            metricas.get("wape"),
            metricas.get("r2"),
            total_linhas,
            current.get("wape") if current else None,
            current.get("r2") if current else None,
            current.get("total_linhas") if current else None,
        )
        return {
            "promoted": False,
            "is_champion": False,
            "promotion_reason": reason,
            "champion_modelo_versao": current.get("modelo_versao") if current else None,
            "champion_rmse": current.get("rmse") if current else None,
            "champion_wape": current.get("wape") if current else None,
        }

    registry_metrics = _metrics_for_registry(metricas, meta, modelo_versao)
    save_model_s3(model, bucket, f"{champion_prefix}/model.ubj", region)
    _put_json(bucket, f"{champion_prefix}/metrics.json", registry_metrics, region)
    _put_json(bucket, f"{champion_prefix}/feature_importance.json", feature_importance, region)

    promotion = {
        "modelo_versao": modelo_versao,
        "run_id": run_id,
        "promoted_at": datetime.now(timezone.utc).isoformat(),
        "promotion_reason": reason,
        **registry_metrics,
        **{k: meta[k] for k in ("linhas_adicionadas", "data_referencia_lote") if k in meta},
    }
    _put_json(bucket, f"{champion_prefix}/champion_meta.json", promotion, region)
    _put_json(bucket, f"{champion_prefix}/history/{run_id}.json", promotion, region)

    logger.info(
        "Modelo promovido a champion: %s run_id=%s wape=%s r2=%s linhas=%s",
        modelo_versao,
        run_id,
        metricas.get("wape"),
        metricas.get("r2"),
        total_linhas,
    )
    return {
        "promoted": True,
        "is_champion": True,
        "promotion_reason": reason,
        "champion_modelo_versao": modelo_versao,
        "champion_rmse": metricas["rmse"],
        "champion_wape": metricas.get("wape"),
    }
