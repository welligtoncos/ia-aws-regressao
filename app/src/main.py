"""
Pipeline principal: leitura S3 -> pré-processamento -> XGBoost -> métricas e saída Glue.
Executável localmente ou como AWS Glue Python Shell / Glue ETL driver.
"""

import argparse
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

try:
    from src.model import (
        calcular_metricas,
        extrair_feature_importance,
        gerar_predicoes_output,
        salvar_json_s3,
        treinar_modelo,
    )
    from src.preprocessor import TARGET, Preprocessor
except ImportError:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from app.src.model import (
        calcular_metricas,
        extrair_feature_importance,
        gerar_predicoes_output,
        salvar_json_s3,
        treinar_modelo,
    )
    from app.src.preprocessor import TARGET, Preprocessor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def _load_config_from_glue():
    try:
        from awsglue.utils import getResolvedOptions

        keys = [
            "INPUT_BUCKET", "INPUT_KEY", "OUTPUT_BUCKET",
            "OUTPUT_DATABASE", "OUTPUT_TABLE", "TARGET_COLUMN", "MODE",
        ]
        optional = ["MODEL_OUTPUT_PATH", "XGBOOST_PARAMS", "AWS_REGION"]
        present = [k for k in keys + optional if f"--{k}" in sys.argv]
        return getResolvedOptions(sys.argv, present)
    except ImportError:
        return {}


def _parse_xgboost_params(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        return json.loads(raw)
    return {}


def read_csv_s3(bucket: str, key: str, region: str) -> pd.DataFrame:
    client = boto3.client("s3", region_name=region)
    obj = client.get_object(Bucket=bucket, Key=key)
    return pd.read_csv(StringIO(obj["Body"].read().decode("utf-8")))


def write_parquet_s3_partitioned(df: pd.DataFrame, bucket: str, prefix: str, region: str) -> None:
    """Grava parquet particionado por ano/mes/segmento no S3."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    for (ano, mes, segmento), group in df.groupby(["ano", "mes", "segmento"]):
        table = pa.Table.from_pandas(group.drop(columns=["ano", "mes", "segmento"], errors="ignore"))
        buf = pa.BufferOutputStream()
        pq.write_table(table, buf)
        key = f"{prefix}/ano={ano}/mes={mes}/segmento={segmento}/data.parquet"
        boto3.client("s3", region_name=region).put_object(
            Bucket=bucket,
            Key=key,
            Body=buf.getvalue().to_pybytes(),
        )
    logger.info("Parquet particionado salvo em s3://%s/%s", bucket, prefix)


def run_pipeline(config: dict) -> dict:
    inicio = time.time()
    region = config.get("AWS_REGION", "us-east-1")
    bucket = config["INPUT_BUCKET"]
    key = config["INPUT_KEY"]
    output_bucket = config["OUTPUT_BUCKET"]
    model_path = config.get("MODEL_OUTPUT_PATH", "models/xgboost_saldo/")
    mode = config.get("MODE", "train")
    xgb_params = _parse_xgboost_params(config.get("XGBOOST_PARAMS", "{}"))

    logger.info("Lendo s3://%s/%s", bucket, key)
    df = read_csv_s3(bucket, key, region)
    logger.info("Dataset carregado: %s", df.shape)

    preprocessor = Preprocessor()
    x, y = preprocessor.fit_transform(df)
    x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.2, random_state=42)

    resultado = {"mode": mode, "rows": len(df)}

    if mode == "train":
        model = treinar_modelo(x_train, y_train, x_test, y_test, xgb_params)
        y_pred = model.predict(x_test)
        metricas = calcular_metricas(y_test.values, y_pred)
        resultado["metricas"] = metricas

        model_hash = hashlib.md5(json.dumps(metricas, sort_keys=True).encode()).hexdigest()[:8]
        modelo_versao = f"xgb-saldo-v1-{model_hash}"

        fi = extrair_feature_importance(model, list(x.columns))
        salvar_json_s3(metricas, output_bucket, f"{model_path}metricas.json", region)
        salvar_json_s3(fi, output_bucket, f"{model_path}feature_importance.json", region)

        df_test_idx = y_test.index
        df_out = gerar_predicoes_output(
            df.loc[df_test_idx].reset_index(drop=True),
            y_pred,
            y_test.values,
            modelo_versao,
        )
        table_prefix = config.get("OUTPUT_TABLE", "tb_saldo_previsto")
        write_parquet_s3_partitioned(
            df_out,
            output_bucket,
            f"processed/{table_prefix}",
            region,
        )
        resultado["modelo_versao"] = modelo_versao
        resultado["metricas_path"] = f"s3://{output_bucket}/{model_path}metricas.json"

    logger.info("Pipeline concluído em %.2fs", time.time() - inicio)
    return resultado


def main():
    glue_cfg = _load_config_from_glue()
    if glue_cfg:
        config = {
            "INPUT_BUCKET": glue_cfg.get("INPUT_BUCKET"),
            "INPUT_KEY": glue_cfg.get("INPUT_KEY"),
            "OUTPUT_BUCKET": glue_cfg.get("OUTPUT_BUCKET"),
            "OUTPUT_DATABASE": glue_cfg.get("OUTPUT_DATABASE", ""),
            "OUTPUT_TABLE": glue_cfg.get("OUTPUT_TABLE", "tb_saldo_previsto"),
            "TARGET_COLUMN": glue_cfg.get("TARGET_COLUMN", TARGET),
            "MODE": glue_cfg.get("MODE", "train"),
            "MODEL_OUTPUT_PATH": glue_cfg.get("MODEL_OUTPUT_PATH", "models/xgboost_saldo/"),
            "XGBOOST_PARAMS": glue_cfg.get("XGBOOST_PARAMS", "{}"),
            "AWS_REGION": glue_cfg.get("AWS_REGION", os.getenv("AWS_REGION", "us-east-1")),
        }
    else:
        parser = argparse.ArgumentParser()
        parser.add_argument("--input-bucket", default=os.getenv("INPUT_BUCKET", "sample-data-dev"))
        parser.add_argument("--input-key", default=os.getenv("INPUT_KEY", "raw/saldo_previsto/dados_treino.csv"))
        parser.add_argument("--output-bucket", default=os.getenv("OUTPUT_BUCKET", "sample-data-dev"))
        parser.add_argument("--output-table", default="tb_saldo_previsto_dev")
        parser.add_argument("--mode", default="train")
        args = parser.parse_args()
        config = {
            "INPUT_BUCKET": args.input_bucket,
            "INPUT_KEY": args.input_key,
            "OUTPUT_BUCKET": args.output_bucket,
            "OUTPUT_TABLE": args.output_table,
            "MODE": args.mode,
            "MODEL_OUTPUT_PATH": "models/xgboost_saldo/",
            "XGBOOST_PARAMS": os.getenv("XGBOOST_PARAMS", "{}"),
            "AWS_REGION": os.getenv("AWS_REGION", "us-east-1"),
        }

    result = run_pipeline(config)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
