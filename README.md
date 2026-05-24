# AWS IA Regressão — Saldo Previsto

Template de automação AWS com pipeline ML **XGBoost** para previsão de saldo bancário. Combina S3, Glue, Lambda, Step Functions, EventBridge, DynamoDB e Athena. Em **prod** o agendamento EventBridge está **desligado**; retreinos são disparados por scripts (`run_rafo044_experiment`) ou `start-execution` / `start-job-run` manual (ver [`infra/inventories/prod/terraform.tfvars`](infra/inventories/prod/terraform.tfvars)).

## Proposta de valor

Automatizar o **treino, a validação e a publicação** de previsões de saldo bancário, com rastreabilidade operacional e consulta analítica em SQL — sem servidor de aplicação.

| Para quem | Entrega |
|-----------|---------|
| **Engenharia de dados / ML** | Pipeline reprodutível (Glue + Step Functions), métricas (RMSE, WAPE, por segmento) e feature importance no S3; retreino agendável via EventBridge ou sob demanda |
| **Analytics / negócio** | Tabela Athena com previsão vs. real, erro por cliente, segmento e período |
| **Produto / estratégia** | Casos de uso reais (tesouraria, crédito, CRM) e roadmap de escala — **[docs/USO_REAL_E_ESCALABILIDADE.md](docs/USO_REAL_E_ESCALABILIDADE.md)** |
| **Operações** | Histórico de runs no DynamoDB, orquestração visível no Step Functions — diagrama: **[docs/FLUXO_TREINAMENTO_AWS.md](docs/FLUXO_TREINAMENTO_AWS.md)** |

### Insight principal

> O modelo **não erra igual para todos**. A leitura mais útil combina **WAPE por segmento** (estável com saldos baixos) e erro por mês — não só R² global. **MAPE** permanece apenas como diagnóstico (oscila quando `saldo_real` é próximo de zero).

### Modelagem de dados

Glossário completo (tabelas, colunas, `is_champion`): **[docs/DATA_MODEL.md](docs/DATA_MODEL.md)**

| Nome | Onde | Significado |
|------|------|-------------|
| `saldo_alvo` | CSV treino | Rótulo: saldo do **próximo** período |
| `saldo_predito` | Athena predições | Saída do **modelo** |
| `saldo_realizado` | Athena predições | Valor **observado** no teste |

### Alvo e qualidade do modelo

| Aspecto | Comportamento |
|---------|----------------|
| **Alvo (`saldo_alvo`)** | Saldo do **próximo período** (`saldo_m1` shift por cliente), sem fórmula no mesmo período — evita vazamento de features |
| **Split** | Temporal **treino / validação / teste**; validação para early stopping; métricas finais no teste |
| **Métrica principal** | **WAPE** (promoção champion e negócio); **RMSE** registrado, não define promoção |
| **Diagnóstico** | MAPE, SMAPE, R² |

### Onde ver evolução e qualidade

| Fonte | O que mostra | Uso |
|-------|----------------|-----|
| **Athena** `tb_saldo_previsto_prod` | Predições, `erro_absoluto`, `erro_percentual`, `modelo_versao` | WAPE/MAE por segmento e mês nas predições publicadas |
| **Athena** `tb_metricas_treino` | RMSE, WAPE, SMAPE, MAPE, `metricas_segmento` (JSON), `is_champion` | Série temporal entre retreinos (1 partição por `run_id`) |
| **S3** `models/xgboost_saldo/metricas.json` | Métricas globais + `metricas_segmento` do último treino | Snapshot atual |
| **S3** `models/xgboost_saldo/champion/` | `model.ubj`, métricas e histórico de promoções | Modelo oficial quando WAPE melhora **≥ 1 p.p.**, R² e volume OK — ver **[docs/CHAMPION_PROMOTION.md](docs/CHAMPION_PROMOTION.md)** |
| **S3** `feature_importance.json` | Importância das variáveis | Auditoria de features |
| **DynamoDB** `saldo-previsto-results-prod` | Status validate → Glue → finalize | Operação |

Queries completas: [`payloads/athena_queries.sql`](payloads/athena_queries.sql). Guia de análise: [`docs/ANALISE_METRICAS_ATHENA.md`](docs/ANALISE_METRICAS_ATHENA.md) (inclui **validação em prod**: WAPE ~20% após reconcile, evidência no Athena).

**Erro `COLUMN_NOT_FOUND: metricas_segmento`?** O catálogo Athena em prod ainda não tem as colunas novas. Execute uma vez [`payloads/athena_migrate_tb_metricas_treino.sql`](payloads/athena_migrate_tb_metricas_treino.sql) no console Athena (ou `terraform apply`), depois rode um retreino com o Glue atualizado.

### Model registry (champion)

A cada retreino o Glue treina do zero e grava métricas. O `.ubj` **só vai para** `models/xgboost_saldo/champion/` quando o run **promove** o campeão:

| Critério | Regra |
|----------|--------|
| **WAPE (primária)** | Novo WAPE **≥ 1 p.p. menor** que o champion (`CHAMPION_MIN_WAPE_IMPROVEMENT_PP = 1.0`) |
| **R²** | Não piora mais que **0,01** vs champion |
| **Volume** | `total_linhas` do treino **≥** linhas do champion |
| **`is_champion = true`** | Run que gravou novo `champion/model.ubj` |

Detalhes: **[docs/CHAMPION_PROMOTION.md](docs/CHAMPION_PROMOTION.md)**.

```powershell
aws s3 cp s3://saldo-previsto-data-prod/models/xgboost_saldo/champion/champion_meta.json -
aws s3 cp s3://saldo-previsto-data-prod/models/xgboost_saldo/metricas.json -
```

### Queries essenciais (Athena)

Database: `saldo_previsto_db_prod`. Result location: `s3://saldo-previsto-data-prod/athena-results/`.

Colunas `wape`, `smape`, `metricas_segmento` e `champion_wape` existem após **terraform apply** e novos retreinos; runs antigos podem ter `NULL`.

**1. Evolução do treino** (métricas globais do holdout):

```sql
SELECT dt_processamento, run_id,
       ROUND(rmse, 2) AS rmse,
       ROUND(wape, 2) AS wape,
       ROUND(mape, 4) AS mape_diag,
       linhas_adicionadas, modelo_versao, is_champion
FROM saldo_previsto_db_prod.tb_metricas_treino
ORDER BY dt_processamento DESC
LIMIT 30;
```

**2. WAPE por segmento no último retreino** (`metricas_segmento` JSON):

```sql
WITH ultimo AS (
  SELECT * FROM saldo_previsto_db_prod.tb_metricas_treino
  ORDER BY dt_processamento DESC LIMIT 1
)
SELECT run_id,
       ROUND(wape, 2) AS wape_global,
       ROUND(CAST(json_extract_scalar(metricas_segmento, '$.VAREJO.wape') AS double), 2) AS wape_varejo,
       ROUND(CAST(json_extract_scalar(metricas_segmento, '$.PRIME.wape') AS double), 2) AS wape_prime,
       ROUND(CAST(json_extract_scalar(metricas_segmento, '$.PRIVATE.wape') AS double), 2) AS wape_private
FROM ultimo
WHERE metricas_segmento IS NOT NULL AND metricas_segmento <> '';
```

**3. Campeão atual**:

```sql
SELECT dt_processamento, run_id, modelo_versao,
       ROUND(rmse, 2) AS rmse, ROUND(wape, 2) AS wape
FROM saldo_previsto_db_prod.tb_metricas_treino
WHERE is_champion = true
ORDER BY dt_processamento DESC
LIMIT 5;
```

**4. Gabarito por mês** (após reconcile ou export local):

```sql
SELECT ano, mes, segmento,
       COUNT(*) AS registros,
       ROUND(100.0 * SUM(erro_absoluto)
         / NULLIF(SUM(ABS(COALESCE(saldo_realizado, saldo_real))), 0), 2) AS wape_pct
FROM saldo_previsto_db_prod.tb_saldo_previsto_prod
GROUP BY ano, mes, segmento
ORDER BY ano, mes, segmento;
```

**5. Erro por segmento nas predições** (WAPE estável):

```sql
SELECT segmento,
       COUNT(*) AS registros,
       ROUND(100.0 * SUM(erro_absoluto)
         / NULLIF(SUM(ABS(COALESCE(saldo_realizado, saldo_real))), 0), 2) AS wape_pct,
       ROUND(AVG(erro_percentual), 2) AS mape_diag,
       ROUND(AVG(erro_absoluto), 2) AS mae_medio
FROM saldo_previsto_db_prod.tb_saldo_previsto_prod
GROUP BY segmento
ORDER BY wape_pct DESC;
```

**6. Tendência suavizada** (média móvel de 5 retreinos):

```sql
SELECT dt_processamento,
       ROUND(rmse, 2) AS rmse,
       ROUND(wape, 2) AS wape,
       ROUND(AVG(wape) OVER (ORDER BY dt_processamento ROWS BETWEEN 4 PRECEDING), 2) AS wape_media_5,
       is_champion
FROM saldo_previsto_db_prod.tb_metricas_treino
ORDER BY dt_processamento DESC
LIMIT 30;
```

Com EventBridge **habilitado** (`enable_eventbridge_schedule = true`), há tentativa de pipeline na cadência configurada (ex. `rate(2 minutes)`); linha em `tb_metricas_treino` só quando o Glue **efetivamente treina** (sem `SkipNoNewData` / `SkipGlueBusy`). Com o schedule **desligado** (estado atual em prod), use `--export-reports` ou Athena após cada treino manual.

**Interpretação rápida:** prefira **WAPE** para conclusões; use **RMSE** para comparar runs; **MAPE**/`erro_percentual` só como diagnóstico. Guia completo (pós-reconcile, troubleshooting): [`docs/ANALISE_METRICAS_ATHENA.md`](docs/ANALISE_METRICAS_ATHENA.md).

### Uso em produção real e escalabilidade

Casos de uso (tesouraria, crédito, CRM, cobrança), diagramas de integração com data lake e roadmap POC → escala:

**[docs/USO_REAL_E_ESCALABILIDADE.md](docs/USO_REAL_E_ESCALABILIDADE.md)**

### Treinamento e serviços AWS

Fluxo de retreino (Step Functions → Lambda → Glue → S3 → Athena) e tabela de serviços AWS:

**[docs/FLUXO_TREINAMENTO_AWS.md](docs/FLUXO_TREINAMENTO_AWS.md)**

### Dataset Rafo044 (banco sintético com série temporal)

Fonte: [Rafo044/Synthetic_Bank_Dataset](https://github.com/Rafo044/Synthetic_Bank_Dataset). O repositório remoto pode não incluir `transactions.parquet`; gere com `scripts/synthetic_data_create.py` (polars + faker) e use a pasta `data/` ou `synthetic_output/`.

```powershell
python scripts/run_etl_rafo044.py --clone data/rafo044/repo
# após gerar transactions.parquet no clone:
python scripts/run_etl_rafo044.py --data-dir data/rafo044/repo/data --output data/dados_treino.csv --max-customers 5000
python scripts/run_etl_rafo044.py --data-dir data/rafo044/repo/data --split-at 2016-02 --output data/dados_treino.csv --incoming-output data/incoming/lote_2016-02.csv
python scripts/run_etl_rafo044.py --data-dir data/rafo044/repo/data --output data/dados_treino.csv --upload --bucket saldo-previsto-data-prod
```

Em prod, `ml_ingest_daily_simulated = false` (já no `terraform.tfvars`): o Glue **não** gera micro-lotes aleatórios; só merge de `incoming/` + treino com `dados_treino.csv`.

**Ingestão Rafo044 (estado real em prod — sem EventBridge):**

O agendamento automático está **pausado** (`enable_eventbridge_schedule = false`). Cada lote e cada treino são disparados pelos scripts (Step Functions ou Glue direto), não por cron na AWS.

```powershell
cd C:\welligton-pos-IA\aws-ia-regressao
python scripts/generate_rafo044_sample.py --customers 2000
python scripts/automate_rafo044_ingest.py --init --upload
# Opção A: um comando (recomendado)
python scripts/run_rafo044_experiment.py --run-all --upload --wait-glue
# Opção B: loop local (só upload; você dispara SFN/Glue ou use --run-all)
python scripts/automate_rafo044_ingest.py --loop --interval-minutes 3 --upload
```

Compare predito vs realizado: `payloads/athena_queries.sql` (seção **Gabarito**) ou [`docs/ANALISE_METRICAS_ATHENA.md`](docs/ANALISE_METRICAS_ATHENA.md).

**Se religar o EventBridge** (`enable_eventbridge_schedule = true` + `terraform apply`), cada CSV em `incoming/` pode ser detectado no próximo ciclo (`rate(2 minutes)` no tfvars hoje; pode mudar para `rate(15 minutes)`).

**Um único procedimento** (todos os lotes + treino após cada um + CSV de evolução):

```powershell
python scripts/run_rafo044_experiment.py --run-all --upload --wait-glue
# Relatórios: data/reports/evolucao_metricas.csv e data/reports/gabarito_por_mes.csv
```

O `--run-all` aguarda o **JobRun do Glue iniciado após cada Step Functions** (não o último job da conta) e faz pausa de 30s entre lotes. Para evitar merge parcial por concorrência, use `--upload-all-incoming-once` (envia todos os lotes e dispara **um** Glue com todos os `INCOMING_KEYS`).

**Verificar estado no S3** (sem upload):

```powershell
python scripts/run_rafo044_experiment.py --verify-only
```

Se aparecer `[AVISO]` com meses faltando em `dados_treino.csv` (ex.: 2015-10, 2015-12), o merge incremental ficou incompleto — corrija com `--reconcile` abaixo.

**Reconcile** (painel completo + 1 treino — recomendado após merge incompleto):

```powershell
python scripts/run_rafo044_experiment.py --reconcile --upload
```

Equivalente manual (Parte A — ops sem esperar script novo):

```powershell
python scripts/generate_rafo044_sample.py --customers 2000
python scripts/run_etl_rafo044.py --data-dir data/rafo044/raw --output data/dados_treino_full.csv
aws s3 cp data/dados_treino_full.csv s3://saldo-previsto-data-prod/raw/saldo_previsto/dados_treino.csv
aws glue start-job-run --job-name saldo-previsto-glue-job-prod --region us-east-1 `
  --arguments '{"--run_id":"reconcile-full","--INGEST_DAILY":"false","--INCOMING_KEYS":"[]"}'
python scripts/run_rafo044_experiment.py --verify-only
python scripts/run_rafo044_experiment.py --export-reports
```

Critério de sucesso: `--verify-only` sem meses faltando; `dados_treino.csv` com todos os meses do painel (ex. 2015-06 … 2015-12); linhas no CSV tipicamente ~10–12 mil (menor que o painel local porque o Glue remove linhas sem `saldo_alvo`).

**Analisar métricas após reconcile:**

```powershell
python scripts/run_rafo044_experiment.py --export-reports
```

No Athena (database `saldo_previsto_db_prod`), comece por:

```sql
-- Evolução de todos os retreinos
SELECT dt_processamento, run_id, ROUND(wape, 2) AS wape, ROUND(rmse, 2) AS rmse,
       total_linhas, modelo_versao, is_champion
FROM saldo_previsto_db_prod.tb_metricas_treino
ORDER BY dt_processamento;

-- Runs do experimento Rafo044
SELECT * FROM saldo_previsto_db_prod.tb_metricas_treino
WHERE run_id LIKE 'rafo044-%'
ORDER BY dt_processamento DESC;
```

Mais queries (gabarito por mês, segmento, champion): [`payloads/athena_queries.sql`](payloads/athena_queries.sql) e [`docs/ANALISE_METRICAS_ATHENA.md`](docs/ANALISE_METRICAS_ATHENA.md).

### Ingestão incremental (prod — estado real)

Fonte de verdade: [`infra/inventories/prod/terraform.tfvars`](infra/inventories/prod/terraform.tfvars).

| Parâmetro | Valor em prod | Efeito |
|-----------|---------------|--------|
| `enable_eventbridge_schedule` | **`false`** | Pipeline **não** roda sozinho na AWS |
| `eventbridge_schedule_expression` | `rate(2 minutes)` | Só usado se religar o schedule (reservado no tfvars) |
| `ml_ingest_daily_simulated` | **`false`** | Sem dados aleatórios no Glue; Rafo044 / `incoming/` |
| `ml_ingest_mode` | `micro` | Modo de ingestão (micro-lote quando simulado estiver ligado) |
| `ml_incremental_step_minutes` | `2` | Passo temporal do simulador **só se** `ml_ingest_daily_simulated = true` |
| `ml_enable_check_new_data` | `true` | Lambda detecta CSV novo em `incoming/` (ETag vs watermark) |
| `glue_max_concurrent_runs` | `1` | Um Glue por vez; SFN pode retornar `SkipGlueBusy` |

**Como o treino roda hoje (EventBridge off):**

1. Você envia dados (`automate_rafo044_ingest`, `run_rafo044_experiment`, ou `aws s3 cp` em `incoming/`).
2. Dispara o pipeline manualmente: `run_rafo044_experiment` (`_start_sfn` / `start-job-run`), `aws stepfunctions start-execution`, ou `aws glue start-job-run`.
3. **Step Functions** → **Lambda `check_new_data`** → se há chave nova em `incoming/` (ou simulado pendente, se ligado) → **Glue** merge + treino; senão `SkipNoNewData`.
4. **Glue**: merge `INCOMING_KEYS`, `prepare_training_dataset`, XGBoost, métricas em `tb_metricas_treino`, predições em `tb_saldo_previsto_prod`.
5. **Lambda finalize** atualiza watermark no DynamoDB.

**Fluxo quando EventBridge estiver ligado** (`enable_eventbridge_schedule = true` + `terraform apply`):

1. EventBridge dispara Step Functions na cadência (`rate(2 minutes)` no tfvars; opcional `rate(15 minutes)`).
2. Mesmos passos 3–5; CSV em `incoming/` é detectado no **próximo** ciclo do schedule.

CSV em `incoming/`:

```powershell
aws s3 cp meu_lote.csv s3://saldo-previsto-data-prod/incoming/meu_lote.csv
# Com EventBridge off: dispare o SFN ou Glue após o upload
aws stepfunctions start-execution `
  --state-machine-arn arn:aws:states:us-east-1:303238378103:stateMachine:saldo-previsto-sfn-prod `
  --input file://payloads/sfn_input.json
```

Teste da Lambda de check (sem treinar):

```powershell
python scripts/run_incremental_daily.py --run-id teste-micro-1
```

**Religar agendamento automático** (ex. a cada 15 min):

```hcl
enable_eventbridge_schedule     = true
eventbridge_schedule_expression = "rate(15 minutes)"
```

```powershell
cd infra
terraform apply "-var-file=inventories/prod/terraform.tfvars"
```

<details>
<summary>Modo diário (legacy)</summary>

```hcl
eventbridge_schedule_expression = "cron(0 6 * * ? *)"
ml_ingest_mode                  = "daily"
```

Append de **+1 dia** e **10 clientes novos** por execução.

</details>

**[Guia completo → docs/GUIA_INSTALACAO.md](docs/GUIA_INSTALACAO.md)** — arquitetura, deploy, testes e troubleshooting.

## Início rápido

```powershell
pip install -r requirements.txt
pytest tests/ -v

# Assets no S3 (após mudanças em glue_bundle/ ou workloads/)
.\scripts\upload_glue_assets.ps1 -Bucket saldo-previsto-data-prod
.\scripts\package_lambda.ps1 -Bucket saldo-previsto-data-prod -Upload
aws lambda update-function-code `
  --function-name saldo-previsto-lambda-prod `
  --s3-bucket saldo-previsto-data-prod `
  --s3-key builds/handler.zip `
  --region us-east-1

cd infra
terraform init
terraform apply "-var-file=inventories/prod/terraform.tfvars"

aws stepfunctions start-execution `
  --state-machine-arn arn:aws:states:us-east-1:303238378103:stateMachine:saldo-previsto-sfn-prod `
  --input file://../payloads/sfn_input.json
```

> Após mudança no alvo ou no schema de métricas, regenere ou deixe a ingestão regravar o CSV em `raw/saldo_previsto/dados_treino.csv` para não misturar linhas com alvo antigo (vazado).

## Arquitetura

Diagrama completo (treinamento, serviços AWS, etapas do Glue): **[docs/FLUXO_TREINAMENTO_AWS.md](docs/FLUXO_TREINAMENTO_AWS.md)**.

## Pausar / religar o pipeline

**Estado atual em prod:** `enable_eventbridge_schedule = false` no Terraform — retreino **não** é automático. Treinos vêm de `run_rafo044_experiment`, `start-execution` ou `glue start-job-run`.

**Pausar agendamento** (se estiver ligado na AWS):

```powershell
aws events disable-rule --name saldo-previsto-schedule-prod --region us-east-1
```

```hcl
# infra/inventories/prod/terraform.tfvars
enable_eventbridge_schedule = false
```

**Religar agendamento:**

```hcl
enable_eventbridge_schedule     = true
eventbridge_schedule_expression = "rate(2 minutes)"   # ou rate(15 minutes)
```

```powershell
cd infra
terraform apply "-var-file=inventories/prod/terraform.tfvars"
aws events enable-rule --name saldo-previsto-schedule-prod --region us-east-1
```

**Só dados reais em `incoming/`** (sem simulador no Glue) — já é o padrão em prod:

```hcl
ml_ingest_daily_simulated = false
```

## Modos de operação

| `workload_type` | Uso |
|-----------------|-----|
| `pipeline` | SFN + Lambda + Glue — **prod** |
| `glue` | Apenas Glue Job |
| `lambda` | Apenas Lambda |
| `stepfunctions` | Apenas Step Functions |

## Estrutura principal

```
app/src/              # ML local (model, preprocessor, target)
glue_bundle/          # Deploy Glue (train_pipeline, model_registry, target)
workloads/shared/     # incremental_data, model_registry, target
infra/                # Terraform
scripts/              # Deploy e generate_dataset
payloads/             # SFN input + athena_queries.sql
docs/                 # ... CHAMPION_PROMOTION, ANALISE_METRICAS_ATHENA, USO_REAL_E_ESCALABILIDADE
```

## Comandos

| Comando | Ação |
|---------|------|
| `make install` | Dependências |
| `make test` | pytest |
| `make plan-prod` | Terraform plan |
| `make apply-prod` | Terraform apply |
| `make generate-data` | Dataset sintético local |

## Recursos prod (referência)

| Serviço | Nome |
|---------|------|
| S3 | `saldo-previsto-data-prod` |
| Glue Job | `saldo-previsto-glue-job-prod` |
| Step Functions | `saldo-previsto-sfn-prod` |
| Athena DB | `saldo_previsto_db_prod` |
| Predições | `tb_saldo_previsto_prod` |
| Métricas treino | `tb_metricas_treino` |
| EventBridge | `saldo-previsto-schedule-prod` — **desligado** (`enable_eventbridge_schedule = false`; expressão reservada `rate(2 minutes)`) |
| Champion | `models/xgboost_saldo/champion/model.ubj` |

## Licença / uso

Template para automação e ML na AWS. Copie o repositório, ajuste `infra/inventories/<env>/terraform.tfvars` e substitua ARNs da conta.
