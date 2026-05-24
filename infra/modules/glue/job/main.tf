resource "aws_glue_job" "this" {
  name     = var.glue_job_name
  role_arn = var.glue_job_role_arn

  description = var.glue_job_description

  command {
    name            = var.glue_command_type
    script_location = var.glue_script_location
    python_version  = var.glue_command_type == "pythonshell" ? "3.9" : "3"
  }

  default_arguments = merge(
    var.glue_job_default_arguments,
    {
      "--enable-metrics"                   = "true"
      "--enable-continuous-cloudwatch-log" = "true"
    }
  )

  glue_version = var.glue_command_type == "pythonshell" ? "3.0" : "4.0"

  execution_property {
    max_concurrent_runs = var.max_concurrent_runs
  }

  max_capacity      = var.glue_command_type == "pythonshell" ? var.python_shell_capacity : null
  number_of_workers = var.glue_command_type == "glueetl" ? var.number_of_workers : null
  worker_type       = var.glue_command_type == "glueetl" ? var.worker_type : null

  tags = var.tags
}
