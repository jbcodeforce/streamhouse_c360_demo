################################################################################
# 1. Network access (Security Group)
################################################################################

# HTTP + SSH only from the allowlisted CIDRs (validated to exclude 0.0.0.0/0).
# The RDS security group (IaC/AWS) already admits 5432 from the whole VPC CIDR,
# so no extra database rule is needed for this instance.
resource "aws_security_group" "app" {
  name        = "${var.project_name}-${var.environment}-app-sg"
  description = "C360 app host: HTTP and SSH from allowlisted CIDRs only"
  vpc_id      = data.aws_vpc.existing.id

  tags = {
    Name        = "${var.project_name}-${var.environment}-app-sg"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_vpc_security_group_ingress_rule" "http" {
  for_each          = toset(var.allowed_cidr_blocks)
  security_group_id = aws_security_group.app.id
  description       = "HTTP from allowlisted CIDR"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  cidr_ipv4         = each.value
}

resource "aws_vpc_security_group_ingress_rule" "ssh" {
  for_each          = toset(var.allowed_cidr_blocks)
  security_group_id = aws_security_group.app.id
  description       = "SSH from allowlisted CIDR"
  ip_protocol       = "tcp"
  from_port         = 22
  to_port           = 22
  cidr_ipv4         = each.value
}

# The host pulls OS packages, container images, the git repo, and talks to
# Confluent Cloud and RDS, so outbound stays open (same as the RDS security group).
resource "aws_vpc_security_group_egress_rule" "all" {
  security_group_id = aws_security_group.app.id
  description       = "Allow all outbound traffic"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

################################################################################
# 2. Secrets Manager (backend settings; value supplied out of band)
################################################################################

# JSON object {ENV_VAR: value} with the backend's Kafka / Schema Registry / Flink
# settings (see apps/backend/.env.example). DATABASE_URL is derived at deploy time
# from the RDS secret, so it is not stored here. The secret VALUE is deliberately
# not managed by Terraform, so it never lands in state or git.
resource "aws_secretsmanager_secret" "app_env" {
  name                    = "${var.project_name}-${var.environment}-app-env"
  description             = "Backend environment (Kafka, Schema Registry, Flink) for the C360 app host"
  kms_key_id              = data.terraform_remote_state.aws.outputs.kms_key_arn
  recovery_window_in_days = 0

  tags = {
    Name        = "${var.project_name}-${var.environment}-app-env"
    Environment = var.environment
    Project     = var.project_name
  }
}

################################################################################
# 3. IAM (SSM Session Manager + read the two secrets, least privilege)
################################################################################

data "aws_iam_policy_document" "assume_ec2" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "app" {
  name               = "${var.project_name}-${var.environment}-app-role"
  assume_role_policy = data.aws_iam_policy_document.assume_ec2.json

  tags = {
    Name        = "${var.project_name}-${var.environment}-app-role"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.app.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "read_secrets" {
  statement {
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      data.terraform_remote_state.aws.outputs.secrets_manager_secret_arn,
      aws_secretsmanager_secret.app_env.arn,
    ]
  }

  statement {
    actions   = ["kms:Decrypt"]
    resources = [data.terraform_remote_state.aws.outputs.kms_key_arn]
  }
}

resource "aws_iam_role_policy" "read_secrets" {
  name   = "${var.project_name}-${var.environment}-read-secrets"
  role   = aws_iam_role.app.id
  policy = data.aws_iam_policy_document.read_secrets.json
}

resource "aws_iam_instance_profile" "app" {
  name = "${var.project_name}-${var.environment}-app-profile"
  role = aws_iam_role.app.name

  tags = {
    Name        = "${var.project_name}-${var.environment}-app-profile"
    Environment = var.environment
    Project     = var.project_name
  }
}

################################################################################
# 4. EC2 instance
################################################################################

resource "aws_instance" "app" {
  ami                         = nonsensitive(data.aws_ssm_parameter.al2023_ami.value)
  instance_type               = var.instance_type
  subnet_id                   = coalesce(var.subnet_id, try(data.aws_subnets.public.ids[0], null))
  vpc_security_group_ids      = [aws_security_group.app.id]
  iam_instance_profile        = aws_iam_instance_profile.app.name
  key_name                    = var.key_pair_name
  associate_public_ip_address = true

  # IMDSv2 only; hop limit 2 lets containers reach the metadata service if needed.
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = var.root_volume_size
    encrypted   = true
    kms_key_id  = data.terraform_remote_state.aws.outputs.kms_key_arn

    tags = {
      Name        = "${var.project_name}-${var.environment}-app-root"
      Environment = var.environment
      Project     = var.project_name
    }
  }

  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    deploy_script_b64 = base64encode(file("${path.module}/../../deploy/c360-deploy.sh"))
    repo_url          = var.repo_url
    repo_ref          = var.repo_ref
    aws_region        = var.aws_region_primary
    rds_secret_arn    = data.terraform_remote_state.aws.outputs.secrets_manager_secret_arn
    app_secret_id     = aws_secretsmanager_secret.app_env.arn
  })

  lifecycle {
    precondition {
      condition     = coalesce(var.subnet_id, try(data.aws_subnets.public.ids[0], null)) != null
      error_message = "No public subnet found in the IaC/AWS VPC; set subnet_id."
    }
  }

  tags = {
    Name        = "${var.project_name}-${var.environment}-app"
    Environment = var.environment
    Project     = var.project_name
  }
}
