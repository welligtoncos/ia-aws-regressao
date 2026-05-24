#!/usr/bin/env python
"""
Automatiza ingestão Rafo044: histórico em S3 + lotes mensais em incoming/.

O pipeline prod (EventBridge + Step Functions) detecta cada arquivo novo em
incoming/, faz merge, retreina e publica predições. O "gabarito" é o
saldo_realizado no holdout de teste (Athena: tb_saldo_previsto_prod).

Uso típico (na raiz do repo):

  # 1) Gerar dados locais (se ainda não existir)
  python scripts/generate_rafo044_sample.py --customers 2000

  # 2) Carga inicial + estado
  python scripts/automate_rafo044_ingest.py --init --upload

  # 3) Enviar próximo mês (repetir ou usar --loop)
  python scripts/automate_rafo044_ingest.py --tick --upload

  # 4) A cada 3 minutos, envia o próximo mês
  python scripts/automate_rafo044_ingest.py --loop --interval-minutes 3 --upload

Prod: defina ml_ingest_daily_simulated = false no terraform.tfvars.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workloads.shared.rafo044_etl import build_monthly_panel, export_month_batch  # noqa: E402

STATE_FILE = ROOT / "data" / "rafo044" / ".ingest_state.json"
DEFAULT_DATA_DIR = ROOT / "data" / "rafo044" / "raw"
DEFAULT_BUCKET = os.getenv("INPUT_BUCKET", "saldo-previsto-data-prod")
DEFAULT_TRAIN_KEY = os.getenv("INPUT_KEY", "raw/saldo_previsto/dados_treino.csv")
DEFAULT_INCOMING_PREFIX = os.getenv("INCOMING_PREFIX", "incoming/")
DEFAULT_REGION = os.getenv("AWS_REGION", "us-east-1")
SFN_ARN = os.getenv(
    "SFN_ARN",
    "arn:aws:states:us-east-1:303238378103:stateMachine:saldo-previsto-sfn-prod",
)


def _load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"next_index": 0, "months": [], "sent": []}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _month_list(panel) -> list[str]:
    periods = (
        panel["data_referencia"]
        .astype(str)
        .pipe(lambda s: __import__("pandas").to_datetime(s).dt.to_period("M"))
    )
    return sorted({str(p) for p in periods.unique()})


def _ensure_raw_data(data_dir: Path, customers: int) -> None:
    if (data_dir / "transactions.parquet").exists():
        return
    print("transactions.parquet ausente; gerando amostra...")
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "generate_rafo044_sample.py"),
            "--output-dir",
            str(data_dir),
            "--customers",
            str(customers),
        ],
        check=True,
        cwd=str(ROOT),
    )


def _upload_file(local_path: Path, bucket: str, key: str, region: str) -> None:
    import boto3

    boto3.client("s3", region_name=region).upload_file(str(local_path), bucket, key)
    print(f"s3://{bucket}/{key}")


def _start_sfn(region: str) -> None:
    import boto3

    client = boto3.client("stepfunctions", region_name=region)
    name = f"rafo044-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    resp = client.start_execution(
        stateMachineArn=SFN_ARN,
        name=name[:80],
        input=json.dumps({"source_prefix": "raw/"}),
    )
    print(f"Step Functions iniciado: {resp['executionArn']}")


def cmd_init(args: argparse.Namespace, panel) -> None:
    months = _month_list(panel)
    if len(months) < 2:
        raise SystemExit("Painel precisa de pelo menos 2 meses para init + incoming.")

    cutoff = months[args.holdout_start_index]
    periods = __import__("pandas").to_datetime(panel["data_referencia"]).dt.to_period("M")
    initial = panel[periods < __import__("pandas").Period(cutoff, freq="M")].copy()

    out_train = Path(args.train_output)
    out_train.parent.mkdir(parents=True, exist_ok=True)
    initial.to_csv(out_train, index=False)
    print(f"Histórico local: {out_train} ({len(initial)} linhas, até antes de {cutoff})")

    if args.upload:
        _upload_file(out_train, args.bucket, args.train_key, args.region)

    state = {
        "next_index": args.holdout_start_index,
        "months": months,
        "sent": [],
        "holdout_from": cutoff,
    }
    _save_state(state)
    print(f"Estado: próximo lote = {months[args.holdout_start_index]} ({len(months)} meses no painel)")


def cmd_status(panel, state: Optional[dict] = None) -> None:
    """Resumo de registros e lotes restantes."""
    state = state or _load_state()
    months = state.get("months") or _month_list(panel)
    idx = state.get("next_index", 0)
    p = __import__("pandas").to_datetime(panel["data_referencia"]).dt.to_period("M")

    print("\n=== Resumo Rafo044 ===")
    print(f"Painel completo (com lags m1-m6): {len(panel):,} linhas")
    print(f"Clientes únicos: {panel['cliente_id'].nunique():,}")
    print(f"Meses no painel: {len(months)} ({months[0]} .. {months[-1]})")
    for m in months:
        print(f"  {m}: {int((p.astype(str) == m).sum()):,} linhas")

    holdout = state.get("holdout_from", "?")
    init_rows = int((p < __import__("pandas").Period(holdout, freq="M")).sum()) if holdout != "?" else 0
    print(f"\nCarga inicial (--init, antes de {holdout}): ~{init_rows:,} linhas")
    remaining = months[idx:] if idx < len(months) else []
    rem_rows = sum(int((p.astype(str) == m).sum()) for m in remaining)
    print(f"Lotes incoming restantes: {len(remaining)} de {max(0, len(months) - idx)}")
    if remaining:
        for m in remaining:
            print(f"  pendente {m}: {int((p.astype(str) == m).sum()):,} linhas")
        print(f"Total linhas ainda por enviar (incoming): ~{rem_rows:,}")
    else:
        print("Nenhum lote pendente — automação concluída.")
    print(f"\nEstado: next_index={idx}/{len(months)}")
    if state.get("sent"):
        print(f"Já enviados: {len(state['sent'])} lote(s)")


def cmd_tick(args: argparse.Namespace, panel) -> bool:
    state = _load_state()
    months = state.get("months") or _month_list(panel)
    idx = state.get("next_index", 0)

    if idx >= len(months):
        print("Todos os meses do painel já foram enviados.")
        return False

    ym = months[idx]
    print(f"[{idx + 1}/{len(months)}] Próximo lote: {ym}")
    batch = export_month_batch(panel, ym)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    local_name = f"lote_{ym}_{ts}.csv"
    local_path = Path(args.incoming_dir) / local_name
    local_path.parent.mkdir(parents=True, exist_ok=True)
    batch.to_csv(local_path, index=False)
    print(f"Lote {ym}: {local_path} ({len(batch)} linhas)")

    if args.upload:
        key = f"{args.incoming_prefix.rstrip('/')}/{local_name}"
        _upload_file(local_path, args.bucket, key, args.region)
        if args.trigger_sfn:
            _start_sfn(args.region)

    state["months"] = months
    state["next_index"] = idx + 1
    state.setdefault("sent", []).append({"month": ym, "file": local_name, "at": ts})
    _save_state(state)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingestão automática Rafo044 → S3 incoming/")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--max-customers", type=int, default=2000)
    parser.add_argument("--init", action="store_true", help="Sobe histórico inicial (sem últimos meses de teste)")
    parser.add_argument("--tick", action="store_true", help="Envia um mês (próximo no estado)")
    parser.add_argument("--loop", action="store_true", help="Repete --tick até acabar os meses")
    parser.add_argument("--status", action="store_true", help="Mostra contagem de registros e lotes pendentes")
    parser.add_argument(
        "--interval-minutes",
        type=float,
        default=5.0,
        help="Pausa entre lotes no --loop (tempo para Glue treinar; default 5 min)",
    )
    parser.add_argument(
        "--holdout-start-index",
        type=int,
        default=-3,
        help="Índice do primeiro mês só em incoming (default: -3 = 3 últimos meses fora do init)",
    )
    parser.add_argument("--train-output", default="data/dados_treino.csv")
    parser.add_argument("--incoming-dir", default="data/incoming")
    parser.add_argument("--upload", action="store_true")
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--train-key", default=DEFAULT_TRAIN_KEY)
    parser.add_argument("--incoming-prefix", default=DEFAULT_INCOMING_PREFIX)
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument(
        "--trigger-sfn",
        action="store_true",
        help="Dispara Step Functions após upload (senão aguarda EventBridge)",
    )
    args = parser.parse_args()

    if not (args.init or args.tick or args.loop or args.status):
        parser.error("Use --init, --tick, --loop ou --status")

    _ensure_raw_data(args.data_dir, args.max_customers)
    print(f"Montando painel de {args.data_dir}...")
    panel = build_monthly_panel(args.data_dir, max_customers=args.max_customers)
    months = _month_list(panel)
    print(f"Painel: {len(panel)} linhas, meses {months[0]} .. {months[-1]}")

    if args.holdout_start_index < 0:
        args.holdout_start_index = max(1, len(months) + args.holdout_start_index)

    if args.status:
        cmd_status(panel)
        if not (args.init or args.tick or args.loop):
            return

    if args.init:
        cmd_init(args, panel)

    if args.tick or args.loop:
        while True:
            has_more = cmd_tick(args, panel)
            if not args.loop or not has_more:
                if args.loop and not has_more:
                    print("\nAutomação concluída: todos os meses foram enviados.")
                    cmd_status(panel, _load_state())
                break
            print(
                f"Aguardando {args.interval_minutes} min (retreino no Glue; "
                "consulte gabarito no Athena entre lotes)..."
            )
            time.sleep(args.interval_minutes * 60)

    if args.upload:
        print("\n--- Gabarito no Athena (predito vs realizado) ---")
        print(
            "SELECT cliente_id, segmento,\n"
            "       ROUND(COALESCE(saldo_predito, saldo_previsto), 2) AS predito,\n"
            "       ROUND(COALESCE(saldo_realizado, saldo_real), 2) AS gabarito,\n"
            "       ROUND(erro_absoluto, 2) AS erro_abs,\n"
            "       modelo_versao, run_id\n"
            "FROM saldo_previsto_db_prod.tb_saldo_previsto_prod\n"
            "ORDER BY dt_processamento DESC\n"
            "LIMIT 50;"
        )


if __name__ == "__main__":
    main()
