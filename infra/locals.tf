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
      "--SOURCE_BUCKET"    = local.source_bucket_name
      "--OUTPUT_BUCKET"    = local.output_bucket_name
      "--DYNAMODB_TABLE"   = local.dynamodb_table_name
      "--TempDir"          = var.glue_temp_dir != "" ? var.glue_temp_dir : "s3://${local.output_bucket_name}/temp/"
      "--INPUT_BUCKET"     = local.source_bucket_name
      "--INPUT_KEY"        = var.ml_input_key
      "--OUTPUT_DATABASE"  = var.ml_output_database
      "--OUTPUT_TABLE"     = var.ml_output_table
      "--TARGET_COLUMN"    = var.ml_target_column
      "--MODE"             = var.ml_mode
      "--MODEL_OUTPUT_PATH" = var.ml_model_output_path
      "--XGBOOST_PARAMS"   = jsonencode(var.xgboost_params)
      "--INGEST_DAILY"              = var.ml_ingest_daily_simulated ? "true" : "false"
      "--INGEST_MODE"               = var.ml_ingest_mode
      "--INCREMENTAL_STEP_MINUTES" = tostring(var.ml_incremental_step_minutes)
      "--INCREMENTAL_NEW_CLIENTS"   = tostring(var.ml_incremental_new_clients)
      "--INCREMENTAL_SEED_CLIENTES" = tostring(var.ml_incremental_seed_clientes)
      "--METRICS_TABLE"             = var.ml_metrics_table
      "--METRICS_DATABASE"          = var.ml_output_database
    }
  )

  lambda_env = merge(
    var.lambda_environment_variables,
    {
      SOURCE_BUCKET       = local.source_bucket_name
      OUTPUT_BUCKET       = local.output_bucket_name
      DYNAMODB_TABLE      = local.dynamodb_table_name
      PROJECT_NAME        = var.project_name
      ENVIRONMENT         = var.environment
      INCOMING_PREFIX     = var.ml_incoming_prefix
      INGEST_SIMULATED    = var.ml_ingest_daily_simulated ? "true" : "false"
      INGEST_MODE         = var.ml_ingest_mode
      INGEST_STEP_MINUTES = tostring(var.ml_incremental_step_minutes)
    }
  )

  glue_catalog_s3_location = "s3://${local.output_bucket_name}/processed/${var.ml_output_table}/"
  glue_metrics_s3_location = "s3://${local.output_bucket_name}/processed/${var.ml_metrics_table}/"

  sfn_definition = var.sfn_definition != "" ? var.sfn_definition : (
    var.sfn_use_pipeline_template ? templatefile(
      var.ml_enable_check_new_data ? "${path.root}/templates/stepfunctions/pipeline-ml.asl.json.tpl" : "${path.root}/templates/stepfunctions/pipeline.asl.json.tpl",
      {
        lambda_function_name = local.lambda_function_name
        glue_job_name        = local.glue_job_name
        dynamodb_table_name  = local.dynamodb_table_name
      }
    ) : file("${path.root}/../workloads/stepfunctions/definitions/sample.asl.json")
  )
}
