# AWS IA Regressão — Saldo Previsto

Template de automação AWS com pipeline ML **XGBoost** para previsão de saldo bancário. Combina S3, Glue, Lambda, Step Functions, EventBridge, DynamoDB e Athena.

## Documentação

**[Guia completo de instalação e testes → docs/GUIA_INSTALACAO.md](docs/GUIA_INSTALACAO.md)**

Inclui arquitetura, pré-requisitos, deploy passo a passo, testes (local, Glue, Step Functions, Athena) e troubleshooting.

## Início rápido

```powershell
# 1. Dependências e testes
pip install -r requirements.txt
pytest tests/ -v

# 2. Assets no S3
.\scripts\upload_glue_assets.ps1 -Bucket saldo-previsto-data-prod
.\scripts\package_lambda.ps1 -Bucket saldo-previsto-data-prod -Upload

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
  EB[EventBridge]
  SFN[Step Functions]
  L[Lambda]
  G[Glue XGBoost]
  S3[(S3)]
  ATH[Athena]

  EB --> SFN --> L
  SFN --> G --> S3
  S3 --> ATH
```

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
| Athena Table | `tb_saldo_previsto_prod` |

Consulta Athena:

```sql
SELECT * FROM saldo_previsto_db_prod.tb_saldo_previsto_prod LIMIT 10;
```

## Licença / uso

Template base para novos projetos de automação e ML na AWS. Copie o repositório, ajuste `infra/inventories/<env>/terraform.tfvars` e substitua ARNs da conta.
