################################################################################
# Outputs
################################################################################

output "vpc_id" {
  description = "ID of the reused VPC"
  value       = data.aws_vpc.existing.id
}

output "vpc_cidr_block" {
  description = "CIDR block of the reused VPC"
  value       = data.aws_vpc.existing.cidr_block
}

output "db_subnet_group_name" {
  description = "Name of the DB Subnet Group created in the existing VPC"
  value       = aws_db_subnet_group.rds.name
}

output "db_security_group_id" {
  description = "Security group ID attached to the RDS instance"
  value       = aws_security_group.rds_sg.id
}

output "rds_endpoint" {
  description = "Connection endpoint for the PostgreSQL RDS instance"
  value       = aws_db_instance.postgres.endpoint
}

output "rds_address" {
  description = "Hostname of the PostgreSQL RDS instance"
  value       = aws_db_instance.postgres.address
}

output "rds_port" {
  description = "Port number of the PostgreSQL RDS instance"
  value       = aws_db_instance.postgres.port
}

output "rds_database_name" {
  description = "Default database name"
  value       = aws_db_instance.postgres.db_name
}

output "secrets_manager_secret_arn" {
  description = "ARN of the AWS Secrets Manager secret holding database credentials"
  value       = aws_secretsmanager_secret.db_credentials.arn
}

output "kms_key_arn" {
  description = "ARN of the customer-managed KMS key (RDS storage, secrets; reused by IaC/EC2 for EBS and its secret)"
  value       = aws_kms_key.rds_key.arn
}

output "confluent_egress_ips" {
  description = "Confluent Cloud Connect/Kafka egress IP addresses allowlisted in RDS security group"
  value       = [for ip in data.confluent_ip_addresses.connectors.ip_addresses : ip.ip_prefix]
}
