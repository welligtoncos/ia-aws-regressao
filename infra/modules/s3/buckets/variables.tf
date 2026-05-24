variable "project_name" {
  description = "Nome do projeto."
  type        = string
}

variable "environment" {
  description = "Ambiente de deploy."
  type        = string
}

variable "force_destroy" {
  description = "Permite destruir bucket com objetos."
  type        = bool
}

variable "tags" {
  description = "Tags dos recursos."
  type        = map(string)
}
