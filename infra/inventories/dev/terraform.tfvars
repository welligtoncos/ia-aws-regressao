# Pipeline completo: S3 -> Lambda -> Glue -> DynamoDB (via Step Functions)

project_name  = "sample-automation"
environment   = "dev"
workload_type = "pipeline"
aws_region    = "us-east-1"

# Storage
enable_s3_buckets = true
enable_dynamodb   = true
dynamodb_hash_key = "run_id"

# Compute
enable_lambda        = true
enable_glue_job      = true
enable_stepfunctions = true
sfn_use_pipeline_template = true

# IAM roles (substituir pelos ARNs reais)
glue_job_role_arn = "arn:aws:iam::000000000000:role/sample-automation-glue-role-dev"
lambda_role_arn   = "arn:aws:iam::000000000000:role/sample-automation-lambda-role-dev"
sfn_role_arn      = "arn:aws:iam::000000000000:role/sample-automation-sfn-role-dev"

# Artefatos
glue_script_location = "s3://sample-automation-dev-artifacts/scripts/main.py"
lambda_artifact_key  = "builds/handler.zip"

# Agendamento opcional
enable_eventbridge_schedule     = false
eventbridge_schedule_expression = "cron(0 6 * * ? *)"
