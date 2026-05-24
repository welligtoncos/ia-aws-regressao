-- Athena: Settings -> Query result location = s3://saldo-previsto-data-prod/athena-results/
-- Database: saldo_previsto_db_prod
--
-- Guia passo a passo (Rafo044, reconcile, interpretacao): docs/ANALISE_METRICAS_ATHENA.md
-- Benchmark (1 linha, modelo champion): secao "Benchmark do modelo" abaixo; docs/ANALISE_METRICAS_ATHENA.md#query-de-benchmark
-- Relatorios locais: python scripts/run_rafo044_experiment.py --export-reports
--
-- PREREQUISITO metricas: payloads/athena_migrate_tb_metricas_treino.sql
-- PREREQUISITO predicoes (se COLUMN_NOT_FOUND em saldo_real):
--   payloads/athena_migrate_tb_saldo_previsto_prod.sql
--
-- NOMES (docs/DATA_MODEL.md) — COALESCE exige as 4 colunas no catalogo Glue:
--   saldo_predito    = COALESCE(saldo_predito, saldo_previsto)
--   saldo_realizado  = COALESCE(saldo_realizado, saldo_real)
-- Runs novos: só predito/realizado preenchidos. Runs antigos: só previsto/real.

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
-- Gabarito: predito vs realizado (holdout de teste por cliente)
-- saldo_realizado = valor observado (gabarito); saldo_predito = modelo
-- =============================================================================

-- Amostra cliente a cliente (último run / modelo)
SELECT cliente_id,
       segmento,
       ano,
       mes,
       ROUND(COALESCE(saldo_predito, saldo_previsto), 2) AS saldo_predito,
       ROUND(COALESCE(saldo_realizado, saldo_real), 2) AS gabarito_saldo_realizado,
       ROUND(erro_absoluto, 2) AS erro_absoluto,
       ROUND(erro_percentual, 2) AS erro_pct_diag,
       modelo_versao,
       run_id,
       dt_processamento
FROM saldo_previsto_db_prod.tb_saldo_previsto_prod
ORDER BY dt_processamento DESC, segmento, cliente_id
LIMIT 100;

-- Gabarito agregado por segmento (último modelo_versao publicado)
WITH ultimo_modelo AS (
  SELECT modelo_versao
  FROM saldo_previsto_db_prod.tb_saldo_previsto_prod
  ORDER BY dt_processamento DESC
  LIMIT 1
)
SELECT p.segmento,
       COUNT(*) AS registros,
       ROUND(AVG(COALESCE(p.saldo_predito, p.saldo_previsto)), 2) AS media_predito,
       ROUND(AVG(COALESCE(p.saldo_realizado, p.saldo_real)), 2) AS media_gabarito,
       ROUND(AVG(COALESCE(p.saldo_predito, p.saldo_previsto) - COALESCE(p.saldo_realizado, p.saldo_real)), 2) AS vies_medio,
       ROUND(100.0 * SUM(p.erro_absoluto) / NULLIF(SUM(ABS(COALESCE(p.saldo_realizado, p.saldo_real))), 0), 2) AS wape_pct
FROM saldo_previsto_db_prod.tb_saldo_previsto_prod p
INNER JOIN ultimo_modelo u ON p.modelo_versao = u.modelo_versao
GROUP BY p.segmento
ORDER BY p.segmento;

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

-- Baselines vs modelo (JSON metricas_baseline — apos migrate + retreino Glue novo)
SELECT dt_processamento, run_id,
       ROUND(wape, 2) AS modelo_wape,
       ROUND(CAST(json_extract_scalar(metricas_baseline, '$.naive_wape') AS double), 2) AS naive_wape,
       ROUND(CAST(json_extract_scalar(metricas_baseline, '$.media_saldos_wape') AS double), 2) AS media_saldos_wape,
       CAST(json_extract_scalar(metricas_baseline, '$.beats_naive') AS boolean) AS beats_naive,
       ROUND(CAST(json_extract_scalar(metricas_baseline, '$.wape_gain_vs_naive_pp') AS double), 2) AS ganho_pp_vs_naive
FROM saldo_previsto_db_prod.tb_metricas_treino
WHERE metricas_baseline IS NOT NULL AND metricas_baseline <> ''
ORDER BY dt_processamento DESC
LIMIT 10;

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

-- Runs que viraram champion (promocao: WAPE >= 1 p.p. melhor, R2 e total_linhas — ver docs/CHAMPION_PROMOTION.md)
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
-- Benchmark do modelo (1 linha) — servidor Athena / dashboard / comparacao entre runs
-- Documentacao: docs/ANALISE_METRICAS_ATHENA.md#query-de-benchmark
-- Retorna: metricas globais do champion + gabarito agregado + WAPE por segmento + baselines
-- Sem champion: troque WHERE is_champion = true por ORDER BY dt_processamento DESC LIMIT 1
-- =============================================================================
WITH champion AS (
  SELECT *
  FROM saldo_previsto_db_prod.tb_metricas_treino
  WHERE is_champion = true
  ORDER BY dt_processamento DESC
  LIMIT 1
),
gabarito AS (
  SELECT
    COUNT(*) AS registros_holdout,
    COUNT(DISTINCT cliente_id) AS clientes,
    ROUND(100.0 * SUM(p.erro_absoluto)
      / NULLIF(SUM(ABS(COALESCE(p.saldo_realizado, p.saldo_real))), 0), 2) AS wape_pct,
    ROUND(AVG(p.erro_absoluto), 2) AS mae,
    ROUND(AVG(COALESCE(p.saldo_predito, p.saldo_previsto)
      - COALESCE(p.saldo_realizado, p.saldo_real)), 2) AS vies_medio
  FROM saldo_previsto_db_prod.tb_saldo_previsto_prod p
  INNER JOIN champion c ON p.modelo_versao = c.modelo_versao
)
SELECT
  c.run_id,
  c.modelo_versao,
  c.dt_processamento,
  c.total_linhas AS linhas_treino,
  ROUND(c.rmse, 2) AS rmse,
  ROUND(c.mae, 2) AS mae,
  ROUND(c.wape, 2) AS wape,
  ROUND(c.r2, 4) AS r2,
  g.registros_holdout,
  g.clientes,
  g.wape_pct AS wape_gabarito,
  g.mae AS mae_gabarito,
  g.vies_medio,
  ROUND(CAST(json_extract_scalar(c.metricas_segmento, '$.VAREJO.wape') AS double), 2) AS wape_varejo,
  ROUND(CAST(json_extract_scalar(c.metricas_segmento, '$.PRIME.wape') AS double), 2) AS wape_prime,
  ROUND(CAST(json_extract_scalar(c.metricas_segmento, '$.PRIVATE.wape') AS double), 2) AS wape_private,
  ROUND(CAST(json_extract_scalar(c.metricas_baseline, '$.naive_wape') AS double), 2) AS baseline_naive_wape,
  ROUND(CAST(json_extract_scalar(c.metricas_baseline, '$.media_saldos_wape') AS double), 2) AS baseline_media_saldos_wape,
  CAST(json_extract_scalar(c.metricas_baseline, '$.beats_naive') AS boolean) AS beats_naive,
  ROUND(CAST(json_extract_scalar(c.metricas_baseline, '$.wape_gain_vs_naive_pp') AS double), 2) AS ganho_pp_vs_naive
FROM champion c
CROSS JOIN gabarito g;

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

-- =============================================================================
-- Diagnostico completo (retreinos + gabarito + segmento) — ver docs/ANALISE_METRICAS_ATHENA.md
-- Validacao prod 2026-05: reconcile 12168 linhas, WAPE ~20.45%, R2 ~0.845
-- =============================================================================
WITH retreinos AS (
  SELECT dt_processamento, run_id, total_linhas, linhas_adicionadas,
         ROUND(rmse, 2) AS rmse, ROUND(wape, 2) AS wape, ROUND(r2, 4) AS r2,
         modelo_versao, is_champion, champion_modelo_versao,
         ROUND(champion_wape, 2) AS champion_wape
  FROM saldo_previsto_db_prod.tb_metricas_treino
  ORDER BY dt_processamento DESC
  LIMIT 15
),
gabarito AS (
  SELECT CAST(ano AS VARCHAR) || '-' || LPAD(CAST(mes AS VARCHAR), 2, '0') AS periodo,
         segmento, COUNT(*) AS registros,
         ROUND(AVG(COALESCE(saldo_predito, saldo_previsto)), 2) AS media_predito,
         ROUND(AVG(COALESCE(saldo_realizado, saldo_real)), 2) AS media_gabarito,
         ROUND(100.0 * SUM(erro_absoluto)
           / NULLIF(SUM(ABS(COALESCE(saldo_realizado, saldo_real))), 0), 2) AS wape_pct
  FROM saldo_previsto_db_prod.tb_saldo_previsto_prod
  GROUP BY ano, mes, segmento
),
por_segmento_ultimo AS (
  SELECT p.segmento, COUNT(*) AS registros,
         ROUND(100.0 * SUM(p.erro_absoluto)
           / NULLIF(SUM(ABS(COALESCE(p.saldo_realizado, p.saldo_real))), 0), 2) AS wape_pct
  FROM saldo_previsto_db_prod.tb_saldo_previsto_prod p
  WHERE p.dt_processamento = (
    SELECT max(dt_processamento) FROM saldo_previsto_db_prod.tb_saldo_previsto_prod
  )
  GROUP BY p.segmento
)
SELECT 'RETREINO' AS tipo, CAST(dt_processamento AS VARCHAR) AS col1, run_id AS col2,
       CAST(total_linhas AS VARCHAR) AS col3, CAST(linhas_adicionadas AS VARCHAR) AS col4,
       CAST(wape AS VARCHAR) AS col5, CAST(rmse AS VARCHAR) AS col6, CAST(r2 AS VARCHAR) AS col7,
       modelo_versao AS col8, CAST(is_champion AS VARCHAR) AS col9,
       COALESCE(champion_modelo_versao, '-') AS col10, COALESCE(CAST(champion_wape AS VARCHAR), '-') AS col11
FROM retreinos
UNION ALL
SELECT 'GABARITO_MES', periodo, segmento, CAST(registros AS VARCHAR),
       CAST(media_predito AS VARCHAR), CAST(media_gabarito AS VARCHAR), CAST(wape_pct AS VARCHAR),
       '-', '-', '-', '-', '-'
FROM gabarito
UNION ALL
SELECT 'SEG_ULTIMO_PROC', segmento, CAST(registros AS VARCHAR), CAST(wape_pct AS VARCHAR),
       '-', '-', '-', '-', '-', '-', '-', '-'
FROM por_segmento_ultimo
ORDER BY tipo, col1 DESC;
