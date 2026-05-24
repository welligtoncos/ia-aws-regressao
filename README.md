# AWS IA Regressão — Saldo Previsto

Template de automação AWS com pipeline ML **XGBoost** para previsão de saldo bancário. Combina S3, Glue, Lambda, Step Functions, EventBridge, DynamoDB e Athena — com **ingestão incremental a cada 10 minutos** em produção.

## Proposta de valor

Automatizar o **treino, a validação e a publicação** de previsões de saldo bancário, com rastreabilidade operacional e consulta analítica em SQL — sem servidor de aplicação.

| Para quem | Entrega |
|-----------|---------|
| **Engenharia de dados / ML** | Pipeline reprodutível (Glue + Step Functions), retreino a cada **10 min**, métricas e feature importance no S3 |
| **Analytics / negócio** | Tabela Athena com previsão vs. real, erro por cliente, segmento e período |
| **Operações** | Histórico de runs no DynamoDB, orquestração visível no Step Functions |

### Insight principal

> O modelo **não erra igual para todos**. A leitura mais útil não é só o R² global — é o **MAPE por segmento e por mês**, que mostra onde priorizar retreino, regras de negócio ou novas features.

### Onde ver evolução e qualidade

| Fonte | O que mostra | Uso |
|-------|----------------|-----|
| **Athena** `saldo_previsto_db_prod.tb_saldo_previsto_prod` | Predições, erro, `modelo_versao`, `dt_processamento` | Erro por segmento/mês; comparar versões após retreinos |
| **Athena** `saldo_previsto_db_prod.tb_metricas_treino` | RMSE, MAPE, linhas adicionadas por `run_id` / `run_date` | Série temporal de qualidade entre retreinos |
| **S3** `models/xgboost_saldo/metricas.json` | RMSE, MAE, R², MAPE do **último** treino | Snapshot da qualidade atual |
| **S3** `models/xgboost_saldo/feature_importance.json` | Variáveis que mais explicam o saldo | Interpretabilidade e auditoria |
| **DynamoDB** `saldo-previsto-results-prod` | Status das execuções (validate → Glue → finalize) | Monitoramento operacional |

Queries prontas em [`payloads/athena_queries.sql`](payloads/athena_queries.sql).

**Erro por segmento (onde o modelo mais precisa melhorar):**

```sql
SELECT segmento,
       COUNT(*) AS registros,
       ROUND(AVG(erro_percentual), 2) AS mape_medio,
       ROUND(AVG(erro_absoluto), 2) AS mae_medio
FROM saldo_previsto_db_prod.tb_saldo_previsto_prod
GROUP BY segmento
ORDER BY mape_medio DESC;
```

**Evolução entre retreinos (compare `modelo_versao`):**

```sql
SELECT modelo_versao,
       MIN(dt_processamento) AS treinado_em,
       ROUND(AVG(erro_percentual), 2) AS mape
FROM saldo_previsto_db_prod.tb_saldo_previsto_prod
GROUP BY modelo_versao
ORDER BY treinado_em;
```

**Últimas métricas globais (CLI):**

```powershell
aws s3 cp s3://saldo-previsto-data-prod/models/xgboost_saldo/metricas.json -
```

Com o EventBridge ativo (`rate(10 minutes)`), a cada ciclo com dados novos o pipeline gera uma nova `modelo_versao` — as queries acima formam a **série temporal de qualidade do modelo**.

### Ingestão incremental (prod — a cada 10 minutos)

Configuração atual em `infra/inventories/prod/terraform.tfvars`:

```hcl
eventbridge_schedule_expression = "rate(10 minutes)"
ml_ingest_mode                  = "micro"
ml_incremental_step_minutes     = 10
ml_ingest_daily_simulated       = true
ml_enable_check_new_data        = true
```

Fluxo:

1. **EventBridge** dispara o Step Functions a cada **10 minutos**
2. **Lambda `check_new_data`** verifica:
   - CSVs novos em `s3://saldo-previsto-data-prod/incoming/` (ETag vs watermark DynamoDB)
   - Se passou o intervalo de **10 min** desde o último lote simulado
3. Se **não há dados novos**, encerra sem treinar (`SkipNoNewData`)
4. Se há dados, o **Glue** faz append de um **micro-lote** (+10 min na última `data_referencia`, ~2 clientes novos por lote) e/ou merge de CSVs em `incoming/`
5. Retreina com split **temporal** e grava métricas em `tb_metricas_treino`
6. **Glue `MaxConcurrentRuns = 1`** evita execuções sobrepostas

Enviar CSV externo:

```powershell
aws s3 cp meu_lote.csv s3://saldo-previsto-data-prod/incoming/meu_lote.csv
```

O próximo ciclo (≤10 min) detecta o arquivo, treina e marca o ETag no DynamoDB (`__ingest_watermark__`).

```sql
-- Evolução do modelo a cada retreino (micro-lotes de 10 min)
SELECT run_date, run_id, total_linhas, linhas_adicionadas,
       ROUND(rmse, 2) AS rmse, ROUND(mape, 4) AS mape, modelo_versao
FROM saldo_previsto_db_prod.tb_metricas_treino
ORDER BY dt_processamento DESC;
```

Teste manual da ingestão (sem treinar):

```powershell
python scripts/run_incremental_daily.py --run-id teste-micro-1
```

<details>
<summary>Modo diário (legacy — não usado em prod)</summary>

Para retreino **uma vez por dia** em vez de micro-lotes, altere no tfvars:

```hcl
eventbridge_schedule_expression = "cron(0 6 * * ? *)"   # 06:00 UTC
ml_ingest_mode                  = "daily"
```

Nesse modo o Glue adiciona **+1 dia** e **10 clientes novos** por execução.

</details>


**[Guia completo de instalação e testes → docs/GUIA_INSTALACAO.md](docs/GUIA_INSTALACAO.md)**

Inclui arquitetura, pré-requisitos, deploy passo a passo, testes (local, Glue, Step Functions, Athena) e troubleshooting.

## Início rápido

```powershell
# 1. Dependências e testes
pip install -r requirements.txt
pytest tests/ -v

# 2. Assets no S3 (obrigatório após mudanças no código)
.\scripts\upload_glue_assets.ps1 -Bucket saldo-previsto-data-prod
.\scripts\package_lambda.ps1 -Bucket saldo-previsto-data-prod -Upload
aws lambda update-function-code `
  --function-name saldo-previsto-lambda-prod `
  --s3-bucket saldo-previsto-data-prod `
  --s3-key builds/handler.zip `
  --region us-east-1

# 3. Infraestrutura
cd infra
terraform init
terraform apply "-var-file=inventories/prod/terraform.tfvars"

# 4. Disparar pipeline
aws stepfunctions start-execution `
  --state-machine-arn arn:aws:states:us-east-1:303238378103:stateMachine:saldo-previsto-sfn-prod `
  --input file://../payloads/sfn_input.json
```

## Arquitetura

```mermaid
flowchart LR
  EB[EventBridge 10min]
  SFN[Step Functions]
  L1[Lambda check/validate]
  G[Glue XGBoost]
  L2[Lambda finalize]
  S3[(S3)]
  ATH[Athena]
  DDB[(DynamoDB watermark)]

  EB --> SFN --> L1
  L1 -->|dados novos| G
  L1 -->|sem dados| Skip[SkipNoNewData]
  G --> S3
  G --> L2 --> DDB
  S3 --> ATH
```

## Desligar o pipeline

Para **parar treinos automáticos** sem apagar modelo, predições ou tabelas Athena:

**Imediato (CLI):**

```powershell
aws events disable-rule --name saldo-previsto-schedule-prod --region us-east-1
```

**Permanente (Terraform)** — em `infra/inventories/prod/terraform.tfvars`:

```hcl
enable_eventbridge_schedule = false
```

```powershell
cd infra
terraform apply "-var-file=inventories/prod/terraform.tfvars"
```

Para **parar só a ingestão simulada** (pipeline só treina com CSV em `incoming/`):

```hcl
ml_ingest_daily_simulated = false
```

Nesse caso o EventBridge continua disparando a cada 10 min, mas encerra em `SkipNoNewData` até chegar arquivo em `incoming/`.

Para **religar**:

```powershell
aws events enable-rule --name saldo-previsto-schedule-prod --region us-east-1
```

O modelo em `models/xgboost_saldo/` e as tabelas Athena continuam consultáveis com o agendamento desligado.

## Modos de operação

| `workload_type` | Uso |
|-----------------|-----|
| `pipeline` | Fluxo completo (SFN + Lambda + Glue) — **prod atual** |
| `glue` | Apenas Glue Job |
| `lambda` | Apenas Lambda |
| `stepfunctions` | Apenas Step Functions |

## Estrutura principal

```
app/src/           # ML local
glue_bundle/       # Código deployado no Glue
workloads/         # Lambda + libs compartilhadas
infra/             # Terraform (modules + inventories)
scripts/           # Deploy e utilitários
payloads/          # Inputs SFN e SQL Athena
docs/              # Documentação
```

## Comandos

| Comando | Ação |
|---------|------|
| `make install` | Instala dependências |
| `make test` | Roda pytest |
| `make plan-prod` | Terraform plan (prod) |
| `make apply-prod` | Terraform apply (prod) |
| `make generate-data` | Gera dataset sintético local |

## Recursos prod (referência)

| Serviço | Nome |
|---------|------|
| S3 | `saldo-previsto-data-prod` |
| Glue Job | `saldo-previsto-glue-job-prod` |
| Step Functions | `saldo-previsto-sfn-prod` |
| Athena DB | `saldo_previsto_db_prod` |
| Athena Table (predições) | `tb_saldo_previsto_prod` |
| Athena Table (métricas) | `tb_metricas_treino` |
| EventBridge | `saldo-previsto-schedule-prod` (`rate(10 minutes)`) |

Consulta Athena:

```sql
SELECT * FROM saldo_previsto_db_prod.tb_saldo_previsto_prod LIMIT 10;
```

## Licença / uso

Template base para novos projetos de automação e ML na AWS. Copie o repositório, ajuste `infra/inventories/<env>/terraform.tfvars` e substitua ARNs da conta.
