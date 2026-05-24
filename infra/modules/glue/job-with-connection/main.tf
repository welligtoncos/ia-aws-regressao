resource "aws_security_group" "glue" {
  count = var.disable_sg_creation ? 0 : 1

  name        = "${var.project_name}-${var.glue_security_group}-${var.environment}"
  description = "Security group para Glue Connection - ${var.project_name}"

  vpc_id = var.glue_connection_properties["VPC_ID"]

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.glue_security_group}-${var.environment}"
  })
}

locals {
  security_group_ids = var.disable_sg_creation ? var.custom_sg_ids : [aws_security_group.glue[0].id]
}

resource "aws_glue_connection" "this" {
  name            = var.glue_connection_name
  connection_type = var.glue_connection_type

  connection_properties = var.glue_connection_properties

  dynamic "physical_connection_requirements" {
    for_each = length(var.custom_subnet_ids) > 0 ? [1] : []
    content {
      availability_zone      = var.glue_connection_properties["AVAILABILITY_ZONE"]
      security_group_id_list = local.security_group_ids
      subnet_id              = var.custom_subnet_ids[0]
    }
  }

  tags = var.tags
}

resource "aws_glue_job" "this" {
  name     = var.glue_job_name
  role_arn = var.glue_job_role_arn

  description = var.glue_job_description
  connections = [aws_glue_connection.this.name]

  command {
    name            = "glueetl"
    script_location = var.glue_script_location
    python_version  = "3"
  }

  default_arguments = merge(
    var.glue_job_default_arguments,
    {
      "--TempDir"                          = var.glue_temp_dir
      "--SOURCE_BUCKET"                    = var.glue_source_bucket
      "--OUTPUT_BUCKET"                    = var.glue_output_bucket
      "--enable-metrics"                   = "true"
      "--enable-continuous-cloudwatch-log" = "true"
    }
  )

  glue_version      = "4.0"
  number_of_workers = 2
  worker_type       = "G.1X"

  tags = var.tags
}
