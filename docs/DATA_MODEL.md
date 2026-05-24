# Modelagem de dados — Saldo Previsto

Glossário oficial de camadas, tabelas Athena e nomes de colunas.

## Glossário de colunas (nomes canônicos)

| Nome | Camada | Significado |
|------|--------|-------------|
| **`saldo_alvo`** | CSV de treino | Saldo do **próximo período** (rótulo `y`). Calculado por `shift(saldo_m1)` por cliente. |
| `saldo_previsto` | CSV legado | Nome antigo do alvo; **ignorado** no treino — recalculado como `saldo_alvo`. |
| **`saldo_predito`** | `tb_saldo_previsto_prod` | Saída do **modelo** (`y_pred`) no conjunto de teste. |
| **`saldo_realizado`** | `tb_saldo_previsto_prod` | Valor **observado** no teste (mesmo conceito que `saldo_alvo` naquela linha). |
| `saldo_previsto` / `saldo_real` | Parquet legado | Partições antigas; use `COALESCE` nas queries (ver abaixo). |

> **Regra mnemônica:** *alvo* = treino · *predito* = modelo · *realizado* = fato no teste.

---

## Camadas do pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│ S3 raw/          dados_treino.csv     (treino, não é Athena)    │
│                  incoming/*.csv       (opcional)                 │
├─────────────────────────────────────────────────────────────────┤
│ Glue treino      XGBoost + holdout temporal                      │
├─────────────────────────────────────────────────────────────────┤
│ S3 processed/    tb_metricas_treino/   → 1 linha / retreino      │
│                  tb_saldo_previsto_prod/ → N linhas / teste      │
├─────────────────────────────────────────────────────────────────┤
│ S3 models/       champion/, metricas.json                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 1. Dataset de treino (CSV)

| Item | Valor |
|------|--------|
| **Path** | `s3://saldo-previsto-data-prod/raw/saldo_previsto/dados_treino.csv` |
| **Granularidade** | 1 linha = `cliente_id` + `data_referencia` |
| **Chave** | `(cliente_id, data_referencia)` |
| **Alvo** | `saldo_alvo` |

Colunas principais de **features** (período atual): `saldo_m1`…`saldo_m6`, `valor_creditos_mes`, `valor_debitos_mes`, `segmento`, `renda_mensal`, etc.

Após cada ingestão, `prepare_training_dataset()` recalcula `saldo_alvo` e remove alvo legado vazado.

---

## 2. `tb_metricas_treino` (métricas por retreino)

| Item | Valor |
|------|--------|
| **Database** | `saldo_previsto_db_prod` |
| **S3** | `processed/tb_metricas_treino/run_date=…/run_id=…/` |
| **Partições** | `run_date`, `run_id` |
| **Granularidade** | **1 linha por execução** do Glue |

| Coluna | Descrição |
|--------|-----------|
| `rmse`, `wape`, `r2`, … | Métricas no **holdout de teste** (global) |
| `metricas_segmento` | JSON com métricas por VAREJO / PRIME / PRIVATE |
| `modelo_versao` | ID do modelo deste run |
| `is_champion` | `true` se **este run promoveu** novo `champion/` no S3 |
| `champion_*` | Estado do campeão no S3 após o run |

**Não contém** `cliente_id`. Use para evolução temporal e promoção.

---

## 3. `tb_saldo_previsto_prod` (predições por cliente)

| Item | Valor |
|------|--------|
| **S3** | `processed/tb_saldo_previsto_prod/ano=/mes=/segmento=/` |
| **Partições** | `ano`, `mes`, `segmento` |
| **Granularidade** | 1 linha = 1 cliente no **conjunto de teste** (~20% temporal) |

| Coluna | Descrição |
|--------|-----------|
| `saldo_predito` | Previsão do modelo |
| `saldo_realizado` | Saldo observado (alvo no teste) |
| `erro_absoluto`, `erro_percentual` | Erros derivados |
| `modelo_versao`, `run_id`, `dt_processamento` | Rastreio do retreino |
| `data_referencia` | Período das **features** (não do alvo) |

Cada retreino **acrescenta** linhas; filtre por `dt_processamento` ou `modelo_versao` para o run desejado.

---

## 4. Artefatos S3 (sem Athena)

| Path | Conteúdo |
|------|----------|
| `models/xgboost_saldo/metricas.json` | Último treino |
| `models/xgboost_saldo/champion/model.ubj` | Modelo oficial |
| `models/xgboost_saldo/champion/metrics.json` | Métricas do campeão |

---

## Queries Athena — partições legadas

O **catálogo Glue** precisa declarar as **quatro** colunas (`saldo_predito`, `saldo_realizado`, `saldo_previsto`, `saldo_real`). Sem isso, `COALESCE(saldo_realizado, saldo_real)` gera `COLUMN_NOT_FOUND`.

Execute uma vez: `payloads/athena_migrate_tb_saldo_previsto_prod.sql`

```sql
COALESCE(saldo_predito, saldo_previsto)     AS saldo_predito
COALESCE(saldo_realizado, saldo_real)       AS saldo_realizado
```

| Partição | Colunas preenchidas no Parquet |
|----------|--------------------------------|
| Runs novos (`rename-cols-v1`, etc.) | `saldo_predito`, `saldo_realizado` |
| Runs antigos | `saldo_previsto`, `saldo_real` |

---

## Relacionamento entre tabelas

```
tb_metricas_treino.run_id  ─────┐
         │                        │ mesmo retreino (via run_id / dt_processamento)
         ▼                        ▼
   1 linha agregada          N linhas em tb_saldo_previsto_prod
```

Não há FK formal; junte por `run_id` e `modelo_versao`.

---

## `is_champion` (esclarecimento)

- **`true`** = naquele `run_id`, o pipeline gravou um novo modelo em `champion/`.
- **Não** significa “melhor modelo de todos os tempos”.
- Champion **atual** = último `is_champion = true` por data **ou** arquivo em `champion/champion_meta.json`.

Runs com métricas vazadas (R² ~1) podem ter `is_champion = true`; runs honestos podem ter `false` se não baterem RMSE do champion antigo.

---

## Referências no código

| Módulo | Função |
|--------|--------|
| `workloads/shared/columns.py` | Constantes de nomes |
| `workloads/shared/target.py` | `prepare_training_dataset`, split temporal |
| `glue_bundle/train_pipeline.py` | Orquestração do retreino |
| `payloads/athena_queries.sql` | SQL de monitoramento |
| `docs/ANALISE_METRICAS_ATHENA.md` | Guia de análise no Athena (Rafo044, reconcile) |
