variable "database_name" {
  type = string
}

variable "table_name" {
  type = string
}

variable "s3_location" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
