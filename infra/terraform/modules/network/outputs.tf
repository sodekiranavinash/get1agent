output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "private_subnet_ids" {
  description = "Private subnet IDs for VPC Lambdas"
  value       = [aws_subnet.private_a.id, aws_subnet.private_b.id]
}

output "postgres_security_group_id" {
  description = "RDS security group ID"
  value       = aws_security_group.postgres.id
}

output "db_subnet_group_name" {
  description = "DB subnet group name for RDS module"
  value       = aws_db_subnet_group.postgres.name
}

output "jumpbox_instance_id" {
  description = "On-demand jumpbox EC2 (stop when idle to avoid public IPv4 charges)"
  value       = aws_instance.jumpbox.id
}

output "db_access_command" {
  description = "Start jumpbox, SSM tunnel to RDS, stop on exit"
  value       = "bash infra/aws/db-access.sh"
}

# Backward-compatible alias for scripts still using app_instance_id.
output "app_instance_id" {
  value = aws_instance.jumpbox.id
}
