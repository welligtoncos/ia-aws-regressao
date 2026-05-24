"""Pipeline de treino XGBoost — bundle flat para AWS Glue Python Shell."""

import hashlib
import json
import logging
import os
import sys
import time
from io import StringIO

import boto3
import pandas as pd
from sklearn.model_selection import train_test_split

from catalog_sync import register_partitions
from incremental_data import ingest_simulated
from metrics_history import save_metrics_history
from model import calcular_metricas, extrair_feature_importance, gerar_predicoes_output, salvar_json_s3, treinar_modelo
from preprocessor import TARGET, Preprocessor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def _load_config_from_glue():
    try:
        from awsglue.utils import getResolvedOptions
        keys = [
            "INPUT_BUCKET", "INPUT_KEY", "OUTPUT_BUCKET", "OUTPUT_DATABASE", "OUTPUT_TABLE",
            "TARGET_COLUMN", "MODE",
        ]
        optional = [
            "MODEL_OUTPUT_PATH", "XGBOOST_PARAMS", "AWS_REGION", "run_id",
            "INGEST_DAILY", "INGEST_MODE", "INCREMENTAL_STEP_MINUTES",
            "INCREMENTAL_NEW_CLIENTS", "INCREMENTAL_SEED_CLIENTES", "INCOMING_KEYS",
            "METRICS_TABLE", "METRICS_DATABASE",
        ]
        present = [k for k in keys + optional if f"--{k}" in sys.argv]
        return getResolvedOptions(sys.argv, present)
    except ImportError:
        return {}


def _parse_xgboost_params(raw):
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        return json.loads(raw)
    return {}


def _parse_incoming_keys(raw):
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        raw = raw.strip()
        if raw.startswith("["):
            return json.loads(raw)
        return [k.strip() for k in raw.split(",") if k.strip()]
    return []


def _as_bool(value):
    return str(value).lower() in ("1", "true", "yes")


def read_csv_s3(bucket, key, region):
    obj = boto3.client("s3", region_name=region).get_object(Bucket=bucket, Key=key)
    return pd.read_csv(StringIO(obj["Body"].read().decode("utf-8")))


def write_parquet_s3_partitioned(df, bucket, prefix, region):
    import pyarrow as pa
    import pyarrow.parquet as pq
    for (ano, mes, segmento), group in df.groupby(["ano", "mes", "segmento"]):
        table = pa.Table.from_pandas(group.drop(columns=["ano", "mes", "segmento"], errors="ignore"))
        buf = pa.BufferOutputStream()
        pq.write_table(table, buf)
        key = f"{prefix}/ano={ano}/mes={mes}/segmento={segmento}/data.parquet"
        boto3.client("s3", region_name=region).put_object(Bucket=bucket, Key=key, Body=buf.getvalue().to_pybytes())


def _split_train_test(x, y, df_source, ingest_daily):
    if ingest_daily and "data_referencia" in df_source.columns:
        refs = df_source.loc[x.index, "data_referencia"]
        order = refs.sort_values().index
        x = x.loc[order]
        y = y.loc[order]
        split_at = int(len(x) * 0.8)
        return x.iloc[:split_at], x.iloc[split_at:], y.iloc[:split_at], y.iloc[split_at:]
    return train_test_split(x, y, test_size=0.2, random_state=42)


def run_pipeline(config):
    inicio = time.time()
    region = config.get("AWS_REGION", "us-east-1")
    run_id = config.get("run_id", "manual")
    ingest_enabled = _as_bool(config.get("INGEST_DAILY", "false"))
    incoming_keys = _parse_incoming_keys(config.get("INCOMING_KEYS", "[]"))
    ingest_meta = {}

    if ingest_enabled or incoming_keys:
        ingest_meta = ingest_simulated(
            bucket=config["INPUT_BUCKET"],
            key=config["INPUT_KEY"],
            region=region,
            run_id=run_id,
            seed_clientes=int(config.get("INCREMENTAL_SEED_CLIENTES", 5000)),
            new_clients=int(config.get("INCREMENTAL_NEW_CLIENTS", 10)),
            mode=config.get("INGEST_MODE", "daily"),
            step_minutes=int(config.get("INCREMENTAL_STEP_MINUTES", 10)),
            incoming_keys=incoming_keys,
            skip_simulated=not ingest_enabled,
        )
        logger.info("Ingestão: %s", ingest_meta)

    df = read_csv_s3(config["INPUT_BUCKET"], config["INPUT_KEY"], region)
    logger.info("Dataset: %s", df.shape)

    prep = Preprocessor()
    x, y = prep.fit_transform(df)
    x_train, x_test, y_train, y_test = _split_train_test(x, y, df, ingest_enabled or bool(incoming_keys))
    xgb_params = _parse_xgboost_params(config.get("XGBOOST_PARAMS", "{}"))
    model = treinar_modelo(x_train, y_train, x_test, y_test, xgb_params)
    y_pred = model.predict(x_test)
    metricas = calcular_metricas(y_test.values, y_pred)

    model_path = config.get("MODEL_OUTPUT_PATH", "models/xgboost_saldo/")
    out_bucket = config["OUTPUT_BUCKET"]
    model_hash = hashlib.md5(json.dumps(metricas, sort_keys=True).encode()).hexdigest()[:8]
    modelo_versao = f"xgb-saldo-v1-{model_hash}"

    fi = extrair_feature_importance(model, list(x.columns))
    ingest_meta_for_champion = {
        "run_id": run_id,
        "modelo_versao": modelo_versao,
        "total_linhas": len(df),
        "linhas_adicionadas": ingest_meta.get("rows_added", 0),
        "data_referencia_lote": ingest_meta.get("data_referencia", ""),
    }
    from model_registry import maybe_promote_champion

    champion_result = maybe_promote_champion(
        model, metricas, fi, ingest_meta_for_champion, out_bucket, model_path, region
    )

    salvar_json_s3(metricas, out_bucket, f"{model_path}metricas.json", region)
    salvar_json_s3(fi, out_bucket, f"{model_path}feature_importance.json", region)
    salvar_json_s3(
        {**metricas, "run_id": run_id, "modelo_versao": modelo_versao, **ingest_meta, **champion_result},
        out_bucket,
        f"{model_path}history/{run_id}.json",
        region,
    )

    metrics_table = config.get("METRICS_TABLE", "tb_metricas_treino")
    metrics_db = config.get("METRICS_DATABASE") or config.get("OUTPUT_DATABASE", "")
    save_metrics_history(
        metricas,
        {
            **ingest_meta_for_champion,
            **champion_result,
        },
        out_bucket,
        metrics_table,
        metrics_db,
        region,
    )

    test_idx = y_test.index
    df_out = gerar_predicoes_output(
        df.loc[test_idx].reset_index(drop=True), y_pred, y_test.values, modelo_versao, run_id=run_id
    )
    table = config.get("OUTPUT_TABLE", "tb_saldo_previsto")
    database = config.get("OUTPUT_DATABASE", "")
    prefix = f"processed/{table}"
    write_parquet_s3_partitioned(df_out, out_bucket, prefix, region)
    register_partitions(df_out, out_bucket, database, table, prefix, region)

    logger.info("Pipeline OK em %.2fs", time.time() - inicio)
    return {"metricas": metricas, "modelo_versao": modelo_versao, "ingest": ingest_meta}


def main():
    glue_cfg = _load_config_from_glue()
    config = {
        "INPUT_BUCKET": glue_cfg["INPUT_BUCKET"],
        "INPUT_KEY": glue_cfg["INPUT_KEY"],
        "OUTPUT_BUCKET": glue_cfg["OUTPUT_BUCKET"],
        "OUTPUT_TABLE": glue_cfg.get("OUTPUT_TABLE", "tb_saldo_previsto"),
        "OUTPUT_DATABASE": glue_cfg.get("OUTPUT_DATABASE", ""),
        "METRICS_TABLE": glue_cfg.get("METRICS_TABLE", "tb_metricas_treino"),
        "METRICS_DATABASE": glue_cfg.get("METRICS_DATABASE", glue_cfg.get("OUTPUT_DATABASE", "")),
        "MODEL_OUTPUT_PATH": glue_cfg.get("MODEL_OUTPUT_PATH", "models/xgboost_saldo/"),
        "XGBOOST_PARAMS": glue_cfg.get("XGBOOST_PARAMS", "{}"),
        "AWS_REGION": glue_cfg.get("AWS_REGION", os.getenv("AWS_REGION", "us-east-1")),
        "run_id": glue_cfg.get("run_id", "manual"),
        "INGEST_DAILY": glue_cfg.get("INGEST_DAILY", "false"),
        "INGEST_MODE": glue_cfg.get("INGEST_MODE", "daily"),
        "INCREMENTAL_STEP_MINUTES": glue_cfg.get("INCREMENTAL_STEP_MINUTES", "10"),
        "INCOMING_KEYS": glue_cfg.get("INCOMING_KEYS", "[]"),
        "INCREMENTAL_NEW_CLIENTS": glue_cfg.get("INCREMENTAL_NEW_CLIENTS", "10"),
        "INCREMENTAL_SEED_CLIENTES": glue_cfg.get("INCREMENTAL_SEED_CLIENTES", "5000"),
    }
    print(json.dumps(run_pipeline(config), indent=2))


if __name__ == "__main__":
    main()
