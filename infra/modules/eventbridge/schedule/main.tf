resource "aws_cloudwatch_event_rule" "this" {
  name                = var.rule_name
  schedule_expression = var.schedule_expression

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "this" {
  rule      = aws_cloudwatch_event_rule.this.name
  target_id = "automation-target"
  arn       = var.target_arn
  role_arn  = var.target_role_arn
  input     = var.input
}
