variable "table_name" {
  description = "Nome da tabela DynamoDB."
  type        = string
}

variable "hash_key" {
  description = "Chave de partição."
  type        = string
}

variable "range_key" {
  description = "Chave de ordenação opcional."
  type        = string
  default     = ""
}

variable "billing_mode" {
  description = "Modo de cobrança."
  type        = string
}

variable "tags" {
  description = "Tags do recurso."
  type        = map(string)
}
