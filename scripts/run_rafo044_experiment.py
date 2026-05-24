#!/usr/bin/env python
"""
Experimento completo Rafo044 em um único comando:
  init → treino inicial → todos os lotes incoming → aguarda Glue → relatório local.

Compara predito vs gabarito (saldo do mês posterior) por período e evolução de WAPE/RMSE.

Uso (raiz do repo):
  python scripts/run_rafo044_experiment.py --run-all --upload

  # CSV completo no S3 + 1 treino (corrige merge parcial):
  python scripts/run_rafo044_experiment.py --reconcile --upload

  # Métricas: --export-reports e Athena (docs/ANALISE_METRICAS_ATHENA.md)

  # Do zero (só estado local; não apaga S3):
  python scripts/run_rafo044_experiment.py --run-all --upload --force-init

Requisitos: AWS CLI credenciais, boto3, pyarrow.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_automate_module():
    import importlib.util

    path = ROOT / "scripts" / "automate_rafo044_ingest.py"
    spec = importlib.util.spec_from_file_location("automate_rafo044_ingest", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_auto = _load_automate_module()
DEFAULT_BUCKET = _auto.DEFAULT_BUCKET
DEFAULT_INCOMING_PREFIX = _auto.DEFAULT_INCOMING_PREFIX
DEFAULT_REGION = _auto.DEFAULT_REGION
DEFAULT_TRAIN_KEY = _auto.DEFAULT_TRAIN_KEY
_ensure_raw_data = _auto._ensure_raw_data
_load_state = _auto._load_state
_month_list = _auto._month_list
_start_sfn = _auto._start_sfn
_upload_file = _auto._upload_file
cmd_init = _auto.cmd_init
cmd_status = _auto.cmd_status
cmd_tick = _auto.cmd_tick

from workloads.shared.rafo044_etl import build_monthly_panel  # noqa: E402

GLUE_JOB = os.getenv("GLUE_JOB_NAME", "saldo-previsto-glue-job-prod")
REPORT_DIR = ROOT / "data" / "reports"
METRICS_PREFIX = "processed/tb_metricas_treino/"
PREDS_PREFIX = "processed/tb_saldo_previsto_prod/"


def verify_processing(bucket: str, region: str, panel, state: dict) -> bool:
    """Checklist: dados ingeridos, lotes enviados, métricas e predições no S3. Retorna True se OK."""
    import boto3
    import pandas as pd

    s3 = boto3.client("s3", region_name=region)
    months = state.get("months", _month_list(panel))
    idx = state.get("next_index", 0)
    sent = state.get("sent", [])
    ok_all = True

    print("\n=== Verificação de processamento ===\n")
    print(
        f"[INFO] Painel local: {len(panel):,} linhas | "
        f"após Glue, CSV costuma ter ~{int(len(panel) * 0.88):,}–{len(panel):,} linhas "
        f"(último mês/cliente sem saldo_alvo é removido)"
    )

    holdout = state.get("holdout_from")
    start_idx = months.index(holdout) if holdout in months else 0
    expected_incoming = len(months) - start_idx
    ok_lotes = len(sent) >= expected_incoming and idx >= len(months)
    ok_all &= ok_lotes
    print(f"[{'OK' if ok_lotes else 'PENDENTE'}] Lotes incoming: {len(sent)}/{expected_incoming} enviados")
    if sent:
        for s in sent:
            print(f"      - {s.get('month')}: {s.get('file')}")
    print(f"      Estado next_index={idx}/{len(months)}")

    faltando = []
    try:
        obj = s3.get_object(Bucket=bucket, Key=DEFAULT_TRAIN_KEY)
        treino = pd.read_csv(io.BytesIO(obj["Body"].read()))
        p = pd.to_datetime(treino["data_referencia"]).dt.to_period("M").astype(str)
        meses_treino = sorted(p.unique())
        print(f"[INFO] dados_treino.csv: {len(treino):,} linhas | meses: {', '.join(meses_treino)}")
        faltando = sorted(set(months) - set(meses_treino))
        if faltando:
            ok_all = False
            print(f"[AVISO] Meses do painel ainda não no CSV de treino: {faltando}")
            print("      >>> Corrija: python scripts/run_rafo044_experiment.py --reconcile --upload")
        else:
            print("[OK] Todos os meses do painel estão no CSV de treino")
    except Exception as exc:
        ok_all = False
        print(f"[ERRO] dados_treino.csv: {exc}")

    inc = s3.list_objects_v2(Bucket=bucket, Prefix=DEFAULT_INCOMING_PREFIX).get("Contents", [])
    inc_files = [o["Key"] for o in (inc or []) if o["Key"].endswith(".csv")]
    print(f"[INFO] Arquivos em incoming/: {len(inc_files)}")

    mets = s3.list_objects_v2(Bucket=bucket, Prefix=METRICS_PREFIX).get("Contents", [])
    met_files = [o["Key"] for o in (mets or []) if o["Key"].endswith("metrics.parquet")]
    has_metrics = bool(met_files)
    print(f"[{'OK' if has_metrics else 'AVISO'}] Retreinos com métricas no S3: {len(met_files)} arquivo(s)")
    for k in met_files[-5:]:
        print(f"      - {k.split('run_id=')[-1]}")

    preds = s3.list_objects_v2(Bucket=bucket, Prefix=PREDS_PREFIX).get("Contents", [])
    pred_files = [o["Key"] for o in (preds or []) if o["Key"].endswith(".parquet")]
    has_preds = bool(pred_files)
    print(f"[{'OK' if has_preds else 'AVISO'}] Partições de predição: {len(pred_files)} arquivo(s) parquet")

    if not has_metrics or not has_preds:
        ok_all = False
        print("\n[Dica] Sem métricas/predições: rode treino com Glue SUCCEEDED.")
    if faltando:
        print(
            "\n[Dica] Merge incremental incompleto (SFN concorrente). "
            "Use --reconcile ou --upload-all-incoming-once no próximo --run-all."
        )
    print()
    return ok_all


def _parse_glue_time(value) -> datetime:
    if value is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _wait_glue_job_run(region: str, job_run_id: str, timeout_sec: int = 1200, poll_sec: int = 20) -> dict:
    import boto3

    client = boto3.client("glue", region_name=region)
    deadline = time.time() + timeout_sec
    last_state = None
    while time.time() < deadline:
        run = client.get_job_run(JobName=GLUE_JOB, RunId=job_run_id)["JobRun"]
        state = run["JobRunState"]
        if state != last_state:
            print(f"Glue {job_run_id}: {state}")
            last_state = state
        if state in ("SUCCEEDED", "FAILED", "STOPPED", "TIMEOUT"):
            if state != "SUCCEEDED":
                raise RuntimeError(f"Glue {state}: {run.get('ErrorMessage', '')}")
            return run
        time.sleep(poll_sec)
    raise TimeoutError(f"Glue {job_run_id} não terminou em {timeout_sec}s")


def _wait_glue_after(
    region: str,
    since: datetime,
    timeout_sec: int = 1200,
    poll_sec: int = 20,
) -> dict:
    """Aguarda o primeiro JobRun iniciado em ou após ``since`` (evita SUCCEEDED de run antigo)."""
    import boto3

    client = boto3.client("glue", region_name=region)
    since = since.astimezone(timezone.utc) if since.tzinfo else since.replace(tzinfo=timezone.utc)
    deadline = time.time() + timeout_sec
    seen: set[str] = set()

    while time.time() < deadline:
        runs = client.get_job_runs(JobName=GLUE_JOB, MaxResults=10).get("JobRuns", [])
        for run in reversed(runs):
            run_id = run["Id"]
            started = _parse_glue_time(run.get("StartedOn"))
            if started < since:
                continue
            state = run["JobRunState"]
            if run_id not in seen:
                print(f"Glue {run_id} (desde {since.isoformat()}): {state}")
                seen.add(run_id)
            if state in ("SUCCEEDED", "FAILED", "STOPPED", "TIMEOUT"):
                if state != "SUCCEEDED":
                    raise RuntimeError(f"Glue {state}: {run.get('ErrorMessage', '')}")
                return run
        time.sleep(poll_sec)
    raise TimeoutError(
        f"Nenhum Glue JobRun iniciado após {since.isoformat()} em {timeout_sec}s"
    )


def _start_glue_direct(
    region: str,
    run_id: str,
    incoming_keys: list | None = None,
) -> str:
    import boto3

    client = boto3.client("glue", region_name=region)
    args = {
        "--run_id": run_id,
        "--INGEST_DAILY": "false",
        "--INCOMING_KEYS": json.dumps(incoming_keys or []),
    }
    resp = client.start_job_run(JobName=GLUE_JOB, Arguments=args)
    job_run_id = resp["JobRunId"]
    print(f"Glue start_job_run: {job_run_id} (run_id={run_id})")
    return job_run_id


def _list_incoming_keys(bucket: str, prefix: str, region: str) -> list[str]:
    import boto3

    s3 = boto3.client("s3", region_name=region)
    resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    return sorted(
        o["Key"] for o in (resp.get("Contents") or []) if o["Key"].endswith(".csv")
    )


def _trigger_train_and_wait(ns: argparse.Namespace, incoming_keys: list | None = None) -> None:
    """Dispara treino (Glue direto ou SFN) e aguarda conclusão."""
    run_id = f"rafo044-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    use_direct = ns.use_glue_direct or incoming_keys is not None
    if use_direct:
        job_run_id = _start_glue_direct(ns.region, run_id, incoming_keys=incoming_keys)
        _wait_glue_job_run(ns.region, job_run_id, timeout_sec=ns.glue_timeout)
    else:
        since = datetime.now(timezone.utc)
        _start_sfn(ns.region)
        _wait_glue_after(ns.region, since=since, timeout_sec=ns.glue_timeout)
    if ns.post_glue_pause > 0:
        time.sleep(ns.post_glue_pause)


def _enrich_from_s3_key(df, key: str):
    import re

    m = re.search(r"ano=(\d+)/mes=(\d+)/segmento=([^/]+)/", key)
    if m:
        if "ano" not in df.columns:
            df = df.copy()
            df["ano"] = int(m.group(1))
        if "mes" not in df.columns:
            df["mes"] = int(m.group(2))
        if "segmento" not in df.columns:
            df["segmento"] = m.group(3)
    return df


def _s3_read_parquet_keys(bucket: str, prefix: str, region: str):
    import boto3
    import pandas as pd

    client = boto3.client("s3", region_name=region)
    paginator = client.get_paginator("list_objects_v2")
    frames = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith(".parquet"):
                continue
            body = client.get_object(Bucket=bucket, Key=key)["Body"].read()
            part = pd.read_parquet(io.BytesIO(body))
            part = _enrich_from_s3_key(part, key)
            frames.append(part)
    if not frames:
        return None
    out = pd.concat(frames, ignore_index=True)
    if "data_referencia" in out.columns:
        dr = pd.to_datetime(out["data_referencia"])
        if "ano" not in out.columns:
            out["ano"] = dr.dt.year
        if "mes" not in out.columns:
            out["mes"] = dr.dt.month
    return out


def _export_evolution_reports(bucket: str, region: str) -> None:
    import pandas as pd

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    metrics = _s3_read_parquet_keys(bucket, METRICS_PREFIX, region)
    if metrics is not None and not metrics.empty:
        cols = [c for c in [
            "dt_processamento", "run_id", "rmse", "wape", "mae", "r2",
            "linhas_adicionadas", "total_linhas", "modelo_versao", "is_champion",
            "data_referencia_lote",
        ] if c in metrics.columns]
        out = metrics[cols].sort_values("dt_processamento")
        path = REPORT_DIR / "evolucao_metricas.csv"
        out.to_csv(path, index=False)
        print(f"Relatório métricas: {path} ({len(out)} runs)")

    preds = _s3_read_parquet_keys(bucket, PREDS_PREFIX, region)
    if preds is not None and not preds.empty:
        pred_col = "saldo_predito" if "saldo_predito" in preds.columns else "saldo_previsto"
        real_col = "saldo_realizado" if "saldo_realizado" in preds.columns else "saldo_real"
        preds = preds.copy()
        preds["erro_absoluto"] = (preds[pred_col] - preds[real_col]).abs()
        rows = []
        for (ano, mes), g in preds.groupby(["ano", "mes"]):
            denom = g[real_col].abs().sum()
            wape = 100.0 * g["erro_absoluto"].sum() / denom if denom > 0 else 0.0
            rows.append({
                "ano": ano,
                "mes": mes,
                "registros": len(g),
                "media_predito": round(g[pred_col].mean(), 2),
                "media_gabarito": round(g[real_col].mean(), 2),
                "wape_pct": round(wape, 2),
            })
        by_month = pd.DataFrame(rows)
        path = REPORT_DIR / "gabarito_por_mes.csv"
        by_month.to_csv(path, index=False)
        print(f"Relatório gabarito por mês (predito vs mês posterior): {path}")

        path2 = REPORT_DIR / "gabarito_detalhe_amostra.csv"
        cols = [c for c in [
            "cliente_id", "segmento", "data_referencia", "ano", "mes",
            pred_col, real_col, "erro_absoluto", "modelo_versao", "run_id",
        ] if c in preds.columns]
        preds[cols].head(500).to_csv(path2, index=False)
        print(f"Amostra detalhe: {path2}")


def _build_args(ns: argparse.Namespace):
    """Namespace compatível com automate_rafo044_ingest."""
    class A:
        pass

    a = A()
    for k, v in vars(ns).items():
        setattr(a, k, v)
    a.upload = ns.upload
    a.trigger_sfn = False
    return a


def run_reconcile(ns: argparse.Namespace, panel) -> None:
    """Substitui dados_treino.csv pelo painel completo e dispara um único treino Glue."""
    if not ns.upload:
        print("--reconcile requer --upload")
        sys.exit(1)

    print("\n=== Reconcile: painel completo → S3 + 1 treino ===\n")
    out = Path(ns.train_output)
    out.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(out, index=False)
    print(f"Painel local: {out} ({len(panel):,} linhas, {len(_month_list(panel))} meses)")
    _upload_file(out, ns.bucket, ns.train_key, ns.region)
    print(f"Upload: s3://{ns.bucket}/{ns.train_key}")

    if ns.wait_glue:
        print("Treino único (INGEST_DAILY=false, sem incoming)...")
        _trigger_train_and_wait(ns, incoming_keys=[])

    print("\n=== Relatórios ===")
    try:
        _export_evolution_reports(ns.bucket, ns.region)
    except Exception as exc:
        print(f"Aviso ao gerar relatórios: {exc}")
    verify_processing(ns.bucket, ns.region, panel, _load_state())
    print("\nAthena (opcional): payloads/athena_queries.sql seção Gabarito")


def run_all(ns: argparse.Namespace, panel) -> None:
    args = _build_args(ns)
    state = _load_state()

    cmd_status(panel, state)

    need_init = ns.force_init or not state.get("holdout_from") or state.get("next_index", 0) == 0
    if need_init and not state.get("sent"):
        print("\n=== 1/3 Carga inicial ===")
        cmd_init(args, panel)
        if ns.upload and ns.wait_glue:
            print("Treino inicial (histórico)...")
            _trigger_train_and_wait(ns)
    elif state.get("next_index", 0) == state.get("holdout_from") and not state.get("sent"):
        print("\n=== Treino inicial (estado sem lotes enviados) ===")
        if ns.upload and ns.wait_glue:
            _trigger_train_and_wait(ns)

    print("\n=== 2/3 Lotes incoming (todos os meses restantes) ===")
    batch_num = 0
    if ns.upload_all_incoming_once:
        while True:
            if not cmd_tick(args, panel):
                break
            batch_num += 1
        print(f"Upload de {batch_num} lote(s) concluído (sem SFN por lote).")
        if ns.upload and ns.wait_glue and batch_num > 0:
            keys = _list_incoming_keys(ns.bucket, ns.incoming_prefix, ns.region)
            print(f"Merge único com {len(keys)} arquivo(s) incoming...")
            _trigger_train_and_wait(ns, incoming_keys=keys)
        elif ns.upload and ns.interval_minutes > 0:
            print(f"Aguardando {ns.interval_minutes} min...")
            time.sleep(ns.interval_minutes * 60)
    else:
        while True:
            has_more = cmd_tick(args, panel)
            if not has_more:
                break
            batch_num += 1
            if ns.upload and ns.wait_glue:
                print(f"Disparando treino após lote {batch_num}...")
                _trigger_train_and_wait(ns)
            elif ns.upload and ns.interval_minutes > 0:
                print(f"Aguardando {ns.interval_minutes} min (sem --wait-glue)...")
                time.sleep(ns.interval_minutes * 60)

    print("\n=== 3/3 Relatórios ===")
    if ns.upload:
        try:
            _export_evolution_reports(ns.bucket, ns.region)
        except Exception as exc:
            print(f"Aviso ao gerar relatórios: {exc}")
    verify_processing(ns.bucket, ns.region, panel, _load_state())
    cmd_status(panel, _load_state())
    print("\nAthena (opcional): payloads/athena_queries.sql seção Gabarito")


def main() -> None:
    parser = argparse.ArgumentParser(description="Experimento Rafo044 completo")
    parser.add_argument("--run-all", action="store_true", help="Init + todos os lotes + relatórios")
    parser.add_argument(
        "--reconcile",
        action="store_true",
        help="Upload painel completo como dados_treino.csv + 1 treino Glue (corrige merge parcial)",
    )
    parser.add_argument("--verify-only", action="store_true", help="Só checklist S3/estado (sem upload)")
    parser.add_argument("--export-reports", action="store_true", help="Só gera CSV em data/reports/")
    parser.add_argument("--force-init", action="store_true", help="Refaz --init (reset estado local)")
    parser.add_argument(
        "--upload-all-incoming-once",
        action="store_true",
        help="Envia todos os lotes sem SFN; depois 1 treino com todos os INCOMING_KEYS",
    )
    parser.add_argument(
        "--use-glue-direct",
        action="store_true",
        help="start-job-run em vez de Step Functions (reconcile usa por padrão)",
    )
    parser.add_argument(
        "--post-glue-pause",
        type=int,
        default=30,
        help="Segundos após Glue SUCCEEDED antes do próximo lote (default: 30)",
    )
    parser.add_argument("--upload", action="store_true")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data" / "rafo044" / "raw")
    parser.add_argument("--max-customers", type=int, default=2000)
    parser.add_argument("--holdout-start-index", type=int, default=-3)
    parser.add_argument("--train-output", default="data/dados_treino.csv")
    parser.add_argument("--incoming-dir", default="data/incoming")
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--train-key", default=DEFAULT_TRAIN_KEY)
    parser.add_argument("--incoming-prefix", default=DEFAULT_INCOMING_PREFIX)
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--interval-minutes", type=float, default=0.0)
    parser.add_argument(
        "--wait-glue",
        action="store_true",
        default=True,
        help="Aguarda Glue SUCCEEDED após cada treino (default: ligado)",
    )
    parser.add_argument("--no-wait-glue", action="store_false", dest="wait_glue")
    parser.add_argument("--glue-timeout", type=int, default=1200)
    ns = parser.parse_args()

    if not (ns.run_all or ns.verify_only or ns.export_reports or ns.reconcile):
        parser.error("Use --run-all, --reconcile, --verify-only ou --export-reports")

    if ns.force_init:
        state_path = ROOT / "data" / "rafo044" / ".ingest_state.json"
        if state_path.exists():
            state_path.unlink()
            print("Estado local resetado.")

    _ensure_raw_data(ns.data_dir, ns.max_customers)
    panel = build_monthly_panel(ns.data_dir, max_customers=ns.max_customers)
    months = _month_list(panel)
    if ns.holdout_start_index < 0:
        ns.holdout_start_index = max(1, len(months) + ns.holdout_start_index)

    print(f"Painel: {len(panel)} linhas | meses {months[0]}..{months[-1]}")
    print("Alvo do modelo: saldo_m1 do MÊS POSTERIOR (gabarito = saldo_realizado no teste).\n")

    state = _load_state()
    if ns.verify_only:
        verify_processing(ns.bucket, ns.region, panel, state)
        return
    if ns.export_reports:
        _export_evolution_reports(ns.bucket, ns.region)
        return
    if ns.reconcile:
        run_reconcile(ns, panel)
        return

    run_all(ns, panel)


if __name__ == "__main__":
    main()
