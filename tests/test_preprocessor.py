"""Testes do pré-processador de saldo bancário."""

from app.src.preprocessor import (
    TARGET,
    Preprocessor,
    criar_features_derivadas,
    tratar_nulos_saldo,
)
from scripts.generate_dataset import gerar_dataset


def _sample_df(n=100):
    return gerar_dataset(n_clientes=n, n_meses=2)


def test_criar_features_derivadas():
    df = _sample_df(50)
    out = criar_features_derivadas(df)
    assert "media_saldo_historico" in out.columns
    assert "credito_debito_ratio" in out.columns


def test_tratar_nulos_saldo():
    df = _sample_df(20)
    df.loc[0, "saldo_m1"] = None
    out = tratar_nulos_saldo(df)
    assert out["saldo_m1"].isna().sum() == 0


def test_preprocessor_fit_transform():
    df = _sample_df(80)
    prep = Preprocessor()
    x, y = prep.fit_transform(df)
    assert len(x) == len(y)
    assert TARGET not in x.columns
    assert len(prep.feature_columns) > 0
