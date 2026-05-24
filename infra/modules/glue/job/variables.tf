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

variable "glue_command_type" {
  description = "Tipo do comando Glue: glueetl (Spark) ou pythonshell (ML/pandas)."
  type        = string
  default     = "glueetl"
}

variable "python_shell_capacity" {
  description = "DPUs para job Python Shell."
  type        = number
  default     = 1
}

variable "number_of_workers" {
  description = "Número de workers Glue."
  type        = number
  default     = 2
}

variable "worker_type" {
  description = "Tipo de worker Glue."
  type        = string
  default     = "G.1X"
}

variable "tags" {
  description = "Tags dos recursos."
  type        = map(string)
}
