"""Nomes canônicos de colunas — evita ambiguidade saldo_previsto (alvo vs predição)."""

# Treino (CSV / features): saldo do próximo período (y)
TARGET_ALVO = "saldo_alvo"
TARGET_LEGACY = "saldo_previsto"  # CSV antigo; remapeado para saldo_alvo no preprocessamento

# Predições publicadas (tb_saldo_previsto_prod)
COL_PREDITO = "saldo_predito"
COL_REALIZADO = "saldo_realizado"
COL_PREDITO_LEGACY = "saldo_previsto"
COL_REALIZADO_LEGACY = "saldo_real"
