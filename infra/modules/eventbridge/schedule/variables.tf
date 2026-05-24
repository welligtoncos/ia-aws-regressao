variable "rule_name" {
  description = "Nome da regra EventBridge."
  type        = string
}

variable "schedule_expression" {
  description = "Expressão cron ou rate."
  type        = string
}

variable "target_arn" {
  description = "ARN alvo (Step Functions ou Lambda)."
  type        = string
}

variable "target_role_arn" {
  description = "IAM Role para EventBridge invocar o alvo."
  type        = string
}

variable "input" {
  description = "Payload JSON enviado ao alvo."
  type        = string
  default     = "{}"
}

variable "tags" {
  description = "Tags da regra."
  type        = map(string)
}
