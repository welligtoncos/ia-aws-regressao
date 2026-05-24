-- =============================================================================
-- Migracao tb_saldo_previsto_prod — colunas canonicas + legado
--
-- Erro: COLUMN_NOT_FOUND: Column 'saldo_real' cannot be resolved
-- Causa: catálogo só tinha saldo_predito/saldo_realizado; COALESCE precisa das 4 no schema.
--
-- Execute no Athena (database saldo_previsto_db_prod), uma vez.
-- =============================================================================

DESCRIBE saldo_previsto_db_prod.tb_saldo_previsto_prod;

-- Colunas canônicas (runs novos após rename-cols-v1)
ALTER TABLE saldo_previsto_db_prod.tb_saldo_previsto_prod
ADD COLUMNS (
  saldo_predito double,
  saldo_realizado double
);

-- Colunas legado (partições Parquet antigas)
ALTER TABLE saldo_previsto_db_prod.tb_saldo_previsto_prod
ADD COLUMNS (
  saldo_previsto double,
  saldo_real double
);

DESCRIBE saldo_previsto_db_prod.tb_saldo_previsto_prod;

-- Leitura unificada (use em todas as queries):
--   COALESCE(saldo_predito, saldo_previsto)   AS saldo_predito
--   COALESCE(saldo_realizado, saldo_real)     AS saldo_realizado

SELECT COALESCE(saldo_predito, saldo_previsto) AS saldo_predito,
       COALESCE(saldo_realizado, saldo_real) AS saldo_realizado,
       segmento, dt_processamento
FROM saldo_previsto_db_prod.tb_saldo_previsto_prod
ORDER BY dt_processamento DESC
LIMIT 5;
