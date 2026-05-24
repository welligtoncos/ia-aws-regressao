project_name  = "sample-automation"
environment   = "prod"
workload_type = "pipeline"
aws_region    = "us-east-1"

enable_s3_buckets           = true
enable_dynamodb             = true
enable_glue_security_config = true

enable_lambda        = true
enable_glue_job      = true
enable_stepfunctions = true

enable_eventbridge_schedule     = true
eventbridge_schedule_expression = "cron(0 6 * * ? *)"

glue_job_role_arn = "arn:aws:iam::000000000000:role/sample-automation-glue-role-prod"
lambda_role_arn   = "arn:aws:iam::000000000000:role/sample-automation-lambda-role-prod"
sfn_role_arn      = "arn:aws:iam::000000000000:role/sample-automation-sfn-role-prod"

glue_script_location = "s3://sample-automation-prod-artifacts/scripts/main.py"
lambda_artifact_key  = "builds/handler.zip"
