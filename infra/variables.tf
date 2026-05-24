# ------------------------------------------------------------------------------
# Comuns
# ------------------------------------------------------------------------------

variable "project_name" {
  description = "Nome do projeto usado em tags e nomenclatura de recursos."
  type        = string
}

variable "environment" {
  description = "Ambiente de deploy (dev, hom, prod)."
  type        = string
}

variable "workload_type" {
  description = "Modo do template: glue, lambda, stepfunctions, pipeline ou automation."
  type        = string

  validation {
    condition     = contains(["glue", "lambda", "stepfunctions", "pipeline", "automation"], var.workload_type)
    error_message = "workload_type deve ser glue, lambda, stepfunctions, pipeline ou automation."
  }
}

variable "aws_region" {
  description = "Região AWS para provisionamento dos recursos."
  type        = string
  default     = "us-east-1"
}

# ------------------------------------------------------------------------------
# S3
# ------------------------------------------------------------------------------

variable "enable_s3_buckets" {
  description = "Cria buckets S3 gerenciados (source, output, artifacts)."
  type        = bool
  default     = false
}

variable "s3_source_bucket_name" {
  description = "Nome do bucket S3 de entrada (quando enable_s3_buckets = false)."
  type        = string
  default     = ""
}

variable "s3_output_bucket_name" {
  description = "Nome do bucket S3 de saída (quando enable_s3_buckets = false)."
  type        = string
  default     = ""
}

variable "s3_force_destroy" {
  description = "Permite destruir buckets S3 mesmo com objetos (útil em dev)."
  type        = bool
  default     = true
}

# ------------------------------------------------------------------------------
# DynamoDB
# ------------------------------------------------------------------------------

variable "enable_dynamodb" {
  description = "Cria tabela DynamoDB para resultados de automação."
  type        = bool
  default     = false
}

variable "dynamodb_table_name" {
  description = "Nome da tabela DynamoDB."
  type        = string
  default     = ""
}

variable "dynamodb_hash_key" {
  description = "Chave de partição (hash key) da tabela DynamoDB."
  type        = string
  default     = "run_id"
}

variable "dynamodb_range_key" {
  description = "Chave de ordenação (range key) opcional da tabela DynamoDB."
  type        = string
  default     = ""
}

variable "dynamodb_billing_mode" {
  description = "Modo de cobrança DynamoDB: PAY_PER_REQUEST ou PROVISIONED."
  type        = string
  default     = "PAY_PER_REQUEST"
}

# ------------------------------------------------------------------------------
# EventBridge (agendamento)
# ------------------------------------------------------------------------------

variable "enable_eventbridge_schedule" {
  description = "Habilita regra EventBridge para disparar a automação em cron."
  type        = bool
  default     = false
}

variable "eventbridge_schedule_expression" {
  description = "Expressão cron/rate do EventBridge (ex.: cron(0 6 * * ? *))."
  type        = string
  default     = "rate(1 day)"
}

variable "eventbridge_target_arn" {
  description = "ARN alvo do EventBridge (SFN ou Lambda). Vazio = usa Step Functions do stack."
  type        = string
  default     = ""
}

# ------------------------------------------------------------------------------
# AWS Glue
# ------------------------------------------------------------------------------

variable "enable_glue_security_config" {
  description = "Habilita configuração de segurança do AWS Glue."
  type        = bool
  default     = false
}

variable "glue_kms_key_arn" {
  description = "ARN da chave KMS para criptografia Glue (SSE-KMS). Vazio = usa SSE-S3 / modos sem KMS."
  type        = string
  default     = ""
}

variable "glue_security_group" {
  description = "Identificador do security group para Glue Connection."
  type        = string
  default     = "glue-sg"
}

variable "enable_glue_connection" {
  description = "Habilita Glue Connection com job (modo glue isolado)."
  type        = bool
  default     = false
}

variable "glue_connection_name" {
  description = "Nome da Glue Connection."
  type        = string
  default     = ""
}

variable "glue_connection_type" {
  description = "Tipo da Glue Connection (JDBC, NETWORK, etc.)."
  type        = string
  default     = "NETWORK"
}

variable "glue_connection_properties" {
  description = "Propriedades da Glue Connection."
  type        = map(string)
  default     = {}
}

variable "disable_sg_creation" {
  description = "Quando true, usa security groups customizados em vez de criar um novo."
  type        = bool
  default     = true
}

variable "custom_sg_ids" {
  description = "Security group IDs para Glue Connection."
  type        = list(string)
  default     = []
}

variable "custom_subnet_ids" {
  description = "Subnet IDs para Glue Connection."
  type        = list(string)
  default     = []
}

variable "enable_glue_job" {
  description = "Habilita AWS Glue Job."
  type        = bool
  default     = false
}

variable "glue_job_name" {
  description = "Nome do Glue Job."
  type        = string
  default     = ""
}

variable "glue_source_bucket" {
  description = "Bucket S3 de origem (legado; preferir s3_source_bucket_name)."
  type        = string
  default     = ""
}

variable "glue_output_bucket" {
  description = "Bucket S3 de saída (legado; preferir s3_output_bucket_name)."
  type        = string
  default     = ""
}

variable "glue_job_role_arn" {
  description = "ARN da IAM Role do Glue Job."
  type        = string
  default     = ""
}

variable "glue_job_description" {
  description = "Descrição do Glue Job."
  type        = string
  default     = ""
}

variable "glue_job_default_arguments" {
  description = "Argumentos padrão do Glue Job."
  type        = map(string)
  default = {
    "--extra-py-files" = ""
    "--job-language"   = "python"
    "--extra-py-path"  = ""
  }
}

variable "enable_glue_crawler" {
  description = "Habilita Glue Crawler (modo glue isolado)."
  type        = bool
  default     = false
}

variable "glue_crawler_name" {
  description = "Nome do Glue Crawler."
  type        = string
  default     = ""
}

variable "glue_crawler_database" {
  description = "Database do Glue Data Catalog."
  type        = string
  default     = ""
}

variable "glue_crawler_s3_target" {
  description = "Path S3 alvo do crawler."
  type        = string
  default     = ""
}

variable "glue_crawler_role_arn" {
  description = "ARN da IAM Role do Glue Crawler."
  type        = string
  default     = ""
}

variable "enable_glue_workflow" {
  description = "Habilita Glue Workflow (modo glue isolado)."
  type        = bool
  default     = false
}

variable "glue_workflow_name" {
  description = "Nome do Glue Workflow."
  type        = string
  default     = ""
}

variable "glue_script_location" {
  description = "URI S3 do script do Glue Job."
  type        = string
  default     = ""
}

variable "glue_temp_dir" {
  description = "Diretório temporário S3 do Glue Job."
  type        = string
  default     = ""
}

# ------------------------------------------------------------------------------
# AWS Lambda
# ------------------------------------------------------------------------------

variable "enable_lambda" {
  description = "Habilita função Lambda."
  type        = bool
  default     = false
}

variable "lambda_function_name" {
  description = "Nome da função Lambda."
  type        = string
  default     = ""
}

variable "lambda_role_arn" {
  description = "ARN da IAM Role da Lambda."
  type        = string
  default     = ""
}

variable "lambda_runtime" {
  description = "Runtime da Lambda (ex.: python3.11)."
  type        = string
  default     = "python3.11"
}

variable "lambda_handler" {
  description = "Handler da Lambda."
  type        = string
  default     = "handler.lambda_handler"
}

variable "lambda_artifact_bucket" {
  description = "Bucket S3 do pacote de deploy da Lambda."
  type        = string
  default     = ""
}

variable "lambda_artifact_key" {
  description = "Chave S3 do pacote de deploy da Lambda."
  type        = string
  default     = "builds/handler.zip"
}

variable "lambda_description" {
  description = "Descrição da função Lambda."
  type        = string
  default     = ""
}

variable "lambda_timeout" {
  description = "Timeout da Lambda em segundos."
  type        = number
  default     = 60
}

variable "lambda_memory_size" {
  description = "Memória da Lambda em MB."
  type        = number
  default     = 256
}

variable "lambda_environment_variables" {
  description = "Variáveis de ambiente adicionais da Lambda."
  type        = map(string)
  default     = {}
}

# ------------------------------------------------------------------------------
# AWS Step Functions
# ------------------------------------------------------------------------------

variable "enable_stepfunctions" {
  description = "Habilita state machine do Step Functions."
  type        = bool
  default     = false
}

variable "sfn_state_machine_name" {
  description = "Nome da state machine."
  type        = string
  default     = ""
}

variable "sfn_role_arn" {
  description = "ARN da IAM Role do Step Functions."
  type        = string
  default     = ""
}

variable "sfn_definition" {
  description = "Definição ASL customizada. Vazio = usa template de pipeline se sfn_use_pipeline_template = true."
  type        = string
  default     = ""
}

variable "sfn_use_pipeline_template" {
  description = "Usa template ASL padrão Lambda -> Glue -> persistência."
  type        = bool
  default     = true
}

variable "sfn_type" {
  description = "Tipo da state machine: STANDARD ou EXPRESS."
  type        = string
  default     = "STANDARD"
}

# ------------------------------------------------------------------------------
# ML / XGBoost (previsão de saldo)
# ------------------------------------------------------------------------------

variable "ml_input_key" {
  description = "Chave S3 do CSV de treino."
  type        = string
  default     = ""
}

variable "ml_output_database" {
  description = "Database Glue Catalog de saída."
  type        = string
  default     = ""
}

variable "ml_output_table" {
  description = "Tabela Glue Catalog de saída."
  type        = string
  default     = ""
}

variable "enable_glue_data_catalog" {
  description = "Cria database/tabela no Glue Data Catalog para consulta no Athena."
  type        = bool
  default     = false
}

variable "ml_metrics_table" {
  description = "Tabela Athena com histórico de métricas por run."
  type        = string
  default     = "tb_metricas_treino"
}

variable "ml_ingest_daily_simulated" {
  description = "Append diário de dados simulados antes do treino (Glue)."
  type        = bool
  default     = false
}

variable "ml_incremental_new_clients" {
  description = "Novos clientes simulados por dia de ingestão."
  type        = number
  default     = 10
}

variable "ml_incremental_seed_clientes" {
  description = "Clientes no bootstrap quando CSV ainda não existe."
  type        = number
  default     = 5000
}

variable "ml_ingest_mode" {
  description = "Modo de ingestão simulada: daily ou micro."
  type        = string
  default     = "daily"
}

variable "ml_incremental_step_minutes" {
  description = "Intervalo em minutos entre lotes no modo micro."
  type        = number
  default     = 10
}

variable "ml_incoming_prefix" {
  description = "Prefixo S3 para CSVs externos (incoming/)."
  type        = string
  default     = "incoming/"
}

variable "ml_enable_check_new_data" {
  description = "Step Functions verifica dados novos antes do treino."
  type        = bool
  default     = false
}

variable "glue_max_concurrent_runs" {
  description = "Máximo de execuções simultâneas do Glue Job."
  type        = number
  default     = 1
}

variable "ml_target_column" {
  description = "Coluna alvo do modelo."
  type        = string
  default     = "saldo_previsto"
}

variable "ml_model_output_path" {
  description = "Prefixo S3 para modelos e métricas."
  type        = string
  default     = "models/xgboost_saldo/"
}

variable "ml_mode" {
  description = "Modo de execução: train ou predict."
  type        = string
  default     = "train"
}

variable "glue_number_of_workers" {
  description = "Número de workers do Glue Job (modo glueetl)."
  type        = number
  default     = 2
}

variable "glue_command_type" {
  description = "Tipo do Glue Job: glueetl ou pythonshell."
  type        = string
  default     = "glueetl"
}

variable "glue_python_shell_capacity" {
  description = "DPUs para Glue Python Shell."
  type        = number
  default     = 1
}

variable "glue_worker_type" {
  description = "Tipo de worker Glue (G.1X, G.2X, etc.)."
  type        = string
  default     = "G.1X"
}

variable "xgboost_params" {
  description = "Parâmetros XGBoost passados ao Glue Job."
  type        = map(string)
  default     = {}
}
