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

output "control_plane_function_name" {
  value       = try(aws_lambda_function.proxy[0].function_name, "")
  description = "Control-plane Lambda invoked by API Gateway to start a MicroVM session"
}

output "control_plane_invoke_arn" {
  value       = try(aws_lambda_function.proxy[0].invoke_arn, "")
  description = "Invoke ARN of the control-plane Lambda (API Gateway integration)"
}

output "microvm_image_arn" {
  value       = try(aws_lambdamicrovms_image.agent_run[0].arn, "")
  description = "ARN of the agent-run Lambda MicroVM image (streaming proxy)"
}
