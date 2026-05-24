"""Geração incremental de dados simulados (append daily/micro no CSV de treino)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import StringIO
from typing import Any, Dict, List, Optional

import boto3
import numpy as np
import pandas as pd
from botocore.exceptions import ClientError
from dateutil.relativedelta import relativedelta

from target import prepare_training_dataset

UFS = ["SP", "RJ", "MG", "RS", "BA", "PR", "SC", "GO", "PE", "CE"]
GENEROS = ["M", "F"]
PROFILE_COLS = [
    "cliente_id", "idade", "renda_mensal", "segmento", "tempo_relacionamento",
    "uf", "genero", "possui_investimento", "possui_credito", "possui_seguro", "score_credito",
]


def _gerar_segmento(renda: float) -> str:
    if renda >= 20000:
        return "PRIVATE"
    if renda >= 8000:
        return "PRIME"
    return "VAREJO"


def _gerar_perfil_cliente(cliente_id: str, rng: np.random.Generator) -> dict:
    idade = int(rng.integers(18, 81))
    renda_mensal = float(rng.uniform(1000, 50000))
    return {
        "cliente_id": cliente_id,
        "idade": idade,
        "renda_mensal": round(renda_mensal, 2),
        "segmento": _gerar_segmento(renda_mensal),
        "tempo_relacionamento": int(rng.integers(1, 241)),
        "uf": str(rng.choice(UFS)),
        "genero": str(rng.choice(GENEROS)),
        "possui_investimento": int(rng.random() > 0.55),
        "possui_credito": int(rng.random() > 0.40),
        "possui_seguro": int(rng.random() > 0.60),
        "score_credito": int(rng.integers(300, 1001)),
    }


def _gerar_saldos_historicos(renda: float, rng: np.random.Generator, saldo_anterior: Optional[float] = None) -> list:
    base = saldo_anterior if saldo_anterior is not None else renda * rng.uniform(0.5, 3.0)
    saldos = []
    for _ in range(6):
        drift = rng.normal(0, renda * 0.05)
        base = max(0, base + drift)
        saldos.append(round(base, 2))
    return list(reversed(saldos))


def _linha_para_data(perfil: dict, data_ref: datetime, rng: np.random.Generator, saldo_seed: Optional[float] = None) -> dict:
    saldos = _gerar_saldos_historicos(perfil["renda_mensal"], rng, saldo_seed)
    valor_creditos = float(rng.uniform(0, perfil["renda_mensal"] * 1.2))
    valor_debitos = float(rng.uniform(0, perfil["renda_mensal"] * 0.9))
    qtd_transacoes = int(rng.integers(0, 201))
    mes = data_ref.month
    return {
        **perfil,
        "data_referencia": data_ref.strftime("%Y-%m-%d"),
        "saldo_m1": saldos[0],
        "saldo_m2": saldos[1],
        "saldo_m3": saldos[2],
        "saldo_m4": saldos[3],
        "saldo_m5": saldos[4],
        "saldo_m6": saldos[5],
        "qtd_transacoes_mes": qtd_transacoes,
        "valor_debitos_mes": round(valor_debitos, 2),
        "valor_creditos_mes": round(valor_creditos, 2),
        "qtd_produtos_ativos": int(rng.integers(1, 9)),
        "mes": mes,
        "trimestre": (mes - 1) // 3 + 1,
        "ano": data_ref.year,
        "is_fim_de_ano": int(mes in (11, 12)),
        "is_inicio_de_ano": int(mes == 1),
    }


def bootstrap_dataset(n_clientes: int, n_meses: int, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    data_fim = datetime(2025, 12, 1)
    datas = [data_fim - relativedelta(months=i) for i in range(n_meses - 1, -1, -1)]
    linhas = []
    for i in range(1, n_clientes + 1):
        perfil = _gerar_perfil_cliente(f"CLI_{str(i).zfill(5)}", rng)
        for data_ref in datas:
            linhas.append(_linha_para_data(perfil, data_ref, rng))
    return pd.DataFrame(linhas)


def gerar_lote_diario(df_existente: pd.DataFrame, data_ref: datetime, new_clients: int = 0, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed + int(data_ref.strftime("%Y%m%d%H%M")))
    linhas = []
    if df_existente.empty:
        raise ValueError("Dataset vazio; use bootstrap antes do lote.")

    ultimo = (
        df_existente.sort_values(["cliente_id", "data_referencia"])
        .groupby("cliente_id", as_index=False)
        .tail(1)
    )
    for _, row in ultimo.iterrows():
        perfil = {col: row[col] for col in PROFILE_COLS if col in row}
        saldo_seed = float(row.get("saldo_m1", 0))
        linhas.append(_linha_para_data(perfil, data_ref, rng, saldo_seed=saldo_seed))

    if new_clients > 0:
        max_id = df_existente["cliente_id"].str.extract(r"CLI_(\d+)")[0].astype(int).max()
        start = int(max_id) + 1 if pd.notna(max_id) else 1
        for i in range(start, start + new_clients):
            perfil = _gerar_perfil_cliente(f"CLI_{str(i).zfill(5)}", rng)
            linhas.append(_linha_para_data(perfil, data_ref, rng))

    return pd.DataFrame(linhas)


def read_csv_s3(bucket: str, key: str, region: str) -> pd.DataFrame:
    client = boto3.client("s3", region_name=region)
    try:
        obj = client.get_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "NoSuchKey":
            return pd.DataFrame()
        raise
    return pd.read_csv(StringIO(obj["Body"].read().decode("utf-8")))


def write_csv_s3(df: pd.DataFrame, bucket: str, key: str, region: str) -> None:
    buf = StringIO()
    df.to_csv(buf, index=False)
    boto3.client("s3", region_name=region).put_object(Bucket=bucket, Key=key, Body=buf.getvalue())


def merge_incoming_csvs(bucket: str, keys: List[str], region: str) -> pd.DataFrame:
    frames = [read_csv_s3(bucket, k, region) for k in keys if k]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def ingest_simulated(
    bucket: str,
    key: str,
    region: str = "us-east-1",
    run_id: str = "manual",
    seed_clientes: int = 5000,
    seed_meses: int = 6,
    new_clients: int = 10,
    max_rows: int = 600_000,
    mode: str = "daily",
    step_minutes: int = 10,
    incoming_keys: Optional[List[str]] = None,
    skip_simulated: bool = False,
) -> Dict[str, Any]:
    """Append lote simulado (daily/micro) e/ou CSVs de incoming/ ao dataset de treino."""
    df = read_csv_s3(bucket, key, region)
    rows_before = len(df)
    incoming_keys = incoming_keys or []
    rows_incoming = 0

    if incoming_keys:
        df_in = merge_incoming_csvs(bucket, incoming_keys, region)
        if not df_in.empty:
            df = pd.concat([df, df_in], ignore_index=True) if not df.empty else df_in
            rows_incoming = len(df_in)

    rows_added = 0
    data_ref = datetime.now(timezone.utc)

    if not skip_simulated:
        if df.empty:
            df = bootstrap_dataset(seed_clientes, seed_meses)
            rows_added = len(df)
            data_ref = pd.to_datetime(df["data_referencia"]).max().to_pydatetime()
        elif mode == "micro":
            ultima_data = pd.to_datetime(df["data_referencia"]).max().to_pydatetime()
            data_ref = ultima_data + timedelta(minutes=step_minutes)
            micro_new_clients = max(1, new_clients // 5)
            lote = gerar_lote_diario(df, data_ref, new_clients=micro_new_clients)
            df = pd.concat([df, lote], ignore_index=True)
            rows_added = len(lote)
        else:
            ultima_data = pd.to_datetime(df["data_referencia"]).max().to_pydatetime()
            data_ref = ultima_data + timedelta(days=1)
            lote = gerar_lote_diario(df, data_ref, new_clients=new_clients)
            df = pd.concat([df, lote], ignore_index=True)
            rows_added = len(lote)

    if len(df) > max_rows:
        df = df.sort_values("data_referencia").tail(max_rows).reset_index(drop=True)

    df = prepare_training_dataset(df)
    write_csv_s3(df, bucket, key, region)

    ts = data_ref.strftime("%Y-%m-%dT%H%M")
    landing_key = f"landing/dt={data_ref.strftime('%Y-%m-%d')}/run_id={run_id}/batch_{ts}.csv"
    tail_n = max(rows_added, rows_incoming, 1)
    write_csv_s3(df.sort_values("data_referencia").tail(tail_n), bucket, landing_key, region)

    return {
        "data_referencia": data_ref.isoformat(),
        "rows_added": rows_added,
        "rows_incoming": rows_incoming,
        "total_rows": len(df),
        "rows_before": rows_before,
        "landing_key": landing_key,
        "run_id": run_id,
        "ingest_mode": mode,
        "incoming_keys": incoming_keys,
    }


def ingest_daily_simulated(
    bucket: str,
    key: str,
    region: str = "us-east-1",
    run_id: str = "manual",
    seed_clientes: int = 5000,
    seed_meses: int = 6,
    new_clients: int = 10,
    max_rows: int = 600_000,
) -> Dict[str, Any]:
    return ingest_simulated(
        bucket, key, region, run_id, seed_clientes, seed_meses, new_clients, max_rows, mode="daily"
    )
