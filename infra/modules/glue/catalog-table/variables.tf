variable "database_name" {
  description = "Nome do database no Glue Data Catalog (consultado no Athena)."
  type        = string
}

variable "table_name" {
  description = "Nome da tabela externa."
  type        = string
}

variable "s3_location" {
  description = "Location S3 da tabela (prefixo processed/)."
  type        = string
}

variable "tags" {
  description = "Tags AWS."
  type        = map(string)
  default     = {}
}
