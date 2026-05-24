output "state_machine_name" {
  description = "Nome da state machine."
  value       = aws_sfn_state_machine.this.name
}

output "state_machine_arn" {
  description = "ARN da state machine."
  value       = aws_sfn_state_machine.this.arn
}
