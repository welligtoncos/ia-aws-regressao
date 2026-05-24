resource "aws_glue_job" "this" {
  name     = var.glue_job_name
  role_arn = var.glue_job_role_arn

  description = var.glue_job_description

  command {
    name            = "glueetl"
    script_location = var.glue_script_location
    python_version  = "3"
  }

  default_arguments = merge(
    var.glue_job_default_arguments,
    {
      "--enable-metrics"                   = "true"
      "--enable-continuous-cloudwatch-log" = "true"
    }
  )

  glue_version      = "4.0"
  number_of_workers = 2
  worker_type       = "G.1X"

  tags = var.tags
}
