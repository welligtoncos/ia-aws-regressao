# Fluxo de treinamento e serviços AWS

Diagrama do **retreino XGBoost** em produção: orquestração, treino no Glue e artefatos no S3. Estado atual: EventBridge **desligado** — disparo via scripts ou CLI (ver [`infra/inventories/prod/terraform.tfvars`](../infra/inventories/prod/terraform.tfvars)).

---

## Serviços AWS utilizados

| Serviço | Recurso (prod) | Papel no treinamento |
|---------|----------------|----------------------|
| **Amazon S3** | `saldo-previsto-data-prod` | CSV de treino (`raw/`), lotes `incoming/`, script Glue (`scripts/`), libs (`libs/app.zip`), modelos (`models/xgboost_saldo/`), parquets (`processed/`), resultados Athena (`athena-results/`) |
| **AWS Glue** | `saldo-previsto-glue-job-prod` | Job Python Shell: ingestão opcional, preprocessamento, treino XGBoost, métricas, predições, registro de partições |
| **AWS Lambda** | `saldo-previsto-lambda-prod` | `check_new_data`, `validate`, `finalize` (watermark no DynamoDB) |
| **Step Functions** | `saldo-previsto-sfn-prod` | Orquestra Lambda → Glue (sync) → Lambda |
| **Amazon EventBridge** | `saldo-previsto-schedule-prod` | Agenda opcional (`rate(2 minutes)` no tfvars; **OFF** em prod) |
| **Amazon DynamoDB** | `saldo-previsto-results-prod` | Watermark de arquivos `incoming/` e status do run |
| **AWS Glue Data Catalog** | DB `saldo_previsto_db_prod` | Tabelas `tb_metricas_treino`, `tb_saldo_previsto_prod` |
| **Amazon Athena** | Workgroup padrão + DB acima | Consulta SQL às métricas e predições |
| **AWS IAM** | Roles Glue / Lambda / SFN | Permissões S3, Glue, DynamoDB, logs |

---

## Arquitetura (treinamento)

```mermaid
flowchart TB
  subgraph trigger [Disparo]
    EB[EventBridge schedule]
    CLI[Scripts / AWS CLI / Console]
    EB -.->|opcional OFF em prod| SFN
    CLI --> SFN
  end

  subgraph orchestration [Orquestração]
    SFN[Step Functions saldo-previsto-sfn-prod]
    L1[Lambda check_new_data]
    L2[Lambda validate]
    L3[Lambda finalize]
    SFN --> L1
    L1 -->|has_new_data| L2
    L1 -->|sem dados| SKIP1[SkipNoNewData]
    L2 --> GLUE
    GLUE --> L3
    GLUE -->|ConcurrentRunsExceeded| SKIP2[SkipGlueBusy]
  end

  subgraph storage [Dados e artefatos]
    S3IN[(S3 raw + incoming)]
    S3OUT[(S3 processed + models)]
    DDB[(DynamoDB watermark)]
    L1 <--> DDB
    L3 --> DDB
  end

  subgraph training [Treino]
    GLUE[AWS Glue Job Python Shell]
    GLUE <--> S3IN
    GLUE --> S3OUT
  end

  subgraph analytics [Consulta]
    CAT[Glue Data Catalog]
    ATH[Athena]
    S3OUT --> CAT
    CAT --> ATH
  end

  CLI -->|start-job-run direto| GLUE
```

---

## Sequência: Step Functions → treino

```mermaid
sequenceDiagram
  participant T as Disparo CLI / EventBridge
  participant SFN as Step Functions
  participant L as Lambda
  participant DDB as DynamoDB
  participant S3 as S3
  participant G as Glue Job
  participant CAT as Glue Catalog

  T->>SFN: start-execution
  SFN->>SFN: AssignRunId run_id
  SFN->>L: check_new_data
  L->>S3: list incoming/ ETag
  L->>DDB: comparar watermark
  alt Sem dados novos
    L-->>SFN: has_new_data=false
    SFN-->>T: SkipNoNewData
  else Dados novos ou reconcile manual
    L-->>SFN: INCOMING_KEYS
    SFN->>L: validate
    L->>S3: validar dados_treino.csv
    SFN->>G: startJobRun.sync
    Note over G,S3: Ver etapas internas abaixo
    G->>S3: CSV atualizado + parquets + modelos
    G->>CAT: register_partitions
    SFN->>L: finalize
    L->>DDB: marcar arquivos processados
  end
```

**Disparo alternativo (sem SFN):** `aws glue start-job-run` ou `run_rafo044_experiment.py --reconcile` chama o Glue direto com `--INGEST_DAILY=false` e `--INCOMING_KEYS=[]`.

---

## Etapas internas do Glue (treino XGBoost)

```mermaid
flowchart LR
  subgraph ingest [1. Ingestão opcional]
    I1[Ler dados_treino.csv do S3]
    I2[Merge incoming/*.csv]
    I3[Gravar CSV atualizado no S3]
    I1 --> I2 --> I3
  end

  subgraph ml [2. Machine learning]
    M1[prepare_training_dataset saldo_alvo]
    M2[Preprocessor fit_transform]
    M3[Split temporal treino / val / teste]
    M4[treinar_modelo XGBoost]
    M5[Métricas RMSE WAPE R2 por segmento]
    M1 --> M2 --> M3 --> M4 --> M5
  end

  subgraph publish [3. Publicação]
    P1[maybe_promote_champion → S3 champion/]
    P2[metricas.json + feature_importance.json]
    P3[Parquet tb_metricas_treino]
    P4[Parquet tb_saldo_previsto_prod]
    P5[register_partitions Glue Catalog]
    P1 --> P2 --> P3 --> P4 --> P5
  end

  ingest --> ml --> publish
```

| Etapa | Saída principal |
|-------|-----------------|
| Ingestão | `s3://.../raw/saldo_previsto/dados_treino.csv` |
| Treino | `models/xgboost_saldo/metricas.json`, `history/{run_id}.json` |
| Champion | `models/xgboost_saldo/champion/model.ubj` (se RMSE ≥ 2% melhor) |
| Métricas run | `processed/tb_metricas_treino/run_date=.../run_id=.../` |
| Predições teste | `processed/tb_saldo_previsto_prod/ano=/mes=/segmento=/` |

---

## Onde cada serviço grava/lê

```mermaid
flowchart LR
  subgraph s3paths [S3 saldo-previsto-data-prod]
    R[raw/saldo_previsto/dados_treino.csv]
    IN[incoming/*.csv]
    SCR[scripts/glue_train.py + libs/app.zip]
    MOD[models/xgboost_saldo/]
    PROC[processed/tb_*]
  end

  Glue --> R
  Glue --> IN
  Glue --> MOD
  Glue --> PROC
  Lambda --> R
  Lambda --> IN
  Lambda --> DDB[(DynamoDB)]
  Athena --> PROC
```

---

## Consulta pós-treino

```mermaid
flowchart LR
  G[Glue conclui SUCCEEDED] --> P[Parquets em S3]
  P --> C[Glue Data Catalog]
  C --> A[Athena saldo_previsto_db_prod]
  A --> Q1[tb_metricas_treino]
  A --> Q2[tb_saldo_previsto_prod]
```

Queries: [`payloads/athena_queries.sql`](../payloads/athena_queries.sql) · Guia: [`ANALISE_METRICAS_ATHENA.md`](ANALISE_METRICAS_ATHENA.md)

---

## Referências

- Casos de uso e escala em produção real: [`USO_REAL_E_ESCALABILIDADE.md`](USO_REAL_E_ESCALABILIDADE.md)
- ASL do pipeline: [`infra/templates/stepfunctions/pipeline-ml.asl.json.tpl`](../infra/templates/stepfunctions/pipeline-ml.asl.json.tpl)
- Código do treino: [`glue_bundle/train_pipeline.py`](../glue_bundle/train_pipeline.py)
- Experimento local: [`scripts/run_rafo044_experiment.py`](../scripts/run_rafo044_experiment.py)
