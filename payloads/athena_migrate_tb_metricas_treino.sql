-- =============================================================================
-- Migracao: colunas novas em tb_metricas_treino (WAPE, metricas_segmento, etc.)
-- Execute UMA VEZ no Athena (database saldo_previsto_db_prod) ANTES das queries
-- que usam metricas_segmento, wape ou champion_wape.
--
-- Erro tipico sem migracao:
--   COLUMN_NOT_FOUND: Column 'metricas_segmento' cannot be resolved
--
-- Alternativa: terraform apply no modulo glue_metrics_catalog (infra/).
-- =============================================================================

-- 1) Ver schema atual
DESCRIBE saldo_previsto_db_prod.tb_metricas_treino;

-- 2) Adicionar colunas (idempotente: se ja existir, Athena retorna erro — ignore ou comente a linha)
ALTER TABLE saldo_previsto_db_prod.tb_metricas_treino
ADD COLUMNS (
  wape double,
  smape double,
  metricas_segmento string,
  champion_wape double,
  metricas_baseline string
);

-- 3) Confirmar
DESCRIBE saldo_previsto_db_prod.tb_metricas_treino;

-- 4) Particoes antigas sem o campo retornam NULL; novos retreinos (Glue atualizado) preenchem JSON.
-- Teste rapido:
SELECT dt_processamento, run_id, wape, metricas_segmento
FROM saldo_previsto_db_prod.tb_metricas_treino
ORDER BY dt_processamento DESC
LIMIT 5;
