#!/usr/bin/env python
"""CLI para gerar dataset sintético e enviar ao S3."""

import argparse
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)

from scripts.generate_dataset import gerar_dataset, upload_to_s3  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Gera dataset sintético de saldo bancário")
    parser.add_argument("--clientes", type=int, default=5000)
    parser.add_argument("--meses", type=int, default=10)
    parser.add_argument("--bucket", default=os.getenv("INPUT_BUCKET", "sample-data-dev"))
    parser.add_argument("--key", default=os.getenv("INPUT_KEY", "raw/saldo_previsto/dados_treino.csv"))
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-1"))
    parser.add_argument("--local-only", action="store_true", help="Salva CSV local sem S3")
    parser.add_argument("--output", default="data/dados_treino.csv")
    args = parser.parse_args()

    print("Gerando dataset...")
    df = gerar_dataset(n_clientes=args.clientes, n_meses=args.meses)
    print(f"Dataset gerado: {df.shape}")
    print(df.head())
    print(df.dtypes)

    if args.local_only:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        df.to_csv(args.output, index=False)
        print(f"Dataset salvo localmente: {args.output}")
    else:
        upload_to_s3(df, args.bucket, args.key, args.region)


if __name__ == "__main__":
    main()
