# XGBoost - previsão de saldo bancário (dev)

project_name  = "saldo-previsto"
environment   = "dev"
workload_type = "glue"
aws_region    = "us-east-1"

# Storage
enable_s3_buckets      = false
s3_source_bucket_name  = "sample-data-dev"
s3_output_bucket_name  = "sample-data-dev"

# Glue Job ML
enable_glue_job      = true
glue_job_name        = "saldo-previsto-glue-job-dev"
glue_job_role_arn    = "arn:aws:iam::000000000000:role/saldo-previsto-glue-role-dev"
glue_job_description = "Treino XGBoost - previsão de saldo bancário"
glue_script_location = "s3://sample-data-dev/scripts/glue_train.py"
glue_number_of_workers = 2
glue_worker_type       = "G.1X"

glue_job_default_arguments = {
  "--job-language"              = "python"
  "--extra-py-files"            = "s3://sample-data-dev/libs/app.zip"
  "--additional-python-modules" = "xgboost==2.0.3,scikit-learn,pandas,pyarrow"
}

# ML
ml_input_key          = "raw/saldo_previsto/dados_treino.csv"
ml_output_database    = "sample_db_dev"
ml_output_table       = "tb_saldo_previsto_dev"
ml_target_column      = "saldo_previsto"
ml_model_output_path  = "models/xgboost_saldo/"
ml_mode               = "train"

xgboost_params = {
  n_estimators     = "300"
  max_depth        = "6"
  learning_rate    = "0.05"
  subsample        = "0.8"
  colsample_bytree = "0.8"
}

# Demais serviços desligados neste exemplo
enable_lambda        = false
enable_stepfunctions = false
enable_dynamodb      = false
