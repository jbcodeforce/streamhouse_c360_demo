# RTCE / Lightning Query API enablement — a SEPARATE stack, applied AFTER dbt
# has created the fct_c360_profile materialized table.
#
# Order of operations:
#   1. IaC/ccloud   — environment, Kafka cluster, Flink (this stack reads its state)
#   2. dbt run      — creates the fct_c360_profile upsert/compacted topic
#   3. IaC/rtce     — THIS stack: Global key + registers the topic with RTCE
#
# confluent_rtce_topic registers an EXISTING topic with the Real-Time Context
# Engine so the Lightning Query API can serve it; without it every Lightning
# query returns HTTP 400 "Customer table info not found for org/env/lkc". That
# is why this is split out of IaC/ccloud — the topic must exist first.
#
# PREREQUISITE: the Real-Time Context Engine / Lightning Query API Early Access
# feature must be enabled for the organization, or RTCE reports the org as not
# found regardless of this stack.
#

# Service account that owns the Global key and reads the table's data.
resource "confluent_service_account" "rtce_lightning" {
  display_name = "${var.prefix}-rtce-lightning"
  description  = "Queries ${var.profile_topic} via the RTCE Lightning Query API"
}

# Read access to the Kafka cluster (the lightning table's data). CloudClusterAdmin
# can be narrowed to DeveloperRead on the specific topic once the exact privilege the Lightning query needs is confirmed.
resource "confluent_role_binding" "rtce_lightning_cluster_admin" {
  principal   = "User:${confluent_service_account.rtce_lightning.id}"
  role_name   = "CloudClusterAdmin"
  crn_pattern = data.confluent_kafka_cluster.this.rbac_crn
}

# Read access to the Schema Registry subjects, so Avro-encoded rows decode.
resource "confluent_role_binding" "rtce_lightning_sr_owner" {
  principal   = "User:${confluent_service_account.rtce_lightning.id}"
  role_name   = "ResourceOwner"
  crn_pattern = "${data.confluent_schema_registry_cluster.this.resource_name}/subject=*"
}

# The Global API key — kind "Global" authenticates the whole organization, which
# is what the Lightning Query API requires. Populate CONFLUENT_GLOBAL_KEY /
# CONFLUENT_GLOBAL_SECRET from the outputs.
resource "confluent_api_key" "rtce_lightning" {
  display_name = "${var.prefix}-rtce-lightning-key"
  description  = "Global API key for the RTCE Lightning Query API (CONFLUENT_GLOBAL_KEY)"

  owner {
    id          = confluent_service_account.rtce_lightning.id
    api_version = confluent_service_account.rtce_lightning.api_version
    kind        = confluent_service_account.rtce_lightning.kind
  }

  managed_resource {
    id          = "global"
    api_version = "global/v1"
    kind        = "Global"
  }

  depends_on = [
    confluent_role_binding.rtce_lightning_cluster_admin,
    confluent_role_binding.rtce_lightning_sr_owner,
  ]
}

# Register the (already-existing) materialized topic with the Real-Time Context
# Engine so the Lightning Query API serves it.
resource "confluent_rtce_topic" "fct_c360_profile" {
  cloud       = var.cloud_provider
  region      = var.aws_region_primary
  topic_name  = var.profile_topic
  description = "Customer 360 analytics profiles"

  environment {
    id = local.environment_id
  }

  kafka_cluster {
    id = local.kafka_cluster_id
  }
}

resource "confluent_rtce_topic" "fct_crm_summary" {
  cloud       = var.cloud_provider
  region      = var.aws_region_primary
  topic_name  = var.crm_summary_topic
  description = "CRM analytics"

  environment {
    id = local.environment_id
  }

  kafka_cluster {
    id = local.kafka_cluster_id
  }
}

resource "confluent_rtce_topic" "fct_hourly_tx_metrics" {
  cloud       = var.cloud_provider
  region      = var.aws_region_primary
  topic_name  = var.fct_hourly_tx_metrics_topic
  description = "Tx hourly analytics"

  environment {
    id = local.environment_id
  }

  kafka_cluster {
    id = local.kafka_cluster_id
  }
}
