project_name  = "sample-automation"
environment   = "hom"
workload_type = "pipeline"
aws_region    = "us-east-1"

enable_s3_buckets = true
enable_dynamodb   = true

enable_lambda        = true
enable_glue_job      = true
enable_stepfunctions = true

glue_job_role_arn = "arn:aws:iam::000000000000:role/sample-automation-glue-role-hom"
lambda_role_arn   = "arn:aws:iam::000000000000:role/sample-automation-lambda-role-hom"
sfn_role_arn      = "arn:aws:iam::000000000000:role/sample-automation-sfn-role-hom"

glue_script_location = "s3://sample-automation-hom-artifacts/scripts/main.py"
lambda_artifact_key  = "builds/handler.zip"
