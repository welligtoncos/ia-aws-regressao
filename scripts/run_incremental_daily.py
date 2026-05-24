#!/usr/bin/env python
"""CLI: append lote diário simulado no CSV de treino (local ou S3)."""

import argparse
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)

from workloads.shared.incremental_data import ingest_daily_simulated  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Ingestão incremental diária simulada")
    parser.add_argument("--bucket", default=os.getenv("INPUT_BUCKET", "saldo-previsto-data-prod"))
    parser.add_argument("--key", default=os.getenv("INPUT_KEY", "raw/saldo_previsto/dados_treino.csv"))
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-1"))
    parser.add_argument("--run-id", default="manual-ingest")
    parser.add_argument("--new-clients", type=int, default=10)
    parser.add_argument("--seed-clientes", type=int, default=5000)
    args = parser.parse_args()

    result = ingest_daily_simulated(
        bucket=args.bucket,
        key=args.key,
        region=args.region,
        run_id=args.run_id,
        seed_clientes=args.seed_clientes,
        new_clients=args.new_clients,
    )
    print(result)


if __name__ == "__main__":
    main()
