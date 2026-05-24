output "glue_job_name" {
  description = "Nome do Glue Job."
  value       = aws_glue_job.this.name
}

output "glue_job_arn" {
  description = "ARN do Glue Job."
  value       = aws_glue_job.this.arn
}
