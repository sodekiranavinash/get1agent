output "function_name" {
  value = aws_lambda_function.this.function_name
}

output "function_arn" {
  value = aws_lambda_function.this.arn
}

output "invoke_arn" {
  value = aws_lambda_function.this.invoke_arn
}

output "role_arn" {
  value = aws_iam_role.lambda.arn
}

output "log_group_name" {
  value = aws_cloudwatch_log_group.lambda.name
}

output "security_group_id" {
  value = try(aws_security_group.lambda[0].id, null)
}
