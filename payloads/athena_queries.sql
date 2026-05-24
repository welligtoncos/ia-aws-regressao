-- Configurar no Athena: Settings -> Query result location
-- s3://saldo-previsto-data-prod/athena-results/

-- Após cada treino, se partições não aparecerem:
-- MSCK REPAIR TABLE saldo_previsto_db_prod.tb_saldo_previsto_prod;

SELECT
  ano,
  mes,
  segmento,
  COUNT(*) AS registros,
  ROUND(AVG(erro_percentual), 2) AS erro_medio_pct,
  ROUND(AVG(saldo_previsto), 2) AS saldo_previsto_medio
FROM saldo_previsto_db_prod.tb_saldo_previsto_prod
GROUP BY ano, mes, segmento
ORDER BY ano, mes, segmento;

SELECT *
FROM saldo_previsto_db_prod.tb_saldo_previsto_prod
WHERE segmento = 'VAREJO'
LIMIT 20;
