output "glue_crawler_name" {
  description = "Nome do Glue Crawler."
  value       = aws_glue_crawler.this.name
}

output "glue_crawler_arn" {
  description = "ARN do Glue Crawler."
  value       = aws_glue_crawler.this.arn
}

output "glue_job_name" {
  description = "Nome do Glue Job."
  value       = aws_glue_job.this.name
}

output "glue_job_arn" {
  description = "ARN do Glue Job."
  value       = aws_glue_job.this.arn
}
