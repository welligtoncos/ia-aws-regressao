"""Geração de dataset sintético de saldo bancário."""

import pandas as pd
import numpy as np
from datetime import datetime
from dateutil.relativedelta import relativedelta

UFS = ["SP", "RJ", "MG", "RS", "BA", "PR", "SC", "GO", "PE", "CE"]
GENEROS = ["M", "F"]


def gerar_cliente_id(n: int) -> list:
    return [f"CLI_{str(i).zfill(5)}" for i in range(1, n + 1)]


def gerar_segmento(renda: float) -> str:
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
        "segmento": gerar_segmento(renda_mensal),
        "tempo_relacionamento": int(rng.integers(1, 241)),
        "uf": rng.choice(UFS),
        "genero": rng.choice(GENEROS),
        "possui_investimento": int(rng.random() > 0.55),
        "possui_credito": int(rng.random() > 0.40),
        "possui_seguro": int(rng.random() > 0.60),
        "score_credito": int(rng.integers(300, 1001)),
    }


def _gerar_saldos_historicos(renda: float, rng: np.random.Generator) -> list:
    base = renda * rng.uniform(0.5, 3.0)
    saldos = []
    for i in range(6):
        drift = rng.normal(0, renda * 0.05)
        base = max(0, base + drift)
        saldos.append(round(base, 2))
    return list(reversed(saldos))


def gerar_dataset(n_clientes: int = 5000, n_meses: int = 10, seed: int = 42) -> pd.DataFrame:
    """
    Gera dataset sintético com n_clientes x n_meses linhas.

    Args:
        n_clientes: Quantidade de clientes.
        n_meses: Meses de histórico por cliente.
        seed: Semente para reprodutibilidade.

    Returns:
        DataFrame completo com features e target saldo_previsto.
    """
    rng = np.random.default_rng(seed)
    clientes = gerar_cliente_id(n_clientes)
    perfis = {cid: _gerar_perfil_cliente(cid, rng) for cid in clientes}

    data_fim = datetime(2025, 12, 1)
    datas = [data_fim - relativedelta(months=i) for i in range(n_meses - 1, -1, -1)]

    linhas = []
    for cliente_id in clientes:
        perfil = perfis[cliente_id]
        for data_ref in datas:
            saldos = _gerar_saldos_historicos(perfil["renda_mensal"], rng)
            valor_creditos = float(rng.uniform(0, perfil["renda_mensal"] * 1.2))
            valor_debitos = float(rng.uniform(0, perfil["renda_mensal"] * 0.9))
            qtd_transacoes = int(rng.integers(0, 201))

            ruido = rng.normal(0, perfil["renda_mensal"] * 0.05)
            saldo_previsto = (
                saldos[0]
                + (valor_creditos - valor_debitos) * 0.7
                + perfil["renda_mensal"] * 0.1
                + ruido
            )
            saldo_previsto = round(max(0, saldo_previsto), 2)

            mes = data_ref.month
            linhas.append({
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
                "saldo_previsto": saldo_previsto,
            })

    return pd.DataFrame(linhas)


def upload_to_s3(df: pd.DataFrame, bucket: str, key: str, region: str = "us-east-1") -> None:
    """Converte DataFrame para CSV e envia ao S3."""
    import boto3
    from io import StringIO

    csv_buffer = StringIO()
    df.to_csv(csv_buffer, index=False)

    client = boto3.client("s3", region_name=region)
    client.put_object(Bucket=bucket, Key=key, Body=csv_buffer.getvalue())
    print(f"Upload concluído: s3://{bucket}/{key} ({len(df)} linhas)")
