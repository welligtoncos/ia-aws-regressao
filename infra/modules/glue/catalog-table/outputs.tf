output "database_name" {
  value = aws_glue_catalog_database.this.name
}

output "table_name" {
  value = aws_glue_catalog_table.this.name
}

output "athena_query_table" {
  description = "Nome qualificado para SELECT no Athena."
  value       = "${aws_glue_catalog_database.this.name}.${aws_glue_catalog_table.this.name}"
}

output "s3_location" {
  value = var.s3_location
}
