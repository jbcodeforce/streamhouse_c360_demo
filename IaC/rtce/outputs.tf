# ------------------------------------------------------
# RTCE / Lightning Query API (Global key)
# ------------------------------------------------------
output "rtce_lightning_sa_id" {
  description = "Service account ID that owns the RTCE Lightning Global key"
  value       = confluent_service_account.rtce_lightning.id
}

output "rtce_lightning_api_key_id" {
  description = "Global API key ID for the RTCE Lightning Query API (CONFLUENT_GLOBAL_KEY)"
  value       = confluent_api_key.rtce_lightning.id
}

output "rtce_lightning_api_key_secret" {
  description = "Global API key secret for the RTCE Lightning Query API (CONFLUENT_GLOBAL_SECRET)"
  value       = confluent_api_key.rtce_lightning.secret
  sensitive   = true
}

output "rtce_c360_profile_topic_name" {
  description = "Topic registered with the Real-Time Context Engine"
  value       = confluent_rtce_topic.fct_c360_profile.topic_name
}

output "rtce_crm_summary_topic_name" {
  description = "Topic registered with the Real-Time Context Engine"
  value       = confluent_rtce_topic.fct_crm_summary.topic_name
}

