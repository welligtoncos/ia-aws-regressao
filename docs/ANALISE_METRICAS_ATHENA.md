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
