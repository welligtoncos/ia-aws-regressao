resource "aws_sfn_state_machine" "this" {
  name     = var.state_machine_name
  role_arn = var.role_arn
  type     = var.state_machine_type

  definition = var.definition

  tags = var.tags
}
