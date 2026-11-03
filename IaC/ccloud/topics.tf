# ------------------------------------------------------
# Kafka topics owned by Terraform
# ------------------------------------------------------
# agent_conversations — history of user interactions with the real-time
# context engine. The chat backend produces two Avro records per turn
# (type="request" / type="response", keyed by session_id, linked by turn_id);
# a downstream Flink agent consumes this stream for intent classification.
#
# The topic lifecycle is managed here; the value schema is registered by the
# backend at runtime (apps/backend/chat/conversation_producer.py).
# ------------------------------------------------------

resource "confluent_kafka_topic" "agent_conversations" {
  kafka_cluster {
    id = confluent_kafka_cluster.kcl.id
  }
  topic_name       = var.agent_conversations_topic
  partitions_count = var.agent_conversations_partitions
  rest_endpoint    = confluent_kafka_cluster.kcl.rest_endpoint

  credentials {
    key    = confluent_api_key.kcl-kafka-api-key.id
    secret = confluent_api_key.kcl-kafka-api-key.secret
  }

  depends_on = [
    confluent_api_key.kcl-kafka-api-key
  ]
}

# Debezium metadata topics required for Kafka Connect
resource "confluent_kafka_topic" "debezium_configs" {
  kafka_cluster {
    id = confluent_kafka_cluster.kcl.id
  }
  topic_name       = "my_connect_configs"
  partitions_count = 1
  rest_endpoint    = confluent_kafka_cluster.kcl.rest_endpoint

  config = {
    "cleanup.policy" = "compact"
  }

  credentials {
    key    = confluent_api_key.kcl-kafka-api-key.id
    secret = confluent_api_key.kcl-kafka-api-key.secret
  }

  depends_on = [
    confluent_api_key.kcl-kafka-api-key
  ]
}

resource "confluent_kafka_topic" "debezium_offsets" {
  kafka_cluster {
    id = confluent_kafka_cluster.kcl.id
  }
  topic_name       = "my_connect_offsets"
  partitions_count = 25
  rest_endpoint    = confluent_kafka_cluster.kcl.rest_endpoint

  config = {
    "cleanup.policy" = "compact"
  }

  credentials {
    key    = confluent_api_key.kcl-kafka-api-key.id
    secret = confluent_api_key.kcl-kafka-api-key.secret
  }

  depends_on = [
    confluent_api_key.kcl-kafka-api-key
  ]
}

resource "confluent_kafka_topic" "debezium_status" {
  kafka_cluster {
    id = confluent_kafka_cluster.kcl.id
  }
  topic_name       = "my_connect_status"
  partitions_count = 5
  rest_endpoint    = confluent_kafka_cluster.kcl.rest_endpoint

  config = {
    "cleanup.policy" = "compact"
  }

  credentials {
    key    = confluent_api_key.kcl-kafka-api-key.id
    secret = confluent_api_key.kcl-kafka-api-key.secret
  }

  depends_on = [
    confluent_api_key.kcl-kafka-api-key
  ]
}

output "agent_conversations_topic" {
  description = "Name of the agent-conversations history topic"
  value       = confluent_kafka_topic.agent_conversations.topic_name
}

output "debezium_topics" {
  description = "Debezium metadata topics for Kafka Connect"
  value = {
    configs = confluent_kafka_topic.debezium_configs.topic_name
    offsets = confluent_kafka_topic.debezium_offsets.topic_name
    status  = confluent_kafka_topic.debezium_status.topic_name
  }
}
