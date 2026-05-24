variable "project_name" {
  description = "Nome do projeto."
  type        = string
}

variable "environment" {
  description = "Ambiente de deploy."
  type        = string
}

variable "glue_connection_name" {
  description = "Nome da Glue Connection."
  type        = string
}

variable "glue_connection_type" {
  description = "Tipo da Glue Connection."
  type        = string
}

variable "glue_connection_properties" {
  description = "Propriedades da Glue Connection."
  type        = map(string)
}

variable "glue_job_name" {
  description = "Nome do Glue Job."
  type        = string
}

variable "glue_job_role_arn" {
  description = "ARN da IAM Role do Glue Job."
  type        = string
}

variable "glue_job_description" {
  description = "Descrição do Glue Job."
  type        = string
}

variable "glue_job_default_arguments" {
  description = "Argumentos padrão do Glue Job."
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
  description = "Bucket S3 de origem."
  type        = string
}

variable "glue_output_bucket" {
  description = "Bucket S3 de saída."
  type        = string
}

variable "custom_subnet_ids" {
  description = "Subnet IDs."
  type        = list(string)
}

variable "custom_sg_ids" {
  description = "Security group IDs."
  type        = list(string)
}

variable "disable_sg_creation" {
  description = "Desabilita criação de security group."
  type        = bool
}

variable "glue_security_group" {
  description = "Identificador do security group."
  type        = string
}

variable "tags" {
  description = "Tags dos recursos."
  type        = map(string)
}
