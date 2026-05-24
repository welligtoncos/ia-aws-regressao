-- Athena: Settings -> Query result location = s3://saldo-previsto-data-prod/athena-results/
-- Database: saldo_previsto_db_prod
--
-- PREREQUISITO metricas: payloads/athena_migrate_tb_metricas_treino.sql
-- PREREQUISITO predicoes: payloads/athena_migrate_tb_saldo_previsto_prod.sql (opcional)
--
-- NOMES CANONICOS (docs/DATA_MODEL.md):
--   saldo_predito    = COALESCE(saldo_predito, saldo_previsto)   -- saida do modelo
--   saldo_realizado  = COALESCE(saldo_realizado, saldo_real)     -- valor observado
-- Treino CSV usa saldo_alvo (nao consultado nesta tabela).

-- =============================================================================
-- Predicoes (tb_saldo_previsto_prod)
-- =============================================================================

-- Visão geral por partição
SELECT ano, mes, segmento,
       COUNT(*) AS registros,
       ROUND(AVG(erro_percentual), 2) AS mape_medio_diag,
       ROUND(100.0 * SUM(erro_absoluto) / NULLIF(SUM(ABS(COALESCE(saldo_realizado, saldo_real))), 0), 2) AS wape_pct,
       ROUND(AVG(COALESCE(saldo_predito, saldo_previsto)), 2) AS saldo_predito_medio
FROM saldo_previsto_db_prod.tb_saldo_previsto_prod
GROUP BY ano, mes, segmento
ORDER BY ano, mes, segmento;

-- Insight principal: erro por segmento (MAPE diagnostico + WAPE estavel)
SELECT segmento,
       COUNT(*) AS registros,
       ROUND(AVG(erro_percentual), 2) AS mape_medio_diag,
       ROUND(100.0 * SUM(erro_absoluto) / NULLIF(SUM(ABS(COALESCE(saldo_realizado, saldo_real))), 0), 2) AS wape_pct,
       ROUND(AVG(erro_absoluto), 2) AS mae_medio,
       ROUND(AVG(COALESCE(saldo_realizado, saldo_real)), 2) AS saldo_realizado_medio
FROM saldo_previsto_db_prod.tb_saldo_previsto_prod
GROUP BY segmento
ORDER BY wape_pct DESC;

-- Comparar MAPE vs WAPE (MAPE explode com saldo_real baixo)
SELECT segmento,
       ROUND(AVG(erro_percentual), 2) AS mape_medio,
       ROUND(100.0 * SUM(erro_absoluto) / NULLIF(SUM(ABS(COALESCE(saldo_realizado, saldo_real))), 0), 2) AS wape_pct,
       ROUND(AVG(ABS(COALESCE(saldo_realizado, saldo_real))), 2) AS saldo_realizado_medio_abs
FROM saldo_previsto_db_prod.tb_saldo_previsto_prod
GROUP BY segmento
ORDER BY mape_medio DESC;

-- Sazonalidade: erro por mês
SELECT ano, mes, segmento,
       COUNT(*) AS n,
       ROUND(AVG(erro_percentual), 2) AS mape_diag,
       ROUND(100.0 * SUM(erro_absoluto) / NULLIF(SUM(ABS(COALESCE(saldo_realizado, saldo_real))), 0), 2) AS wape_pct,
       ROUND(STDDEV(erro_percentual), 2) AS volatilidade_mape
FROM saldo_previsto_db_prod.tb_saldo_previsto_prod
GROUP BY ano, mes, segmento
ORDER BY ano, mes, segmento;

-- Evolução entre retreinos (modelo_versao)
SELECT modelo_versao,
       MIN(dt_processamento) AS treinado_em,
       COUNT(*) AS registros,
       ROUND(AVG(erro_percentual), 2) AS mape_diag,
       ROUND(100.0 * SUM(erro_absoluto) / NULLIF(SUM(ABS(COALESCE(saldo_realizado, saldo_real))), 0), 2) AS wape_pct,
       ROUND(AVG(erro_absoluto), 2) AS mae
FROM saldo_previsto_db_prod.tb_saldo_previsto_prod
GROUP BY modelo_versao
ORDER BY treinado_em;

-- Detalhe amostral
SELECT cliente_id,
       COALESCE(saldo_predito, saldo_previsto) AS saldo_predito,
       COALESCE(saldo_realizado, saldo_real) AS saldo_realizado,
       erro_percentual, modelo_versao, run_id
FROM saldo_previsto_db_prod.tb_saldo_previsto_prod
WHERE segmento = 'VAREJO'
LIMIT 20;

-- =============================================================================
-- Metricas de treino (tb_metricas_treino) — RMSE, WAPE, R2 por run
-- =============================================================================

-- Evolução por retreino (ingestao a cada ~15 min em prod)
SELECT run_date, run_id, total_linhas, linhas_adicionadas,
       data_referencia_lote,
       ROUND(rmse, 2) AS rmse,
       ROUND(mae, 2) AS mae,
       ROUND(r2, 4) AS r2,
       ROUND(wape, 4) AS wape,
       ROUND(smape, 4) AS smape,
       ROUND(mape, 4) AS mape_diag,
       modelo_versao,
       dt_processamento
FROM saldo_previsto_db_prod.tb_metricas_treino
ORDER BY dt_processamento;

-- Ultimo run vs champion (metricas globais do holdout de teste)
SELECT dt_processamento,
       run_id,
       modelo_versao,
       ROUND(rmse, 2) AS rmse,
       ROUND(wape, 2) AS wape,
       is_champion,
       champion_modelo_versao,
       ROUND(champion_rmse, 2) AS champion_rmse,
       ROUND(champion_wape, 2) AS champion_wape
FROM saldo_previsto_db_prod.tb_metricas_treino
ORDER BY dt_processamento DESC
LIMIT 5;

-- Runs que viraram champion (promocao: RMSE >= 2% melhor que anterior)
SELECT run_id, modelo_versao, champion_modelo_versao,
       ROUND(rmse, 2) AS rmse,
       ROUND(wape, 2) AS wape,
       dt_processamento
FROM saldo_previsto_db_prod.tb_metricas_treino
WHERE is_champion = true
ORDER BY dt_processamento DESC;

-- Champion atual
SELECT champion_modelo_versao,
       ROUND(champion_rmse, 2) AS champion_rmse,
       ROUND(champion_wape, 2) AS champion_wape,
       dt_processamento
FROM saldo_previsto_db_prod.tb_metricas_treino
WHERE is_champion = true
ORDER BY dt_processamento DESC
LIMIT 1;

-- =============================================================================
-- FALLBACK: WAPE por segmento SEM metricas_segmento (so tb_saldo_previsto_prod)
-- Use se a migracao ainda nao foi aplicada ou particoes antigas estao vazias.
-- =============================================================================
SELECT segmento,
       COUNT(*) AS registros,
       ROUND(100.0 * SUM(erro_absoluto) / NULLIF(SUM(ABS(COALESCE(saldo_realizado, saldo_real))), 0), 2) AS wape_pct,
       ROUND(AVG(erro_percentual), 2) AS mape_diag
FROM saldo_previsto_db_prod.tb_saldo_previsto_prod
WHERE dt_processamento >= (
  SELECT max(dt_processamento) FROM saldo_previsto_db_prod.tb_saldo_previsto_prod
)
GROUP BY segmento
ORDER BY wape_pct DESC;

-- =============================================================================
-- metricas_segmento (JSON gravado no holdout de teste por run)
-- Requer ALTER TABLE / terraform — ver athena_migrate_tb_metricas_treino.sql
-- Formato: {"VAREJO":{"rmse":...,"wape":...,"mape":...}, "PRIME":{...}, ...}
-- =============================================================================

-- Extrair WAPE por segmento no ultimo retreino (segmentos fixos do simulador)
WITH ultimo AS (
  SELECT *
  FROM saldo_previsto_db_prod.tb_metricas_treino
  ORDER BY dt_processamento DESC
  LIMIT 1
)
SELECT run_id,
       modelo_versao,
       ROUND(rmse, 2) AS rmse_global,
       ROUND(wape, 2) AS wape_global,
       ROUND(CAST(json_extract_scalar(metricas_segmento, '$.VAREJO.wape') AS double), 2) AS wape_varejo,
       ROUND(CAST(json_extract_scalar(metricas_segmento, '$.PRIME.wape') AS double), 2) AS wape_prime,
       ROUND(CAST(json_extract_scalar(metricas_segmento, '$.PRIVATE.wape') AS double), 2) AS wape_private,
       ROUND(CAST(json_extract_scalar(metricas_segmento, '$.VAREJO.rmse') AS double), 2) AS rmse_varejo,
       ROUND(CAST(json_extract_scalar(metricas_segmento, '$.PRIME.rmse') AS double), 2) AS rmse_prime,
       ROUND(CAST(json_extract_scalar(metricas_segmento, '$.PRIVATE.rmse') AS double), 2) AS rmse_private
FROM ultimo
WHERE metricas_segmento IS NOT NULL
  AND metricas_segmento <> '';

-- Serie temporal: WAPE global e por segmento (ultimos 30 retreinos)
SELECT dt_processamento,
       run_id,
       ROUND(wape, 2) AS wape_global,
       ROUND(CAST(json_extract_scalar(metricas_segmento, '$.VAREJO.wape') AS double), 2) AS wape_varejo,
       ROUND(CAST(json_extract_scalar(metricas_segmento, '$.PRIME.wape') AS double), 2) AS wape_prime,
       ROUND(CAST(json_extract_scalar(metricas_segmento, '$.PRIVATE.wape') AS double), 2) AS wape_private,
       is_champion
FROM saldo_previsto_db_prod.tb_metricas_treino
WHERE metricas_segmento IS NOT NULL
  AND metricas_segmento <> ''
ORDER BY dt_processamento DESC
LIMIT 30;

-- Desempacotar todos os segmentos do JSON (Presto/Athena)
-- Requer metricas_segmento valido; segmentos desconhecidos aparecem como novas chaves no map
SELECT m.dt_processamento,
       m.run_id,
       seg.segmento,
       ROUND(CAST(json_extract_scalar(seg.metricas, '$.rmse') AS double), 2) AS rmse,
       ROUND(CAST(json_extract_scalar(seg.metricas, '$.wape') AS double), 2) AS wape,
       ROUND(CAST(json_extract_scalar(seg.metricas, '$.mape') AS double), 2) AS mape_diag,
       ROUND(CAST(json_extract_scalar(seg.metricas, '$.r2') AS double), 4) AS r2
FROM saldo_previsto_db_prod.tb_metricas_treino m
CROSS JOIN UNNEST(
  CAST(json_parse(m.metricas_segmento) AS map(varchar, json))
) AS seg(segmento, metricas)
WHERE m.metricas_segmento IS NOT NULL
  AND m.metricas_segmento <> ''
ORDER BY m.dt_processamento DESC, seg.segmento
LIMIT 200;

-- Segmento com pior WAPE no ultimo retreino
WITH ultimo AS (
  SELECT dt_processamento, run_id, metricas_segmento
  FROM saldo_previsto_db_prod.tb_metricas_treino
  WHERE metricas_segmento IS NOT NULL AND metricas_segmento <> ''
  ORDER BY dt_processamento DESC
  LIMIT 1
),
por_segmento AS (
  SELECT u.dt_processamento,
         u.run_id,
         seg.segmento,
         CAST(json_extract_scalar(seg.metricas, '$.wape') AS double) AS wape
  FROM ultimo u
  CROSS JOIN UNNEST(
    CAST(json_parse(u.metricas_segmento) AS map(varchar, json))
  ) AS seg(segmento, metricas)
)
SELECT *
FROM por_segmento
ORDER BY wape DESC
LIMIT 1;

-- =============================================================================
-- Monitoramento operacional (retreino ~15 min; SkipNoNewData nao grava linha)
-- =============================================================================

-- Ultimo retreino por janela de 15 minutos (ultimas 6 horas)
WITH por_slot AS (
  SELECT date_trunc('hour', from_iso8601_timestamp(dt_processamento))
         + (minute(from_iso8601_timestamp(dt_processamento)) / 15) * interval '15' minute AS slot_15m,
         dt_processamento,
         modelo_versao,
         rmse,
         wape,
         mape,
         r2,
         total_linhas,
         linhas_adicionadas,
         is_champion,
         row_number() OVER (
           PARTITION BY date_trunc('hour', from_iso8601_timestamp(dt_processamento))
                        + (minute(from_iso8601_timestamp(dt_processamento)) / 15) * interval '15' minute
           ORDER BY dt_processamento DESC
         ) AS rn
  FROM saldo_previsto_db_prod.tb_metricas_treino
  WHERE from_iso8601_timestamp(dt_processamento) >= current_timestamp - interval '6' hour
)
SELECT slot_15m,
       ROUND(rmse, 2) AS rmse,
       ROUND(wape, 2) AS wape,
       ROUND(mape, 4) AS mape_diag,
       ROUND(r2, 4) AS r2,
       total_linhas,
       linhas_adicionadas,
       modelo_versao,
       is_champion
FROM por_slot
WHERE rn = 1
ORDER BY slot_15m DESC;

-- Ultimos 60 retreinos (resumo)
SELECT date_trunc('minute', from_iso8601_timestamp(dt_processamento)) AS processado_em,
       dt_processamento,
       ROUND(rmse, 2) AS rmse,
       ROUND(wape, 2) AS wape,
       ROUND(mape, 4) AS mape_diag,
       linhas_adicionadas,
       modelo_versao,
       is_champion
FROM saldo_previsto_db_prod.tb_metricas_treino
ORDER BY dt_processamento DESC
LIMIT 60;

-- Erro das predicoes por slot de processamento (ultimas 6 horas)
SELECT date_trunc('hour', from_iso8601_timestamp(dt_processamento))
       + (minute(from_iso8601_timestamp(dt_processamento)) / 15) * interval '15' minute AS slot_15m,
       COUNT(*) AS registros,
       ROUND(AVG(erro_percentual), 2) AS mape_diag,
       ROUND(100.0 * SUM(erro_absoluto) / NULLIF(SUM(ABS(COALESCE(saldo_realizado, saldo_real))), 0), 2) AS wape_pct,
       ROUND(AVG(erro_absoluto), 2) AS mae,
       max(modelo_versao) AS modelo_versao
FROM saldo_previsto_db_prod.tb_saldo_previsto_prod
WHERE from_iso8601_timestamp(dt_processamento) >= current_timestamp - interval '6' hour
GROUP BY 1
ORDER BY slot_15m DESC;
