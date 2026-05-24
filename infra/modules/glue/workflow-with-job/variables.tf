variable "project_name" {
  description = "Nome do projeto."
  type        = string
}

variable "environment" {
  description = "Ambiente de deploy."
  type        = string
}

variable "glue_workflow_name" {
  description = "Nome do Glue Workflow."
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
  description = "Descrição do Glue Job."
  type        = string
}

variable "glue_job_default_arguments" {
  description = "Argumentos padrão do job."
  type        = map(string)
}

variable "glue_script_location" {
  description = "URI S3 do script."
  type        = string
}

variable "glue_temp_dir" {
  description = "Diretório temporário S3."
  type        = string
}

variable "glue_source_bucket" {
  description = "Bucket de origem."
  type        = string
}

variable "glue_output_bucket" {
  description = "Bucket de saída."
  type        = string
}

variable "tags" {
  description = "Tags dos recursos."
  type        = map(string)
}
