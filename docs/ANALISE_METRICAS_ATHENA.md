# Análise de métricas no Athena (Rafo044 / produção)

Guia para interpretar retreinos após `run_rafo044_experiment.py` (incluindo `--reconcile`).

## Configuração no console

| Campo | Valor |
|--------|--------|
| **Query result location** | `s3://saldo-previsto-data-prod/athena-results/` |
| **Database** | `saldo_previsto_db_prod` |

**Pré-requisitos** (se `COLUMN_NOT_FOUND`):

- [`payloads/athena_migrate_tb_metricas_treino.sql`](../payloads/athena_migrate_tb_metricas_treino.sql)
- [`payloads/athena_migrate_tb_saldo_previsto_prod.sql`](../payloads/athena_migrate_tb_saldo_previsto_prod.sql)

Queries prontas: [`payloads/athena_queries.sql`](../payloads/athena_queries.sql).

---

## Duas tabelas

| Tabela | Conteúdo | Use para |
|--------|----------|----------|
| `tb_metricas_treino` | 1 linha por retreino: RMSE, WAPE, R², champion, `metricas_segmento` (JSON) | Evolução entre runs; comparar modelos |
| `tb_saldo_previsto_prod` | 1 linha por cliente/mês no teste: predito vs realizado, erro | Gabarito; WAPE por segmento/mês; outliers |

Relatórios locais (mesma lógica, sem Athena):

```powershell
python scripts/run_rafo044_experiment.py --export-reports
```

- `data/reports/evolucao_metricas.csv` ↔ `tb_metricas_treino`
- `data/reports/gabarito_por_mes.csv` ↔ agregação em `tb_saldo_previsto_prod`

---

## Fluxo recomendado após `--reconcile`

1. Confirmar ingestão:

   ```powershell
   python scripts/run_rafo044_experiment.py --verify-only
   ```

   Esperado: `[OK] Todos os meses do painel estão no CSV de treino` (ex.: 2015-06 … 2015-12).

2. No Athena — evolução dos retreinos:

   ```sql
   SELECT dt_processamento, run_id, total_linhas,
          ROUND(rmse, 2) AS rmse,
          ROUND(wape, 2) AS wape,
          ROUND(r2, 4) AS r2,
          modelo_versao, is_champion
   FROM saldo_previsto_db_prod.tb_metricas_treino
   ORDER BY dt_processamento;
   ```

3. Filtrar o run do reconcile (prefixo `rafo044-` quando disparado pelo script):

   ```sql
   SELECT *
   FROM saldo_previsto_db_prod.tb_metricas_treino
   WHERE run_id LIKE 'rafo044-%'
   ORDER BY dt_processamento DESC;
   ```

4. Gabarito por mês/segmento:

   ```sql
   SELECT ano, mes, segmento,
          COUNT(*) AS registros,
          ROUND(AVG(COALESCE(saldo_predito, saldo_previsto)), 2) AS media_predito,
          ROUND(AVG(COALESCE(saldo_realizado, saldo_real)), 2) AS media_gabarito,
          ROUND(100.0 * SUM(erro_absoluto)
            / NULLIF(SUM(ABS(COALESCE(saldo_realizado, saldo_real))), 0), 2) AS wape_pct
   FROM saldo_previsto_db_prod.tb_saldo_previsto_prod
   GROUP BY ano, mes, segmento
   ORDER BY ano, mes, segmento;
   ```

5. Amostra cliente a cliente (último processamento):

   ```sql
   SELECT cliente_id, segmento, ano, mes,
          ROUND(COALESCE(saldo_predito, saldo_previsto), 2) AS saldo_predito,
          ROUND(COALESCE(saldo_realizado, saldo_real), 2) AS gabarito,
          ROUND(erro_absoluto, 2) AS erro_absoluto,
          modelo_versao, run_id
   FROM saldo_previsto_db_prod.tb_saldo_previsto_prod
   WHERE dt_processamento = (
     SELECT max(dt_processamento)
     FROM saldo_previsto_db_prod.tb_saldo_previsto_prod
   )
   ORDER BY segmento, cliente_id
   LIMIT 100;
   ```

---

## Como ler os números

| Métrica | Onde | Interpretação |
|---------|------|----------------|
| **WAPE** | `tb_metricas_treino.wape` e agregações em predições | Principal. `SUM(|erro|) / SUM(|realizado|)` em %. **Menor = melhor**. |
| **RMSE** | `tb_metricas_treino.rmse` | Penaliza erros grandes; bom para comparar runs. |
| **R²** | `tb_metricas_treino.r2` | Variância explicada no holdout (~0,84–0,85 é típico no Rafo044 completo). |
| **MAPE** | `mape` / `erro_percentual` | Diagnóstico; explode com saldo real baixo — prefira WAPE. |
| **`is_champion`** | `tb_metricas_treino` | `true` só se o novo modelo superou o champion (regra de promoção no Glue). |
| **`linhas_adicionadas`** | `tb_metricas_treino` | No `--reconcile` costuma ser **0** (CSV substituído, sem merge incremental). |

**Referência de qualidade (Rafo044 ~2000 clientes, painel completo):** WAPE global no holdout costuma ficar na faixa **~18–25%** (bem abaixo de ~79% do pipeline antigo com dados aleatórios).

---

## Validação em produção (prova de que funciona)

Resultados **reais** obtidos no Athena (`saldo_previsto_db_prod`) após:

- Painel Rafo044 sintético (~**2.000** clientes, **7** meses: 2015-06 … 2015-12)
- `python scripts/run_rafo044_experiment.py --reconcile --upload`
- Glue `SUCCEEDED` · `dados_treino.csv` com **12.168** linhas · `--verify-only` sem meses faltando

Comparativo com o pipeline legado (dados aleatórios + target vazado): WAPE ~**79%** → após correção e Rafo044: WAPE ~**20%**.

### Métricas globais do retreino (holdout)

| Run | `total_linhas` | WAPE | RMSE | R² | `is_champion` |
|-----|----------------|------|------|-----|---------------|
| `rafo044-20260524173006` (reconcile) | **12.168** | **20,45%** | 1543,32 | **0,845** | false |
| `rafo044-20260524171108` (merge parcial) | 6.819 | 24,29% | **1473,74** | 0,837 | **true** |

**Conclusão:** o pipeline **treina, publica métricas no Athena e predições particionadas** de forma reproduzível. O modelo com **painel completo** tem melhor WAPE e R² que o treino com dados incompletos.

> **Atenção (champion):** a promoção usa **RMSE** (≥ 2% melhor que o anterior). O champion pode permanecer em um run com **menos linhas** e WAPE pior, enquanto o reconcile com 12.168 linhas não vira champion. Para produção, alinhar champion ao run com CSV completo (novo reconcile após reset do champion ou ajuste da regra).

### Gabarito por mês e segmento (WAPE %)

Estável entre **~17% e ~25%** em todos os meses do painel:

| Período | VAREJO | PRIME | PRIVATE |
|---------|--------|-------|---------|
| 2015-06 | 21,45 | 22,11 | 16,31 |
| 2015-09 | 19,44 | 21,97 | 20,37 |
| 2015-12 | 19,63 | 19,60 | 24,50 |

Predições e gabarito consultáveis no SQL; médias de saldo no teste são negativas (característica do dataset sintético Rafo044).

### WAPE por segmento (último processamento)

| Segmento | Registros (teste) | WAPE |
|----------|-------------------|------|
| PRIVATE | 370 | **19,72%** |
| VAREJO | 1.944 | 20,31% |
| PRIME | 1.169 | 20,94% |

**Conclusão:** erro **homogêneo entre segmentos** (~20% WAPE), adequado para dashboards de negócio e comparação mês a mês.

### Viés observado (auditoria)

Em vários meses, a média predita fica **menos negativa** que o gabarito (ex.: dez/2015 VAREJO: predito -4869 vs realizado -4895) — tendência leve de **superestimar saldo**. Útil para calibrar decisões de crédito/tesouraria (não tratar só o WAPE agregado).

### O que isso prova

| Critério | Evidência |
|----------|-----------|
| Ingestão e merge | 7 meses no CSV; 3 lotes `incoming/`; reconcile com 12.168 linhas |
| Treino ML | RMSE/WAPE/R² gravados em `tb_metricas_treino` |
| Predições | Parquets em `tb_saldo_previsto_prod` + consulta Athena |
| Qualidade utilizável | WAPE ~20% vs ~79% do cenário legado |
| Escalabilidade de consumo | SQL por `segmento`, `ano`, `mes`, `cliente_id` sem app dedicada |

### Reproduzir o diagnóstico

Cole o resultado desta query no Athena (ou use [`payloads/athena_queries.sql`](../payloads/athena_queries.sql) — seção *Diagnóstico completo*):

```sql
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
```

---

## Troubleshooting

| Sintoma | Ação |
|---------|------|
| Tabela vazia ou sem run novo | `SELECT COUNT(*) FROM ...`; conferir parquets em `s3://saldo-previsto-data-prod/processed/` |
| Partições antigas | Glue crawler ou `MSCK REPAIR TABLE` na tabela particionada |
| `COLUMN_NOT_FOUND` em `saldo_real` | Rodar migração `athena_migrate_tb_saldo_previsto_prod.sql`; usar `COALESCE(saldo_realizado, saldo_real)` |
| `metricas_segmento` nulo | Retreino com bundle Glue atual; aplicar `athena_migrate_tb_metricas_treino.sql` |

---

## Ver também

- [`docs/DATA_MODEL.md`](DATA_MODEL.md) — glossário `saldo_alvo` / `saldo_predito` / `saldo_realizado`
- [`README.md`](../README.md) — seção *Queries essenciais (Athena)* e *Dataset Rafo044*
