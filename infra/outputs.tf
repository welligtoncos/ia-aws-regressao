output "workload_type" {
  description = "Tipo de workload provisionado."
  value       = var.workload_type
}

output "project_name" {
  description = "Nome do projeto."
  value       = var.project_name
}

output "s3_bucket_names" {
  description = "Buckets S3 (quando criados)."
  value       = try(module.s3_buckets[0].bucket_names, null)
}

output "dynamodb_table_name" {
  description = "Tabela DynamoDB de resultados."
  value       = try(module.dynamodb_results[0].table_name, local.dynamodb_table_name)
}

output "glue_job_arn" {
  description = "ARN do Glue Job (quando provisionado)."
  value       = try(
    module.glue_standalone_job[0].glue_job_arn,
    module.glue_job_with_connection[0].glue_job_arn,
    module.glue_crawler_and_job[0].glue_job_arn,
    module.glue_workflow_with_job[0].glue_job_arn,
    null
  )
}

output "glue_crawler_arn" {
  description = "ARN do Glue Crawler (quando provisionado)."
  value       = try(module.glue_crawler_and_job[0].glue_crawler_arn, null)
}

output "lambda_function_arn" {
  description = "ARN da função Lambda (quando provisionada)."
  value       = try(module.lambda_function[0].function_arn, null)
}

output "stepfunctions_arn" {
  description = "ARN da state machine (quando provisionada)."
  value       = try(module.stepfunctions[0].state_machine_arn, null)
}

output "eventbridge_rule_arn" {
  description = "ARN da regra EventBridge (quando provisionada)."
  value       = try(module.eventbridge_schedule[0].rule_arn, null)
}

output "athena_database" {
  description = "Database Glue Catalog consultável no Athena."
  value       = try(module.glue_data_catalog[0].database_name, var.ml_output_database != "" ? var.ml_output_database : null)
}

output "athena_table" {
  description = "Tabela qualificada no Athena (database.tabela)."
  value       = try(module.glue_data_catalog[0].athena_query_table, null)
}

output "athena_s3_location" {
  description = "Location S3 dos Parquet de resultado."
  value       = try(module.glue_data_catalog[0].s3_location, null)
}

output "athena_metrics_table" {
  description = "Tabela Athena com evolução de métricas por run."
  value       = try(module.glue_metrics_catalog[0].athena_query_table, null)
}
