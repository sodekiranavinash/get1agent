output "queue_arn" {
  value = aws_sqs_queue.this.arn
}

output "queue_url" {
  value = aws_sqs_queue.this.id
}

output "dlq_arn" {
  value = aws_sqs_queue.dlq.arn
}

output "state_machine_arn" {
  value = aws_sfn_state_machine.this.arn
}

output "event_rule_arn" {
  value = aws_cloudwatch_event_rule.s3.arn
}
