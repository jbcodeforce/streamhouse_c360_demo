################################################################################
# Confluent Cloud Provider Credentials
#
# These authenticate the Terraform provider and must be an OrganizationAdmin
# Cloud API key — creating service accounts, API keys, and RTCE topics are
# org-level operations (a resource-scoped key returns 401).
################################################################################

variable "confluent_cloud_api_key" {
  type        = string
  description = "Confluent Cloud API Key for provider auth (or set CONFLUENT_CLOUD_API_KEY). Needs OrganizationAdmin."
  default     = null
}

variable "confluent_cloud_api_secret" {
  type        = string
  description = "Confluent Cloud API Secret for provider auth (or set CONFLUENT_CLOUD_API_SECRET)."
  sensitive   = true
  default     = null
}

################################################################################
# Cloud / region (must match the Kafka cluster that backs the table)
################################################################################

variable "cloud_provider" {
  type        = string
  description = "Cloud provider of the Kafka cluster / RTCE topic"
  default     = "AWS"
}

variable "aws_region_primary" {
  type        = string
  description = "Region of the Kafka cluster / RTCE topic"
  default     = "us-west-2"
}

variable "prefix" {
  type        = string
  description = "Naming prefix for the RTCE service account and Global API key"
  default     = "j9r-jtbd1"
}

################################################################################
# Core stack state (environment + Kafka cluster ids)
################################################################################

variable "core_state_path" {
  type        = string
  description = "Path to the IaC/ccloud Terraform state whose environment/cluster this stack reads"
  default     = "../ccloud/terraform.tfstate"
}

################################################################################
# RTCE table
################################################################################

variable "profile_topic" {
  type        = string
  description = "Name of the fct_c360_profile materialized (upsert) topic to expose via the Lightning Query API"
  default     = "fct_c360_profile"
}

variable "crm_summary_topic" {
  type        = string
  description = "Name of the fct_crm_summary topic to expose via the Lightning Query API"
  default     = "fct_crm_summary"
}


variable "fct_hourly_tx_metrics_topic" {
  type        = string
  description = "Name of the fct_hourly_tx_metrics topic to expose via the Lightning Query API"
  default     = "fct_hourly_tx_metrics"
}