variable "project_name" {
  description = "Nome do projeto."
  type        = string
}

variable "environment" {
  description = "Ambiente de deploy."
  type        = string
}

variable "function_name" {
  description = "Nome da função Lambda."
  type        = string
}

variable "role_arn" {
  description = "ARN da IAM Role da Lambda."
  type        = string
}

variable "runtime" {
  description = "Runtime da Lambda."
  type        = string
}

variable "handler" {
  description = "Handler da Lambda."
  type        = string
}

variable "artifact_bucket" {
  description = "Bucket S3 do artefato."
  type        = string
}

variable "artifact_key" {
  description = "Chave S3 do artefato."
  type        = string
}

variable "description" {
  description = "Descrição da função."
  type        = string
}

variable "timeout" {
  description = "Timeout em segundos."
  type        = number
}

variable "memory_size" {
  description = "Memória em MB."
  type        = number
}

variable "environment_variables" {
  description = "Variáveis de ambiente."
  type        = map(string)
}

variable "tags" {
  description = "Tags dos recursos."
  type        = map(string)
}
