output "glue_connection_name" {
  description = "Nome da Glue Connection."
  value       = aws_glue_connection.this.name
}

output "glue_connection_arn" {
  description = "ARN da Glue Connection."
  value       = aws_glue_connection.this.arn
}

output "glue_job_name" {
  description = "Nome do Glue Job."
  value       = aws_glue_job.this.name
}

output "glue_job_arn" {
  description = "ARN do Glue Job."
  value       = aws_glue_job.this.arn
}
