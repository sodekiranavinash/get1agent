output "agent_runtime_arn" {
  value       = try(aws_bedrockagentcore_agent_runtime.worker[0].agent_runtime_arn, "")
  description = "AgentCore runtime ARN (empty until the image is pushed)"
}

output "agent_runtime_id" {
  value       = try(aws_bedrockagentcore_agent_runtime.worker[0].agent_runtime_id, "")
  description = "AgentCore runtime id"
}

output "ecr_repository_url" {
  value       = aws_ecr_repository.worker.repository_url
  description = "ECR repository URL for the worker image"
}

output "proxy_function_url" {
  value       = try(aws_lambda_function_url.proxy[0].function_url, "")
  description = "Public Function URL the browser streams agent runs through"
}
