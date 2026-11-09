# ------------------------------------------------------
# Flink Compute Pool
# Cloud/region mirror the Kafka cluster (see kafka.tf) so Flink runs
# alongside the cluster in the same environment.
# ------------------------------------------------------

resource "confluent_flink_compute_pool" "pool" {
  display_name = "${var.prefix}-flink-pool"
  cloud        = var.cloud_provider
  region       = var.aws_region_primary
  max_cfu      = var.flink_max_cfu

  environment {
    id = confluent_environment.env.id
  }

  depends_on = [
    confluent_kafka_cluster.kcl
  ]
}

# ------------------------------------------------------
# Second Flink Compute Pool — crm
# A dedicated pool for the crm data product so pipeline cost can be attributed
# per product (c360 runs on confluent_flink_compute_pool.pool above; crm runs
# here). dbt routes crm models to this pool via FLINK_CRM_COMPUTE_POOL_ID; the
# backend Cost API sums billed CFUs per pool. Reuses the same env/region and the
# shared flink_runner service account + API key (a Flink key is (env, region)
# scoped, not pool scoped), so no new key is needed.
# ------------------------------------------------------

resource "confluent_flink_compute_pool" "crm_pool" {
  display_name = "${var.prefix}-crm-flink-pool"
  cloud        = var.cloud_provider
  region       = var.aws_region_primary
  max_cfu      = var.flink_crm_max_cfu

  environment {
    id = confluent_environment.env.id
  }

  depends_on = [
    confluent_kafka_cluster.kcl
  ]
}

resource "confluent_flink_compute_pool" "sn_pool" {
  display_name = "${var.prefix}-snapshot-q-pool"
  cloud        = var.cloud_provider
  region       = var.aws_region_primary
  max_cfu      = var.flink_crm_max_cfu

  environment {
    id = confluent_environment.env.id
  }

  depends_on = [
    confluent_kafka_cluster.kcl
  ]
}

# ------------------------------------------------------
# Flink API key (environment + region scoped)
#
# A Confluent Flink API key is bound to one (environment, region) pair. dbt's
# confluent adapter authenticates its Flink statements with this key, so the key
# MUST live in the same environment as confluent_environment.env — otherwise the
# Flink REST API returns 404 resource_not_found. Creating it here (rather than by
# hand) keeps it in lockstep with the environment id whenever Terraform rotates
# the environment. set_env_from_tf.sh exports it as FLINK_API_KEY/SECRET.
# ------------------------------------------------------

data "confluent_organization" "org" {}

data "confluent_flink_region" "main" {
  cloud  = var.cloud_provider
  region = var.aws_region_primary
}

# Service account that owns the Flink API key and is the principal the statements
# run as. It needs EnvironmentAdmin (to create the Kafka-backed tables dbt
# materializes) and Assigner on itself (so it may submit statements that run as
# its own principal).
resource "confluent_service_account" "flink_runner" {
  display_name = "${var.prefix}-flink-runner"
  description  = "Owns the Flink API key and runs dbt Flink statements"
}

resource "confluent_role_binding" "flink-runner-env-admin" {
  principal   = "User:${confluent_service_account.flink_runner.id}"
  role_name   = "EnvironmentAdmin"
  crn_pattern = confluent_environment.env.resource_name
}

resource "confluent_role_binding" "flink-runner-assigner" {
  principal   = "User:${confluent_service_account.flink_runner.id}"
  role_name   = "Assigner"
  crn_pattern = "${data.confluent_organization.org.resource_name}/service-account=${confluent_service_account.flink_runner.id}"
}

resource "confluent_api_key" "flink-api-key" {
  display_name = "${var.prefix}-flink-api-key"
  description  = "Flink API Key scoped to ${var.prefix}-env / ${var.aws_region_primary}"

  owner {
    id          = confluent_service_account.flink_runner.id
    api_version = confluent_service_account.flink_runner.api_version
    kind        = confluent_service_account.flink_runner.kind
  }

  managed_resource {
    id          = data.confluent_flink_region.main.id
    api_version = data.confluent_flink_region.main.api_version
    kind        = data.confluent_flink_region.main.kind

    environment {
      id = confluent_environment.env.id
    }
  }

  depends_on = [
    confluent_role_binding.flink-runner-env-admin,
    confluent_role_binding.flink-runner-assigner,
  ]
}

# ------------------------------------------------------
# Cost API (billing) role binding
#
# The backend reads pipeline cost from the Confluent Cloud Cost API
# (GET /billing/v1/costs) using CONFLUENT_CLOUD_API_KEY/SECRET — the same cloud
# key that authenticates this Terraform provider and the Metrics API. That key's
# principal is supplied by the operator (not created here), so this binding is
# parameterized: set `cost_api_principal_id` to the service-account or user id
# behind CONFLUENT_CLOUD_API_KEY to grant it org-level cost read. The binding is
# skipped (count = 0) until that id is provided, so `terraform validate`/plan
# stay clean with defaults and an operator whose principal is already
# OrganizationAdmin can leave it unset. `cost_api_billing_role` defaults to
# OrganizationAdmin (which grants Cost API access); override it if your org
# exposes a narrower billing-read role.
# ------------------------------------------------------
resource "confluent_role_binding" "cost-api-billing" {
  count       = var.cost_api_principal_id == null ? 0 : 1
  principal   = "User:${var.cost_api_principal_id}"
  role_name   = var.cost_api_billing_role
  crn_pattern = data.confluent_organization.org.resource_name
}
