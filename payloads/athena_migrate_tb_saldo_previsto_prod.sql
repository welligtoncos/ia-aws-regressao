-- =============================================================================
-- Migracao: colunas canonicas em tb_saldo_previsto_prod
-- saldo_previsto -> saldo_predito (predicao do modelo)
-- saldo_real     -> saldo_realizado (valor observado no teste)
--
-- Particoes Parquet antigas mantem nomes legados; use COALESCE nas queries
-- ou regrave predicoes com um novo retreino Glue.
-- =============================================================================

DESCRIBE saldo_previsto_db_prod.tb_saldo_previsto_prod;

-- Opcional: adicionar colunas novas ao catalogo (particoes antigas ficam NULL)
ALTER TABLE saldo_previsto_db_prod.tb_saldo_previsto_prod
ADD COLUMNS (
  saldo_predito double,
  saldo_realizado double
);

DESCRIBE saldo_previsto_db_prod.tb_saldo_previsto_prod;

-- Exemplo de leitura unificada (legado + novo):
-- SELECT COALESCE(saldo_predito, saldo_previsto) AS saldo_predito,
--        COALESCE(saldo_realizado, saldo_real) AS saldo_realizado
-- FROM saldo_previsto_db_prod.tb_saldo_previsto_prod
-- LIMIT 10;
