"""Pré-processamento — bundle flat para AWS Glue Python Shell."""

import logging
import time
from typing import List, Tuple

import pandas as pd
from sklearn.preprocessing import LabelEncoder, StandardScaler

from columns import TARGET_ALVO
from target import META_AUX_COL, prepare_training_dataset

logger = logging.getLogger(__name__)

COLUNAS_CATEGORICAS = ["segmento", "uf", "genero"]
COLUNAS_BOOLEANAS = [
    "possui_investimento", "possui_credito", "possui_seguro",
    "is_fim_de_ano", "is_inicio_de_ano",
]
COLUNAS_HISTORICO_SALDO = [
    "saldo_m1", "saldo_m2", "saldo_m3", "saldo_m4", "saldo_m5", "saldo_m6",
]
COLUNAS_REMOVER = ["cliente_id", "data_referencia"]
COLUNAS_NORMALIZAR = [
    "renda_mensal", "saldo_m1", "saldo_m2", "saldo_m3", "saldo_m4", "saldo_m5", "saldo_m6",
    "media_saldo_historico", "tendencia_saldo", "volatilidade_saldo", "saldo_por_renda",
]
TARGET = TARGET_ALVO


def criar_features_derivadas(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    saldos = df[COLUNAS_HISTORICO_SALDO]
    df["media_saldo_historico"] = saldos.mean(axis=1)
    df["tendencia_saldo"] = df["saldo_m1"] - df["saldo_m6"]
    df["volatilidade_saldo"] = saldos.std(axis=1)
    df["variacao_pct_saldo"] = (df["saldo_m1"] - df["saldo_m2"]) / (df["saldo_m2"].abs() + 1)
    df["saldo_por_renda"] = df["saldo_m1"] / (df["renda_mensal"] + 1)
    df["credito_debito_ratio"] = df["valor_creditos_mes"] / (df["valor_debitos_mes"] + 1)
    return df


def tratar_nulos_saldo(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in COLUNAS_HISTORICO_SALDO:
        if col in df.columns:
            df[col] = df[col].fillna(df[col].median())
    return df


def remover_outliers_saldo(df: pd.DataFrame, coluna: str = "saldo_m1", percentil: float = 0.99) -> pd.DataFrame:
    limite = df[coluna].quantile(percentil)
    antes = len(df)
    df = df[df[coluna] <= limite].copy()
    logger.info("Outliers removidos: %d linhas", antes - len(df))
    return df


class Preprocessor:
    def __init__(self):
        self.label_encoders: dict = {}
        self.scaler = StandardScaler()
        self.feature_columns: List[str] = []
        self.meta_df = None

    def fit_transform(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
        logger.info("Iniciando pré-processamento")
        if META_AUX_COL not in df.columns:
            df = prepare_training_dataset(df)
        meta_cols = ["cliente_id", "data_referencia", "segmento"]
        meta_cols.extend(c for c in COLUNAS_HISTORICO_SALDO if c in df.columns)
        if META_AUX_COL in df.columns:
            meta_cols.append(META_AUX_COL)
        self.meta_df = df[meta_cols].copy()

        df = criar_features_derivadas(df)
        df = tratar_nulos_saldo(df)
        df = remover_outliers_saldo(df)
        y = df[TARGET].copy()
        drop_extra = [META_AUX_COL] if META_AUX_COL in df.columns else []
        work = df.drop(columns=COLUNAS_REMOVER + [TARGET] + drop_extra, errors="ignore")
        for col in COLUNAS_CATEGORICAS:
            if col in work.columns:
                le = LabelEncoder()
                work[col] = le.fit_transform(work[col].astype(str))
                self.label_encoders[col] = le
        for col in COLUNAS_BOOLEANAS:
            if col in work.columns:
                work[col] = work[col].fillna(0).astype(int)
        cols_norm = [c for c in COLUNAS_NORMALIZAR if c in work.columns]
        if cols_norm:
            work[cols_norm] = self.scaler.fit_transform(work[cols_norm])
        self.feature_columns = list(work.columns)
        return work, y
