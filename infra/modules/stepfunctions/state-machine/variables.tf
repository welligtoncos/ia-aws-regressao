variable "project_name" {
  description = "Nome do projeto."
  type        = string
}

variable "environment" {
  description = "Ambiente de deploy."
  type        = string
}

variable "state_machine_name" {
  description = "Nome da state machine."
  type        = string
}

variable "role_arn" {
  description = "ARN da IAM Role do Step Functions."
  type        = string
}

variable "definition" {
  description = "Definição ASL da state machine (JSON)."
  type        = string
}

variable "state_machine_type" {
  description = "Tipo: STANDARD ou EXPRESS."
  type        = string
}

variable "tags" {
  description = "Tags dos recursos."
  type        = map(string)
}
