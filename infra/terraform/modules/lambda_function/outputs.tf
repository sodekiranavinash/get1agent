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

output "role_name" {
  value = aws_iam_role.lambda.name
}

output "log_group_name" {
  value = aws_cloudwatch_log_group.lambda.name
}

output "function_url" {
  value       = try(aws_lambda_function_url.this[0].function_url, "")
  description = "Public Function URL (empty unless create_function_url is set)"
}
