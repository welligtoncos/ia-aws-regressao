#!/usr/bin/env python
"""
Apaga dados ML anteriores (S3 + watermark DynamoDB) para reiniciar com dataset novo.

Uso (raiz do repo):
  python scripts/reset_ml_data.py --yes
  python scripts/reset_ml_data.py --yes --purge-dynamodb
  python scripts/reset_ml_data.py --yes --seed-rafo044 --upload
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BUCKET = os.getenv("INPUT_BUCKET", "saldo-previsto-data-prod")
REGION = os.getenv("AWS_REGION", "us-east-1")
DYNAMODB_TABLE = os.getenv("DYNAMODB_TABLE", "saldo-previsto-results-prod")
WATERMARK_ID = "__ingest_watermark__"

# Prefixos S3 apagados (scripts/libs/builds preservados)
S3_PREFIXES = [
    "raw/saldo_previsto/",
    "incoming/",
    "processed/tb_saldo_previsto_prod/",
    "processed/tb_metricas_treino/",
    "models/xgboost_saldo/",
    "landing/",
]

LOCAL_PATHS = [
    ROOT / "data" / "dados_treino.csv",
    ROOT / "data" / "incoming",
    ROOT / "data" / "rafo044" / ".ingest_state.json",
]


def _delete_s3_prefix(bucket: str, prefix: str, region: str) -> int:
    import boto3
    from botocore.exceptions import ClientError

    client = boto3.client("s3", region_name=region)
    paginator = client.get_paginator("list_objects_v2")
    deleted = 0
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        contents = page.get("Contents") or []
        if not contents:
            continue
        keys = [{"Key": o["Key"]} for o in contents]
        for i in range(0, len(keys), 1000):
            batch = keys[i : i + 1000]
            client.delete_objects(Bucket=bucket, Delete={"Objects": batch, "Quiet": True})
            deleted += len(batch)
    return deleted


def _clear_watermark(table: str, region: str) -> None:
    import boto3

    boto3.resource("dynamodb", region_name=region).Table(table).delete_item(
        Key={"run_id": WATERMARK_ID}
    )
    print(f"DynamoDB watermark removido: {WATERMARK_ID}")


def _purge_dynamodb(table: str, region: str) -> int:
    import boto3

    tbl = boto3.resource("dynamodb", region_name=region).Table(table)
    n = 0
    scan_kwargs = {}
    while True:
        resp = tbl.scan(**scan_kwargs)
        for item in resp.get("Items", []):
            tbl.delete_item(Key={"run_id": item["run_id"]})
            n += 1
        if "LastEvaluatedKey" not in resp:
            break
        scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return n


def _clear_local() -> None:
    for path in LOCAL_PATHS:
        if path.is_file():
            path.unlink()
            print(f"Removido local: {path}")
        elif path.is_dir():
            for f in path.glob("*"):
                if f.is_file():
                    f.unlink()
            print(f"Limpado local: {path}/*")


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset dados ML (S3 + DynamoDB + local)")
    parser.add_argument("--yes", action="store_true", help="Confirma apagamento sem prompt")
    parser.add_argument("--bucket", default=BUCKET)
    parser.add_argument("--region", default=REGION)
    parser.add_argument("--dynamodb-table", default=DYNAMODB_TABLE)
    parser.add_argument("--purge-dynamodb", action="store_true", help="Apaga TODOS os runs no DynamoDB")
    parser.add_argument("--skip-s3", action="store_true")
    parser.add_argument("--skip-local", action="store_true")
    parser.add_argument(
        "--seed-rafo044",
        action="store_true",
        help="Gera amostra Rafo044 após reset",
    )
    parser.add_argument("--upload", action="store_true", help="Com --seed-rafo044: init + upload S3")
    parser.add_argument("--customers", type=int, default=2000)
    args = parser.parse_args()

    if not args.yes:
        print(f"Isso apaga dados em s3://{args.bucket}/ (prefixos ML) e watermark DynamoDB.")
        if args.purge_dynamodb:
            print(f"Também apaga todos os itens de {args.dynamodb_table}.")
        confirm = input("Digite APAGAR para continuar: ")
        if confirm.strip().upper() != "APAGAR":
            raise SystemExit("Cancelado.")

    if not args.skip_s3:
        total = 0
        for prefix in S3_PREFIXES:
            n = _delete_s3_prefix(args.bucket, prefix, args.region)
            total += n
            print(f"s3://{args.bucket}/{prefix} -> {n} objetos removidos")
        print(f"S3 total: {total} objetos")

    try:
        _clear_watermark(args.dynamodb_table, args.region)
    except Exception as exc:
        print(f"Aviso watermark: {exc}")

    if args.purge_dynamodb:
        n = _purge_dynamodb(args.dynamodb_table, args.region)
        print(f"DynamoDB: {n} itens removidos de {args.dynamodb_table}")

    if not args.skip_local:
        _clear_local()

    print("\nReset concluído. Próximo passo sugerido:")
    print("  1) ml_ingest_daily_simulated = false no terraform.tfvars")
    print("  2) python scripts/automate_rafo044_ingest.py --init --upload")

    if args.seed_rafo044:
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "generate_rafo044_sample.py"),
                "--customers",
                str(args.customers),
            ],
            check=True,
            cwd=str(ROOT),
        )
        cmd = [sys.executable, str(ROOT / "scripts" / "automate_rafo044_ingest.py"), "--init"]
        if args.upload:
            cmd.append("--upload")
        subprocess.run(cmd, check=True, cwd=str(ROOT))


if __name__ == "__main__":
    main()
