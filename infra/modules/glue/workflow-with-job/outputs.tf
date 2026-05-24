output "glue_workflow_name" {
  description = "Nome do Glue Workflow."
  value       = aws_glue_workflow.this.name
}

output "glue_workflow_arn" {
  description = "ARN do Glue Workflow."
  value       = aws_glue_workflow.this.arn
}

output "glue_trigger_name" {
  description = "Nome do Glue Trigger."
  value       = aws_glue_trigger.workflow_start.name
}

output "glue_job_name" {
  description = "Nome do Glue Job."
  value       = aws_glue_job.this.name
}

output "glue_job_arn" {
  description = "ARN do Glue Job."
  value       = aws_glue_job.this.arn
}
