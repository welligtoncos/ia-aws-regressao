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

**Benchmark (1 linha):** use a [query de benchmark](#query-de-benchmark) para comparar o modelo em produção (dashboard, relatório agendado ou outro ambiente).

---

## Query de benchmark

Consulta **única** que resume o **modelo champion atual** como um todo: métricas globais do holdout de teste, conferência nas predições gravadas, WAPE por segmento e baselines (quando o Glue já gravou `metricas_baseline`).

| Uso | Como |
|-----|------|
| Console Athena | Cole a query abaixo; database `saldo_previsto_db_prod` |
| Servidor / BI | Salve como query nomeada ou agende (ex. QuickSight, Grafana Athena plugin) |
| Comparar ambientes | Rode a mesma SQL em `*_prod` vs `*_dev` e compare `wape`, `r2`, `beats_naive` |
| Após retreino | `wape` deve estar próximo de `wape_gabarito` (mesma fórmula, fontes diferentes) |

**Fonte canônica no repositório:** [`payloads/athena_queries.sql`](../payloads/athena_queries.sql) — seção *Benchmark do modelo*.

### SQL

```sql
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
```

### Colunas de saída (1 linha)

| Coluna | Origem | Significado |
|--------|--------|-------------|
| `run_id`, `modelo_versao`, `dt_processamento` | `tb_metricas_treino` | Identificação do retreino que promoveu o champion |
| `linhas_treino` | `total_linhas` | Volume do CSV de treino usado naquele run |
| `rmse`, `mae`, `wape`, `r2` | Holdout global (Glue) | **Benchmark principal** — mesmo cálculo do treino |
| `registros_holdout`, `clientes` | `tb_saldo_previsto_prod` | Tamanho do conjunto de teste publicado |
| `wape_gabarito`, `mae_gabarito` | Agregação nas predições | Conferência; deve aproximar `wape` / `mae` |
| `vies_medio` | Predito − realizado (média) | Negativo = modelo tende a superestimar saldo |
| `wape_varejo`, `wape_prime`, `wape_private` | JSON `metricas_segmento` | Erro por segmento no holdout |
| `baseline_*`, `beats_naive`, `ganho_pp_vs_naive` | JSON `metricas_baseline` | Comparação com naive e média m1–m6; `NULL` até migrate + retreino novo |

### Referência (Rafo044 completo em prod)

| Campo | Valor esperado (ordem de grandeza) |
|-------|-------------------------------------|
| `linhas_treino` | ~12.168 (7 meses × ~2.000 clientes) |
| `wape` / `wape_gabarito` | ~**20,45%** |
| `r2` | ~**0,845** |
| `wape_*` por segmento | ~19–21% |
| `beats_naive` | `true` após baselines no Glue |

Champion validado: `rafo044-20260524182148` · `xgb-saldo-v1-460f98ec`.

### Sem linha de resultado

| Causa | Ação |
|-------|------|
| Nenhum `is_champion = true` ainda | No CTE `champion`, use `ORDER BY dt_processamento DESC LIMIT 1` (último retreino) |
| `wape_gabarito` nulo | Sem predições para o `modelo_versao` do champion — conferir parquets em `processed/tb_saldo_previsto_prod/` |
| Baselines `NULL` | Rodar [`athena_migrate_tb_metricas_treino.sql`](../payloads/athena_migrate_tb_metricas_treino.sql) + `upload_glue_assets` + retreino |

### Alternativa: diagnóstico multi-linha

Para auditoria operacional (últimos retreinos + gabarito por mês + segmento), use a query *Diagnóstico completo* no final de [`athena_queries.sql`](../payloads/athena_queries.sql) — não substitui o benchmark de 1 linha em dashboards.

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
| `rafo044-20260524182148` | **12.168** | **20,45%** | 1543,32 | **0,845** | **true** |
| `rafo044-20260524173006` (reconcile) | **12.168** | **20,45%** | 1543,32 | **0,845** | false |
| `rafo044-20260524171108` (merge parcial) | 6.819 | 24,29% | **1473,74** | 0,837 | substituído |

**Conclusão:** champion **`xgb-saldo-v1-460f98ec`** com painel completo (7 meses, 12.168 linhas). Promoção via [`CHAMPION_PROMOTION.md`](CHAMPION_PROMOTION.md) (WAPE −1 p.p., R², volume).

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

## Revisão pós-validação (checklist de produção)

### O que está bom

| Item | Evidência |
|------|-----------|
| Champion correto | `rafo044-20260524182148` · `xgb-saldo-v1-460f98ec` · WAPE **20,45%** |
| Treino ≈ produção | Holdout ~20,45% · `SEG_ULTIMO_PROC` ~19,7–20,9% por segmento |
| Segmentos equilibrados | VAREJO / PRIME / PRIVATE na mesma faixa |
| Estabilidade 2015 | WAPE mensal ~16–25% sem degradação clara |

### O que precisa de atenção (esclarecido)

| Tópico | Explicação |
|--------|------------|
| **Retreinos duplicados** | Mesmo CSV + mesmo XGBoost → mesmo `modelo_versao` e métricas. **Re-treina de verdade**; evite vários `--reconcile` sem mudar dados. |
| **`linhas_adicionadas = 0`** | **Esperado no reconcile** (CSV substituído antes do Glue, sem merge `incoming/`). Em ticks incrementais deve ser > 0. |
| **Datas 2015 em 2026** | **Intencional** — Rafo044 sintético / backtest; `dt_processamento` é quando o Glue rodou. |
| **PRIVATE amostra pequena** | 38–64 reg./mês → WAPE mais volátil; considerar modelo por segmento ou mínimo N. |
| **Viés** | Há **superestima leve** de saldo (média predito menos negativa que gabarito) — não é “sem viés”. |
| **WAPE 20% vs quê?** | Baselines no Glue: `naive_saldo_m1` e `media_saldos_m1_m6` em `metricas_baseline` (JSON). |

### Baselines (valor agregado do modelo)

Após `upload_glue_assets` + retreino, consulte:

```sql
SELECT run_id, ROUND(wape, 2) AS modelo_wape,
       ROUND(CAST(json_extract_scalar(metricas_baseline, '$.naive_wape') AS double), 2) AS naive_wape,
       CAST(json_extract_scalar(metricas_baseline, '$.beats_naive') AS boolean) AS beats_naive,
       ROUND(CAST(json_extract_scalar(metricas_baseline, '$.wape_gain_vs_naive_pp') AS double), 2) AS ganho_pp
FROM saldo_previsto_db_prod.tb_metricas_treino
WHERE metricas_baseline IS NOT NULL AND metricas_baseline <> ''
ORDER BY dt_processamento DESC LIMIT 5;
```

O modelo deve ter `beats_naive = true` (WAPE menor que persistir `saldo_m1`).

### Próximos passos sugeridos

| Prioridade | Ação |
|------------|------|
| Alta | Não repetir reconcile sem mudança de dados |
| Alta | Comparar `beats_naive` após deploy com baselines |
| Média | Alerta drift: WAPE produção > treino + 2 p.p. (CloudWatch / query agendada) |
| Média | WAPE por faixa de `saldo_m1` (quartis) no Athena |
| Alta (negócio) | Substituir Rafo044 por extrato real do DW |

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
