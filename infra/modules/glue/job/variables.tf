variable "project_name" {
  description = "Nome do projeto."
  type        = string
}

variable "environment" {
  description = "Ambiente de deploy."
  type        = string
}

variable "glue_job_name" {
  description = "Nome do Glue Job."
  type        = string
}

variable "glue_job_role_arn" {
  description = "ARN da IAM Role do job."
  type        = string
}

variable "glue_job_description" {
  description = "Descrição do job."
  type        = string
}

variable "glue_job_default_arguments" {
  description = "Argumentos do job."
  type        = map(string)
}

variable "glue_script_location" {
  description = "URI S3 do script."
  type        = string
}

variable "tags" {
  description = "Tags dos recursos."
  type        = map(string)
}
