from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict


def _resolve_env_file() -> str:
    env_file = os.environ.get("ENV_CONFIG_FILE")
    if env_file:
        if os.path.isabs(env_file) or os.path.exists(env_file):
            return env_file
        backend_dir = os.path.dirname(os.path.abspath(__file__))
        repo_root = os.path.abspath(os.path.join(backend_dir, "..", ".."))
        for candidate in [
            os.path.join(repo_root, env_file),
            os.path.join(backend_dir, env_file),
            os.path.abspath(env_file),
        ]:
            if os.path.exists(candidate):
                return candidate
        return env_file
    backend_default = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    return backend_default if os.path.exists(backend_default) else ".env"


def _mask_dsn(dsn: str | None) -> str:
    if not dsn:
        return "None"
    try:
        parsed = urlparse(dsn)
        if parsed.password:
            netloc = f"{parsed.username or ''}:****@{parsed.hostname or ''}"
            if parsed.port:
                netloc += f":{parsed.port}"
            return parsed._replace(netloc=netloc).geturl()
        return dsn
    except Exception:
        return "****"


class Settings(BaseSettings):
    # The dotenv file path itself comes from the ENV_CONFIG_FILE env var
    # (default ".env"); real environment variables still take precedence.
    model_config = SettingsConfigDict(
        env_file=_resolve_env_file(), extra="ignore"
    )

    DATABASE_URL: str | None = None
    KAFKA_BOOTSTRAP_SERVERS: str | None = None
    KAFKA_API_KEY: str | None = None
    KAFKA_API_SECRET: str | None = None
    SCHEMA_REGISTRY_URL: str | None = None
    SCHEMA_REGISTRY_API_KEY: str | None = None
    SCHEMA_REGISTRY_API_SECRET: str | None = None
    KAFKA_TOPIC_CUSTOMERS: str = "cdc.public.customers"
    KAFKA_TOPIC_ACCOUNTS: str = "cdc.public.accounts"
    KAFKA_TOPIC_CARDS: str = "cdc.public.cards"
    KAFKA_TOPIC_TRANSACTIONS: str = "cdc.public.transactions"
    # Agent-conversations history topic (owned by Terraform, see
    # IaC/ccloud/topics.tf). The chat backend produces request/response events
    # here for a downstream Flink agent to classify intents. The value schema is
    # registered at runtime (chat/conversation_producer.py); the topic is not.
    KAFKA_TOPIC_AGENT_CONVERSATIONS: str = "agent_conversations"

    # Assistant chat page: the greeting shown in the empty state. Served by
    # GET /api/v1/chat/welcome so the frontend can confirm it reaches the
    # backend (config propagation) on first connection.
    CHAT_FIRST_PROMPT: str = "Hi, Jerome"

    # When True, each live chat turn is also emitted to the agent_conversations
    # topic (request + response as two linked Avro events) for downstream Flink
    # intent analysis. Best-effort: a Kafka failure never breaks the reply.
    # Off by default so the no-infra test suite and a laptop without a broker
    # never attempt a real connection.
    CHAT_PRODUCE_CONVERSATIONS: bool = False
    # Local OpenAI-compatible LLM (MLX server). base_url like http://127.0.0.1:7999/v1.
    LLM_BASE_URL: str | None = None
    LLM_MODEL: str | None = None
    LLM_API_KEY: str = "local-key"
    LLM_TEMPERATURE: float = 0.2
    # The RTCE context-engine MCP server URL is NOT a standalone setting — it is
    # derived from the Confluent coordinates below (see rtce_mcp_url()), so it
    # cannot drift out of sync with them. Auth is the GLOBAL key via HTTP Basic
    # (CONFLUENT_GLOBAL_KEY/SECRET), the same org-wide key the Lightning API uses.

    # Live-mode credentials (unused until Task 3's LiveProvider).
    CONFLUENT_CLOUD_API_KEY: str | None = None
    CONFLUENT_CLOUD_API_SECRET: str | None = None
    FLINK_API_KEY: str | None = None
    FLINK_API_SECRET: str | None = None
    FLINK_ORG_ID: str | None = None
    FLINK_ENV_ID: str | None = None
    FLINK_COMPUTE_POOL_ID: str | None = None
    # Second compute pool backing the crm data product (c360 uses
    # FLINK_COMPUTE_POOL_ID). dbt routes crm models here and the Cost API sums
    # billed CFUs per pool. Wired from Terraform output flink_crm_compute_pool_id
    # by scripts/set_env_from_tf.sh.
    FLINK_CRM_COMPUTE_POOL_ID: str | None = None
    FLINK_REST_ENDPOINT: str | None = None
    # Catalog/database for Flink SQL snapshot queries — the Confluent Cloud
    # environment and Kafka cluster *display names* (not their IDs).
    FLINK_CATALOG: str | None = None
    FLINK_DATABASE: str | None = None

    # RTCE / Confluent Lightning Query API (point-lookup serving layer). Used by
    # the analytics "Customer lookup via RTCE" section in live mode. The endpoint
    # is https://sql.{CLOUD_REGION}.{CLOUD_PROVIDER}.confluent.cloud/query/v1alpha1;
    # the request is scoped by catalog_name = env *id* (FLINK_ENV_ID) and
    # database_name = Kafka cluster *id* (KAFKA_CLUSTER_ID) — IDs, not display
    # names. Authenticates with a dedicated *Global* resource API key
    # (CONFLUENT_GLOBAL_KEY/SECRET) — the Lightning API requires a key that
    # authenticates the whole organization, which a cluster/env/Flink/Metrics
    # key is not. Provisioned by IaC/ccloud/lightning.tf.
    CLOUD_REGION: str | None = None
    CLOUD_PROVIDER: str | None = None
    KAFKA_CLUSTER_ID: str | None = None
    CONFLUENT_GLOBAL_KEY: str | None = None
    CONFLUENT_GLOBAL_SECRET: str | None = None

    def rtce_mcp_url(self) -> str | None:
        """Full RTCE context-engine MCP server URL, derived from the Confluent
        coordinates. Returns None when any piece is missing.

        Shape (confirmed against the live server):
        https://mcp.{REGION}.{PROVIDER}.confluent.cloud/mcp/v1/context-engine/
        organizations/{ORG_ID}/environments/{ENV_ID}/kafka-clusters/{CLUSTER_ID}
        """
        parts = (
            self.CLOUD_REGION,
            self.CLOUD_PROVIDER,
            self.FLINK_ORG_ID,
            self.FLINK_ENV_ID,
            self.KAFKA_CLUSTER_ID,
        )
        if not all(parts):
            return None
        return (
            f"https://mcp.{self.CLOUD_REGION}.{self.CLOUD_PROVIDER}.confluent.cloud"
            f"/mcp/v1/context-engine/organizations/{self.FLINK_ORG_ID}"
            f"/environments/{self.FLINK_ENV_ID}/kafka-clusters/{self.KAFKA_CLUSTER_ID}"
        )

    def summary(self) -> dict[str, str]:
        """Return a dictionary of configuration key/values with secrets masked."""
        env_file = _resolve_env_file()
        exists = bool(env_file and os.path.exists(env_file))
        raw_env = os.environ.get("ENV_CONFIG_FILE")
        display_file = env_file if exists else (raw_env or env_file)
        return {
            "ENV_CONFIG_FILE": f"{display_file}" if exists else f"{display_file} (not found)",
            "DATABASE_URL": _mask_dsn(self.DATABASE_URL),
            "KAFKA_BOOTSTRAP_SERVERS": self.KAFKA_BOOTSTRAP_SERVERS or "None",
            "SCHEMA_REGISTRY_URL": self.SCHEMA_REGISTRY_URL or "None",
            "CHAT_PRODUCE_CONVERSATIONS": self.CHAT_PRODUCE_CONVERSATIONS,
            "CHAT_LLM": (f"{self.LLM_MODEL} @ {self.LLM_BASE_URL}" if (self.LLM_BASE_URL and self.LLM_MODEL) else "None"),
            "CHAT_RTCE_MCP": ("derived" if self.rtce_mcp_url() else "None"),
            "FLINK_REST_ENDPOINT": self.FLINK_REST_ENDPOINT or "None",
            "FLINK_COMPUTE_POOL_ID": self.FLINK_COMPUTE_POOL_ID or "None",
            "FLINK_CRM_COMPUTE_POOL_ID": self.FLINK_CRM_COMPUTE_POOL_ID or "None",
            "RTCE_LIGHTNING": (
                "configured"
                if (self.CLOUD_REGION and self.KAFKA_CLUSTER_ID and self.CONFLUENT_GLOBAL_KEY)
                else "None"
            ),
        }

    def log_summary(self, target_logger: logging.Logger | None = None) -> None:
        """Log active configuration settings."""
        if target_logger is None:
            log = logging.getLogger("c360.config")
            if not log.handlers and not logging.getLogger().handlers:
                logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        else:
            log = target_logger
        log.info("Active Backend Configuration:")
        for k, v in self.summary().items():
            log.info("  %-25s = %s", k, v)


settings = Settings()
