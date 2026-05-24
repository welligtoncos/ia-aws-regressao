resource "aws_glue_catalog_table" "this" {
  name          = var.table_name
  database_name = var.database_name
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
      name = "rmse"
      type = "double"
    }
    columns {
      name = "mae"
      type = "double"
    }
    columns {
      name = "r2"
      type = "double"
    }
    columns {
      name = "mape"
      type = "double"
    }
    columns {
      name = "modelo_versao"
      type = "string"
    }
    columns {
      name = "dt_processamento"
      type = "string"
    }
    columns {
      name = "total_linhas"
      type = "bigint"
    }
    columns {
      name = "linhas_adicionadas"
      type = "bigint"
    }
    columns {
      name = "data_referencia_lote"
      type = "string"
    }
  }

  partition_keys {
    name = "run_date"
    type = "string"
  }
  partition_keys {
    name = "run_id"
    type = "string"
  }
}
