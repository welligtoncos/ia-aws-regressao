output "table_name" {
  value = aws_glue_catalog_table.this.name
}

output "athena_query_table" {
  value = "${var.database_name}.${aws_glue_catalog_table.this.name}"
}
