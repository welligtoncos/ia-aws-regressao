locals {
  name_prefix = var.project_name

  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    Workload    = var.workload_type
    ManagedBy   = "terraform"
  }

  is_pipeline        = contains(["pipeline", "automation"], var.workload_type)
  is_glue            = var.workload_type == "glue" || local.is_pipeline
  is_lambda          = var.workload_type == "lambda" || local.is_pipeline
  is_stepfunctions   = var.workload_type == "stepfunctions" || local.is_pipeline

  glue_crawler_name         = var.glue_crawler_name != "" ? var.glue_crawler_name : "${local.name_prefix}-glue-crawler-${var.environment}"
  glue_workflow_name        = var.glue_workflow_name != "" ? var.glue_workflow_name : "${local.name_prefix}-glue-workflow-${var.environment}"
  glue_job_name             = var.glue_job_name != "" ? var.glue_job_name : "${local.name_prefix}-glue-job-${var.environment}"
  glue_security_config_name = "${local.name_prefix}-glue-security-${var.environment}"

  lambda_function_name   = var.lambda_function_name != "" ? var.lambda_function_name : "${local.name_prefix}-lambda-${var.environment}"
  sfn_state_machine_name = var.sfn_state_machine_name != "" ? var.sfn_state_machine_name : "${local.name_prefix}-sfn-${var.environment}"
  dynamodb_table_name    = var.dynamodb_table_name != "" ? var.dynamodb_table_name : "${local.name_prefix}-results-${var.environment}"

  source_bucket_name   = var.enable_s3_buckets ? module.s3_buckets[0].bucket_names["source"] : coalesce(var.s3_source_bucket_name, var.glue_source_bucket)
  output_bucket_name   = var.enable_s3_buckets ? module.s3_buckets[0].bucket_names["output"] : coalesce(var.s3_output_bucket_name, var.glue_output_bucket)
  artifact_bucket_name = var.enable_s3_buckets ? module.s3_buckets[0].bucket_names["artifacts"] : var.lambda_artifact_bucket

  glue_job_arguments = merge(
    var.glue_job_default_arguments,
    {
      "--SOURCE_BUCKET"   = local.source_bucket_name
      "--OUTPUT_BUCKET"   = local.output_bucket_name
      "--DYNAMODB_TABLE"  = local.dynamodb_table_name
      "--TempDir"         = var.glue_temp_dir != "" ? var.glue_temp_dir : "s3://${local.output_bucket_name}/temp/"
    }
  )

  lambda_env = merge(
    var.lambda_environment_variables,
    {
      SOURCE_BUCKET  = local.source_bucket_name
      OUTPUT_BUCKET  = local.output_bucket_name
      DYNAMODB_TABLE = local.dynamodb_table_name
      PROJECT_NAME   = var.project_name
      ENVIRONMENT    = var.environment
    }
  )

  sfn_definition = var.sfn_definition != "" ? var.sfn_definition : (
    var.sfn_use_pipeline_template ? templatefile("${path.root}/templates/stepfunctions/pipeline.asl.json.tpl", {
      lambda_function_name = local.lambda_function_name
      glue_job_name        = local.glue_job_name
      dynamodb_table_name  = local.dynamodb_table_name
    }) : file("${path.root}/../workloads/stepfunctions/definitions/sample.asl.json")
  )
}
