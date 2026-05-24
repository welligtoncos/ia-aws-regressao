"""Persiste histórico de métricas por run para evolução no Athena."""

import json
import logging
from datetime import datetime, timezone

import boto3
import pandas as pd

logger = logging.getLogger(__name__)


def _safe_int(value, default: int = 0) -> int:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except TypeError:
        pass
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def save_metrics_history(metricas, meta, bucket, table, database, region="us-east-1"):
    import pyarrow as pa
    import pyarrow.parquet as pq
    from catalog_sync import register_metrics_partition

    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    run_id = meta.get("run_id", "manual")
    row = {
        **metricas,
        "modelo_versao": meta.get("modelo_versao", ""),
        "dt_processamento": datetime.now(timezone.utc).isoformat(),
        "total_linhas": _safe_int(meta.get("total_linhas", 0)),
        "linhas_adicionadas": _safe_int(meta.get("linhas_adicionadas", 0)),
        "data_referencia_lote": meta.get("data_referencia_lote", ""),
        "is_champion": bool(meta.get("is_champion", False)),
        "champion_modelo_versao": meta.get("champion_modelo_versao") or "",
        "champion_rmse": float(meta.get("champion_rmse") or 0),
        "champion_wape": float(meta.get("champion_wape") or 0),
        "champion_mape": float(meta.get("champion_mape") or 0),
        "metricas_segmento": json.dumps(meta.get("metricas_segmento") or {}, ensure_ascii=False),
        "metricas_baseline": json.dumps(meta.get("metricas_baseline") or {}, ensure_ascii=False),
    }
    df = pd.DataFrame([row])
    prefix = f"processed/{table}"
    key = f"{prefix}/run_date={run_date}/run_id={run_id}/metrics.parquet"

    import io
    buf = io.BytesIO()
    pq.write_table(pa.Table.from_pandas(df), buf)
    boto3.client("s3", region_name=region).put_object(
        Bucket=bucket, Key=key, Body=buf.getvalue()
    )
    if database:
        register_metrics_partition(bucket, database, table, run_date, run_id, prefix, region)
    logger.info("Métricas históricas: s3://%s/%s", bucket, key)
