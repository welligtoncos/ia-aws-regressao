-- Athena: Settings -> Query result location = s3://saldo-previsto-data-prod/athena-results/
-- Database: saldo_previsto_db_prod

-- Visão geral por partição
SELECT ano, mes, segmento,
       COUNT(*) AS registros,
       ROUND(AVG(erro_percentual), 2) AS erro_medio_pct,
       ROUND(AVG(saldo_previsto), 2) AS saldo_previsto_medio
FROM saldo_previsto_db_prod.tb_saldo_previsto_prod
GROUP BY ano, mes, segmento
ORDER BY ano, mes, segmento;

-- Proposta de valor: erro por segmento (insight principal)
SELECT segmento,
       COUNT(*) AS registros,
       ROUND(AVG(erro_percentual), 2) AS mape_medio,
       ROUND(AVG(erro_absoluto), 2) AS mae_medio,
       ROUND(AVG(saldo_real), 2) AS saldo_real_medio
FROM saldo_previsto_db_prod.tb_saldo_previsto_prod
GROUP BY segmento
ORDER BY mape_medio DESC;

-- Sazonalidade: erro por mês
SELECT ano, mes, segmento,
       COUNT(*) AS n,
       ROUND(AVG(erro_percentual), 2) AS mape,
       ROUND(STDDEV(erro_percentual), 2) AS volatilidade_erro
FROM saldo_previsto_db_prod.tb_saldo_previsto_prod
GROUP BY ano, mes, segmento
ORDER BY ano, mes, segmento;

-- Evolução entre retreinos (modelo_versao)
SELECT modelo_versao,
       MIN(dt_processamento) AS treinado_em,
       COUNT(*) AS registros,
       ROUND(AVG(erro_percentual), 2) AS mape,
       ROUND(AVG(erro_absoluto), 2) AS mae
FROM saldo_previsto_db_prod.tb_saldo_previsto_prod
GROUP BY modelo_versao
ORDER BY treinado_em;

-- Detalhe amostral
SELECT cliente_id, saldo_previsto, saldo_real, erro_percentual, modelo_versao
FROM saldo_previsto_db_prod.tb_saldo_previsto_prod
WHERE segmento = 'VAREJO'
LIMIT 20;
