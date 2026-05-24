resource "aws_glue_catalog_database" "this" {
  name = var.database_name

  tags = var.tags
}

resource "aws_glue_catalog_table" "this" {
  name          = var.table_name
  database_name = aws_glue_catalog_database.this.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    EXTERNAL              = "TRUE"
    "parquet.compression" = "SNAPPY"
  }

  storage_descriptor {
    location      = var.s3_location
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      name                  = "ParquetHiveSerDe"
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "cliente_id"
      type = "string"
    }
    columns {
      name = "data_referencia"
      type = "string"
    }
    columns {
      name = "saldo_predito"
      type = "double"
    }
    columns {
      name = "saldo_realizado"
      type = "double"
    }
    columns {
      name = "uf"
      type = "string"
    }
    columns {
      name = "dt_processamento"
      type = "string"
    }
    columns {
      name = "modelo_versao"
      type = "string"
    }
    columns {
      name = "run_id"
      type = "string"
    }
    columns {
      name = "erro_absoluto"
      type = "double"
    }
    columns {
      name = "erro_percentual"
      type = "double"
    }
  }

  partition_keys {
    name = "ano"
    type = "int"
  }
  partition_keys {
    name = "mes"
    type = "int"
  }
  partition_keys {
    name = "segmento"
    type = "string"
  }
}
