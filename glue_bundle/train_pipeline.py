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
from model import calcular_metricas, extrair_feature_importance, gerar_predicoes_output, salvar_json_s3, treinar_modelo
from preprocessor import TARGET, Preprocessor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def _load_config_from_glue():
    try:
        from awsglue.utils import getResolvedOptions
        keys = ["INPUT_BUCKET", "INPUT_KEY", "OUTPUT_BUCKET", "OUTPUT_DATABASE", "OUTPUT_TABLE", "TARGET_COLUMN", "MODE"]
        optional = ["MODEL_OUTPUT_PATH", "XGBOOST_PARAMS", "AWS_REGION"]
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


def run_pipeline(config):
    inicio = time.time()
    region = config.get("AWS_REGION", "us-east-1")
    df = read_csv_s3(config["INPUT_BUCKET"], config["INPUT_KEY"], region)
    logger.info("Dataset: %s", df.shape)

    prep = Preprocessor()
    x, y = prep.fit_transform(df)
    x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.2, random_state=42)
    xgb_params = _parse_xgboost_params(config.get("XGBOOST_PARAMS", "{}"))
    model = treinar_modelo(x_train, y_train, x_test, y_test, xgb_params)
    y_pred = model.predict(x_test)
    metricas = calcular_metricas(y_test.values, y_pred)

    model_path = config.get("MODEL_OUTPUT_PATH", "models/xgboost_saldo/")
    out_bucket = config["OUTPUT_BUCKET"]
    model_hash = hashlib.md5(json.dumps(metricas, sort_keys=True).encode()).hexdigest()[:8]
    modelo_versao = f"xgb-saldo-v1-{model_hash}"

    salvar_json_s3(metricas, out_bucket, f"{model_path}metricas.json", region)
    salvar_json_s3(extrair_feature_importance(model, list(x.columns)), out_bucket, f"{model_path}feature_importance.json", region)

    df_out = gerar_predicoes_output(df.loc[y_test.index].reset_index(drop=True), y_pred, y_test.values, modelo_versao)
    table = config.get("OUTPUT_TABLE", "tb_saldo_previsto")
    database = config.get("OUTPUT_DATABASE", "")
    prefix = f"processed/{table}"
    write_parquet_s3_partitioned(df_out, out_bucket, prefix, region)
    register_partitions(df_out, out_bucket, database, table, prefix, region)

    logger.info("Pipeline OK em %.2fs", time.time() - inicio)
    return {"metricas": metricas, "modelo_versao": modelo_versao}


def main():
    glue_cfg = _load_config_from_glue()
    config = {
        "INPUT_BUCKET": glue_cfg["INPUT_BUCKET"],
        "INPUT_KEY": glue_cfg["INPUT_KEY"],
        "OUTPUT_BUCKET": glue_cfg["OUTPUT_BUCKET"],
        "OUTPUT_TABLE": glue_cfg.get("OUTPUT_TABLE", "tb_saldo_previsto"),
        "OUTPUT_DATABASE": glue_cfg.get("OUTPUT_DATABASE", ""),
        "MODEL_OUTPUT_PATH": glue_cfg.get("MODEL_OUTPUT_PATH", "models/xgboost_saldo/"),
        "XGBOOST_PARAMS": glue_cfg.get("XGBOOST_PARAMS", "{}"),
        "AWS_REGION": glue_cfg.get("AWS_REGION", os.getenv("AWS_REGION", "us-east-1")),
    }
    print(json.dumps(run_pipeline(config), indent=2))


if __name__ == "__main__":
    main()
