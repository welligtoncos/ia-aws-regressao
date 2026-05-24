provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.common_tags
  }
}

# ==============================================================================
# Storage compartilhado (pipeline / automation)
# ==============================================================================

module "s3_buckets" {
  source = "./modules/s3/buckets"
  count  = var.enable_s3_buckets ? 1 : 0

  project_name  = var.project_name
  environment   = var.environment
  force_destroy = var.s3_force_destroy
  tags          = local.common_tags
}

module "dynamodb_results" {
  source = "./modules/dynamodb/table"
  count  = var.enable_dynamodb ? 1 : 0

  table_name    = local.dynamodb_table_name
  hash_key      = var.dynamodb_hash_key
  range_key     = var.dynamodb_range_key
  billing_mode  = var.dynamodb_billing_mode
  tags          = local.common_tags
}

# ==============================================================================
# AWS Glue
# ==============================================================================

resource "aws_glue_security_configuration" "this" {
  count = local.is_glue && var.enable_glue_security_config ? 1 : 0

  name = local.glue_security_config_name

  encryption_configuration {
    cloudwatch_encryption {
      cloudwatch_encryption_mode = var.glue_kms_key_arn != "" ? "SSE-KMS" : "DISABLED"
      kms_key_arn                = var.glue_kms_key_arn != "" ? var.glue_kms_key_arn : null
    }

    job_bookmarks_encryption {
      job_bookmarks_encryption_mode = var.glue_kms_key_arn != "" ? "CSE-KMS" : "DISABLED"
      kms_key_arn                   = var.glue_kms_key_arn != "" ? var.glue_kms_key_arn : null
    }

    s3_encryption {
      s3_encryption_mode = var.glue_kms_key_arn != "" ? "SSE-KMS" : "SSE-S3"
      kms_key_arn        = var.glue_kms_key_arn != "" ? var.glue_kms_key_arn : null
    }
  }
}

module "glue_standalone_job" {
  source = "./modules/glue/job"
  count  = var.enable_glue_job && (
    local.is_pipeline ||
    (var.workload_type == "glue" && !var.enable_glue_connection && !var.enable_glue_crawler && !var.enable_glue_workflow)
  ) ? 1 : 0

  project_name               = var.project_name
  environment                = var.environment
  glue_job_name              = local.glue_job_name
  glue_job_role_arn          = var.glue_job_role_arn
  glue_job_description       = var.glue_job_description
  glue_job_default_arguments = local.glue_job_arguments
  glue_script_location       = var.glue_script_location
  glue_command_type          = var.glue_command_type
  python_shell_capacity      = var.glue_python_shell_capacity
  number_of_workers          = var.glue_number_of_workers
  worker_type                = var.glue_worker_type
  max_concurrent_runs        = var.glue_max_concurrent_runs
  tags                       = local.common_tags
}

module "glue_job_with_connection" {
  source = "./modules/glue/job-with-connection"
  count  = var.workload_type == "glue" && var.enable_glue_connection && var.enable_glue_job && !var.enable_glue_workflow ? 1 : 0

  project_name               = var.project_name
  environment                = var.environment
  glue_connection_name       = var.glue_connection_name
  glue_connection_type       = var.glue_connection_type
  glue_connection_properties = var.glue_connection_properties
  glue_job_name              = local.glue_job_name
  glue_job_role_arn          = var.glue_job_role_arn
  glue_job_description       = var.glue_job_description
  glue_job_default_arguments = local.glue_job_arguments
  glue_script_location       = var.glue_script_location
  glue_temp_dir              = var.glue_temp_dir
  glue_source_bucket         = local.source_bucket_name
  glue_output_bucket         = local.output_bucket_name
  custom_subnet_ids          = var.custom_subnet_ids
  custom_sg_ids              = var.custom_sg_ids
  disable_sg_creation        = var.disable_sg_creation
  glue_security_group        = var.glue_security_group
  tags                       = local.common_tags
}

module "glue_crawler_and_job" {
  source = "./modules/glue/crawler-with-job"
  count  = var.workload_type == "glue" && var.enable_glue_crawler && var.enable_glue_job && !var.enable_glue_connection && !var.enable_glue_workflow ? 1 : 0

  project_name               = var.project_name
  environment                = var.environment
  glue_crawler_name          = local.glue_crawler_name
  glue_crawler_database      = var.glue_crawler_database
  glue_crawler_s3_target     = var.glue_crawler_s3_target
  glue_crawler_role_arn      = var.glue_crawler_role_arn
  glue_job_name              = local.glue_job_name
  glue_job_role_arn          = var.glue_job_role_arn
  glue_job_description       = var.glue_job_description
  glue_job_default_arguments = local.glue_job_arguments
  glue_script_location       = var.glue_script_location
  glue_temp_dir              = var.glue_temp_dir
  glue_source_bucket         = local.source_bucket_name
  glue_output_bucket         = local.output_bucket_name
  tags                       = local.common_tags
}

module "glue_workflow_with_job" {
  source = "./modules/glue/workflow-with-job"
  count  = var.workload_type == "glue" && var.enable_glue_workflow && var.enable_glue_job ? 1 : 0

  project_name               = var.project_name
  environment                = var.environment
  glue_workflow_name         = local.glue_workflow_name
  glue_job_name              = local.glue_job_name
  glue_job_role_arn          = var.glue_job_role_arn
  glue_job_description       = var.glue_job_description
  glue_job_default_arguments = local.glue_job_arguments
  glue_script_location       = var.glue_script_location
  glue_temp_dir              = var.glue_temp_dir
  glue_source_bucket         = local.source_bucket_name
  glue_output_bucket         = local.output_bucket_name
  tags                       = local.common_tags
}

# ==============================================================================
# Glue Data Catalog (Athena)
# ==============================================================================

module "glue_data_catalog" {
  source = "./modules/glue/catalog-table"
  count  = var.enable_glue_data_catalog && var.ml_output_database != "" && var.ml_output_table != "" ? 1 : 0

  database_name = var.ml_output_database
  table_name    = var.ml_output_table
  s3_location   = local.glue_catalog_s3_location
  tags          = local.common_tags
}

module "glue_metrics_catalog" {
  source = "./modules/glue/catalog-metrics"
  count  = var.enable_glue_data_catalog && var.ml_output_database != "" && var.ml_metrics_table != "" ? 1 : 0

  database_name = var.ml_output_database
  table_name    = var.ml_metrics_table
  s3_location   = local.glue_metrics_s3_location
  tags          = local.common_tags

  depends_on = [module.glue_data_catalog]
}

# ==============================================================================
# AWS Lambda
# ==============================================================================

module "lambda_function" {
  source = "./modules/lambda/function"
  count  = local.is_lambda && var.enable_lambda ? 1 : 0

  project_name          = var.project_name
  environment           = var.environment
  function_name         = local.lambda_function_name
  role_arn              = var.lambda_role_arn
  runtime               = var.lambda_runtime
  handler               = var.lambda_handler
  artifact_bucket       = local.artifact_bucket_name
  artifact_key          = var.lambda_artifact_key
  description           = var.lambda_description
  timeout               = var.lambda_timeout
  memory_size           = var.lambda_memory_size
  environment_variables = local.lambda_env
  tags                  = local.common_tags
}

# ==============================================================================
# AWS Step Functions
# ==============================================================================

module "stepfunctions" {
  source = "./modules/stepfunctions/state-machine"
  count  = local.is_stepfunctions && var.enable_stepfunctions ? 1 : 0

  project_name       = var.project_name
  environment        = var.environment
  state_machine_name = local.sfn_state_machine_name
  role_arn           = var.sfn_role_arn
  definition         = local.sfn_definition
  state_machine_type = var.sfn_type
  tags               = local.common_tags
}

# ==============================================================================
# EventBridge (agendamento opcional)
# ==============================================================================

module "eventbridge_schedule" {
  source = "./modules/eventbridge/schedule"
  count  = var.enable_eventbridge_schedule && local.is_stepfunctions && var.enable_stepfunctions ? 1 : 0

  rule_name           = "${var.project_name}-schedule-${var.environment}"
  schedule_expression = var.eventbridge_schedule_expression
  target_arn          = var.eventbridge_target_arn != "" ? var.eventbridge_target_arn : module.stepfunctions[0].state_machine_arn
  target_role_arn     = var.sfn_role_arn
  input = jsonencode({
    run_id        = "scheduled"
    source_prefix = "raw/"
  })
  tags = local.common_tags
}
