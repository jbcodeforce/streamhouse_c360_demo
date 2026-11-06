################################################################################
# Data Sources
################################################################################

# Outputs of the IaC/AWS stack: VPC, RDS security group, RDS secret, KMS key.
data "terraform_remote_state" "aws" {
  backend = "local"
  config = {
    path = var.aws_state_path
  }
}

# Latest Amazon Linux 2023 AMI (x86_64) published by AWS.
data "aws_ssm_parameter" "al2023_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

data "aws_vpc" "existing" {
  id = data.terraform_remote_state.aws.outputs.vpc_id
}

# Public subnets of the VPC (auto-assign public IPv4) when subnet_id is not given.
data "aws_subnets" "public" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.existing.id]
  }

  filter {
    name   = "map-public-ip-on-launch"
    values = ["true"]
  }
}
