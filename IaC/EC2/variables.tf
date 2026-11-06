variable "aws_region_primary" {
  type        = string
  description = "AWS region (must match the IaC/AWS stack)"
  default     = "us-west-2"
}

variable "environment" {
  type        = string
  description = "Deployment environment name"
  default     = "demo"
}

variable "project_name" {
  type        = string
  description = "Project name identifier"
  default     = "c360"
}

variable "aws_state_path" {
  type        = string
  description = "Path to the IaC/AWS Terraform state file whose outputs this stack consumes"
  default     = "../AWS/terraform.tfstate"
}

variable "subnet_id" {
  type        = string
  description = "Subnet for the instance (optional; defaults to the first public subnet of the IaC/AWS VPC)"
  default     = null
}

variable "instance_type" {
  type        = string
  description = "EC2 instance type (x86_64; images are built on the instance, so keep >= 4 GiB RAM)"
  default     = "t3.medium"
}

variable "root_volume_size" {
  type        = number
  description = "Root EBS volume size in GB (holds Docker images and build cache)"
  default     = 30
}

variable "key_pair_name" {
  type        = string
  description = "Name of an existing EC2 key pair for SSH access"
}

variable "allowed_cidr_blocks" {
  type        = list(string)
  description = "CIDR blocks allowed to reach HTTP (80) and SSH (22), e.g. [\"203.0.113.10/32\"]. Never 0.0.0.0/0."

  validation {
    condition     = length(var.allowed_cidr_blocks) > 0 && alltrue([for c in var.allowed_cidr_blocks : can(cidrhost(c, 0)) && !contains(["0.0.0.0/0", "::/0"], c)])
    error_message = "Provide at least one valid CIDR block; 0.0.0.0/0 and ::/0 are not allowed."
  }
}

variable "repo_url" {
  type        = string
  description = "HTTPS git URL cloned onto the instance (must be reachable without credentials)"
}

variable "repo_ref" {
  type        = string
  description = "Branch or tag of repo_url to deploy"
  default     = "main"
}
