#!/usr/bin/env python
"""CLI: ETL Rafo044 Synthetic Bank → CSV treino / incoming / S3."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)

from workloads.shared.rafo044_etl import (  # noqa: E402
    build_monthly_panel,
    export_month_batch,
    split_initial_and_incoming,
)


def _upload_s3(path: str, bucket: str, key: str, region: str) -> None:
    import boto3

    with open(path, "rb") as fh:
        boto3.client("s3", region_name=region).put_object(Bucket=bucket, Key=key, Body=fh.read())
    print(f"Upload: s3://{bucket}/{key}")


def _clone_repo(dest: str) -> None:
    dest_path = os.path.abspath(dest)
    if os.path.isdir(os.path.join(dest_path, ".git")):
        print(f"Repo já existe: {dest_path}")
        return
    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    subprocess.run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "https://github.com/Rafo044/Synthetic_Bank_Dataset.git",
            dest_path,
        ],
        check=True,
    )
    print(f"Clone OK: {dest_path}")
    print(
        "Gere transactions.parquet (requer polars, faker):\n"
        f"  cd {dest_path} && pip install polars faker numpy && "
        "python scripts/synthetic_data_create.py\n"
        "Copie synthetic_output/* para data/ ou use --data-dir synthetic_output"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="ETL Rafo044 → schema saldo previsto")
    parser.add_argument(
        "--data-dir",
        default=os.getenv("RAFO044_DATA_DIR", "data/rafo044/raw"),
        help="Pasta com customers.csv, accounts.csv, transactions.parquet",
    )
    parser.add_argument("--output", default="data/dados_treino.csv", help="CSV completo (histórico)")
    parser.add_argument(
        "--export-month",
        metavar="YYYY-MM",
        help="Gera só um mês (incoming/), ex.: 2016-03",
    )
    parser.add_argument(
        "--incoming-output",
        default="data/incoming/lote_{month}.csv",
        help="Template de saída do lote (--export-month)",
    )
    parser.add_argument(
        "--split-at",
        metavar="YYYY-MM",
        help="Gera histórico até o mês anterior + incoming no mês (dois arquivos)",
    )
    parser.add_argument("--max-customers", type=int, default=None, help="Subamostra para POC")
    parser.add_argument("--clone", metavar="DIR", help="git clone do repo Rafo044")
    parser.add_argument("--upload", action="store_true", help="Envia ao S3 após gerar")
    parser.add_argument("--bucket", default=os.getenv("INPUT_BUCKET", "saldo-previsto-data-prod"))
    parser.add_argument(
        "--key",
        default=os.getenv("INPUT_KEY", "raw/saldo_previsto/dados_treino.csv"),
    )
    parser.add_argument(
        "--incoming-key",
        default="incoming/lote_{month}.csv",
        help="Chave S3 do lote incoming",
    )
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-1"))
    args = parser.parse_args()

    if args.clone:
        _clone_repo(args.clone)
        return

    from pathlib import Path

    data_dir = Path(args.data_dir)
    print(f"Lendo Rafo044 em {data_dir.resolve()}...")
    panel = build_monthly_panel(data_dir, max_customers=args.max_customers)
    print(f"Painel: {panel.shape[0]} linhas, {panel['cliente_id'].nunique()} clientes")

    if args.split_at:
        initial, incoming = split_initial_and_incoming(panel, args.split_at)
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        initial.to_csv(args.output, index=False)
        month = args.split_at
        inc_path = args.incoming_output.format(month=month)
        os.makedirs(os.path.dirname(inc_path) or ".", exist_ok=True)
        incoming.to_csv(inc_path, index=False)
        print(f"Histórico: {args.output} ({len(initial)} linhas)")
        print(f"Incoming: {inc_path} ({len(incoming)} linhas)")
        if args.upload:
            _upload_s3(args.output, args.bucket, args.key, args.region)
            _upload_s3(
                inc_path,
                args.bucket,
                args.incoming_key.format(month=month),
                args.region,
            )
        return

    if args.export_month:
        batch = export_month_batch(panel, args.export_month)
        out = args.incoming_output.format(month=args.export_month)
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        batch.to_csv(out, index=False)
        print(f"Lote {args.export_month}: {out} ({len(batch)} linhas)")
        if args.upload:
            _upload_s3(
                out,
                args.bucket,
                args.incoming_key.format(month=args.export_month),
                args.region,
            )
        return

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    panel.to_csv(args.output, index=False)
    print(f"Salvo: {args.output}")
    if args.upload:
        _upload_s3(args.output, args.bucket, args.key, args.region)


if __name__ == "__main__":
    main()
