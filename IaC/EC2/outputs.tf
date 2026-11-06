################################################################################
# Outputs
################################################################################

output "instance_id" {
  description = "EC2 instance ID (use with: aws ssm start-session --target <id>)"
  value       = aws_instance.app.id
}

output "public_ip" {
  description = "Public IPv4 address of the app host"
  value       = aws_instance.app.public_ip
}

output "app_url" {
  description = "URL of the C360 app (reachable only from allowed_cidr_blocks)"
  value       = "http://${aws_instance.app.public_ip}/"
}

output "app_secret_arn" {
  description = "Secrets Manager secret to fill with the backend env JSON (see IaC/EC2/README.md)"
  value       = aws_secretsmanager_secret.app_env.arn
}
