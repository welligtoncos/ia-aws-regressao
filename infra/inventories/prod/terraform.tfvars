# XGBoost - previsão de saldo bancário (prod) + pipeline Step Functions

project_name  = "saldo-previsto"
environment   = "prod"
workload_type = "pipeline"
aws_region    = "us-east-1"

# Segurança prod (SSE-S3 sem KMS)
enable_glue_security_config = true

enable_s3_buckets     = false
s3_source_bucket_name = "saldo-previsto-data-prod"
s3_output_bucket_name = "saldo-previsto-data-prod"

enable_glue_job      = true
glue_job_name        = "saldo-previsto-glue-job-prod"
glue_job_role_arn    = "arn:aws:iam::303238378103:role/saldo-previsto-glue-role-prod"
glue_job_description = "Treino XGBoost - saldo bancário (prod)"
glue_script_location = "s3://saldo-previsto-data-prod/scripts/glue_train.py"
glue_command_type          = "pythonshell"
glue_python_shell_capacity = 1
glue_number_of_workers = 2
glue_worker_type       = "G.1X"

glue_job_default_arguments = {
  "--job-language"              = "python"
  "--extra-py-files"            = "s3://saldo-previsto-data-prod/libs/app.zip"
  "--additional-python-modules" = "xgboost==2.0.3,scikit-learn,pandas,pyarrow"
}

ml_input_key         = "raw/saldo_previsto/dados_treino.csv"
ml_output_database   = "saldo_previsto_db_prod"
ml_output_table      = "tb_saldo_previsto_prod"
ml_target_column     = "saldo_previsto"
ml_model_output_path = "models/xgboost_saldo/"
ml_mode              = "train"

xgboost_params = {
  n_estimators     = "300"
  max_depth        = "6"
  learning_rate    = "0.05"
  subsample        = "0.8"
  colsample_bytree = "0.8"
}

enable_glue_data_catalog = true

# Ingestão micro a cada 1 min + detecção de arquivos novos
ml_ingest_daily_simulated   = false
ml_ingest_mode              = "micro"
ml_incremental_step_minutes   = 2
ml_incremental_new_clients    = 10
ml_incremental_seed_clientes  = 5000
ml_incoming_prefix            = "incoming/"
ml_enable_check_new_data      = true
ml_metrics_table              = "tb_metricas_treino"
glue_max_concurrent_runs      = 1

# Pipeline: Lambda -> Glue -> Lambda
enable_lambda            = true
enable_stepfunctions     = true
enable_dynamodb          = true
sfn_use_pipeline_template = true

sfn_role_arn    = "arn:aws:iam::303238378103:role/saldo-previsto-sfn-role-prod"
lambda_role_arn = "arn:aws:iam::303238378103:role/saldo-previsto-lambda-role-prod"

lambda_artifact_bucket = "saldo-previsto-data-prod"
lambda_artifact_key      = "builds/handler.zip"

# EventBridge: dispara pipeline a cada 2 minutos (retreino; promoção exige RMSE >= 2% melhor)
enable_eventbridge_schedule     = true
eventbridge_schedule_expression = "rate(2 minutes)"
