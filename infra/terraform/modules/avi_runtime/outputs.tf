output "microvm_image_arn" {
  value       = try(aws_lambdamicrovms_image.avi[0].arn, "")
  description = "ARN of the Avi Lambda MicroVM image (empty until enabled and built)"
}

output "ecr_repository_url" {
  value       = aws_ecr_repository.agent.repository_url
  description = "ECR repository URL the Avi agent image is pushed to"
}

output "runtime_role_arn" {
  value       = aws_iam_role.runtime.arn
  description = "Role the Avi agent container runs as (Bedrock, DynamoDB, S3, vectors)"
}

output "build_role_arn" {
  value       = try(aws_iam_role.build[0].arn, "")
  description = "Role the Lambda MicroVM build assumes"
}
