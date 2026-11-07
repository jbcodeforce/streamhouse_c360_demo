"""Reset the demo environment: empty the C360 database and delete the CDC topics.

Targets whatever ``config.settings`` resolves (``ENV_CONFIG_FILE`` / ``.env`` /
environment variables) — the same DATABASE_URL, Kafka cluster and Schema
Registry the backend itself uses.

    cd apps/backend
    uv run python clean_env.py                    # prompt, then truncate tables + delete topics
    uv run python clean_env.py --drop-tables      # drop tables instead (re-created by bootstrap)
    uv run python clean_env.py --delete-schemas   # also delete <topic>-key / <topic>-value subjects
    uv run python clean_env.py --skip-db          # Kafka only
    uv run python clean_env.py --skip-kafka       # database only
    uv run python clean_env.py --yes              # no confirmation prompt

Use ``--drop-tables`` after a column-type change: ``CREATE TABLE IF NOT EXISTS``
never alters an existing table. Dropped tables leave the CDC publication
automatically; bootstrap re-adds them on the next backend start.

The Debezium replication slot (if a managed connector is running) is NOT
touched — pause or delete the connector separately.
"""

from __future__ import annotations

import argparse
import logging
import sys

from confluent_kafka import KafkaError, KafkaException
from confluent_kafka.admin import AdminClient
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.error import SchemaRegistryError

import db
from config import _mask_dsn, settings

logger = logging.getLogger("c360.clean_env")

# Child → parent order so FK constraints never block a DROP.
_TABLES = ("transactions", "cards", "accounts", "customers")
_ADMIN_TIMEOUT_S = 30.0


def _topics() -> list[str]:
    return [
        settings.KAFKA_TOPIC_CUSTOMERS,
        settings.KAFKA_TOPIC_ACCOUNTS,
        settings.KAFKA_TOPIC_CARDS,
        settings.KAFKA_TOPIC_TRANSACTIONS,
    ]


def clean_database(*, drop: bool) -> None:
    """Truncate (default) or drop the three C360 tables in one transaction."""
    with db.cursor(commit=True) as cur:
        if drop:
            # Table names are module constants; identifiers cannot be bound.
            for table in _TABLES:
                cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE")  # noqa: S608
                logger.info("Dropped table %s", table)
        else:
            cur.execute(
                f"TRUNCATE TABLE {', '.join(_TABLES)} RESTART IDENTITY CASCADE"  # noqa: S608
            )
            logger.info("Truncated tables: %s", ", ".join(_TABLES))


def _kafka_client_conf() -> dict:
    conf: dict = {"bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS}
    if settings.KAFKA_API_KEY and settings.KAFKA_API_SECRET:
        conf.update({
            "security.protocol": "SASL_SSL",
            "sasl.mechanisms": "PLAIN",
            "sasl.username": settings.KAFKA_API_KEY,
            "sasl.password": settings.KAFKA_API_SECRET,
        })
    return conf


def delete_topics() -> None:
    """Delete the cdc.public.* topics; missing topics are skipped."""
    if not settings.KAFKA_BOOTSTRAP_SERVERS:
        raise RuntimeError("KAFKA_BOOTSTRAP_SERVERS is not configured")
    admin = AdminClient(_kafka_client_conf())
    futures = admin.delete_topics(_topics(), operation_timeout=_ADMIN_TIMEOUT_S)
    for topic, future in futures.items():
        try:
            future.result(timeout=_ADMIN_TIMEOUT_S)
            logger.info("Deleted topic %s", topic)
        except KafkaException as exc:
            if exc.args[0].code() == KafkaError.UNKNOWN_TOPIC_OR_PART:
                logger.info("Topic %s does not exist — skipped", topic)
            else:
                raise


def delete_schemas() -> None:
    """Soft- then hard-delete the <topic>-key / <topic>-value subjects."""
    if not settings.SCHEMA_REGISTRY_URL:
        raise RuntimeError("SCHEMA_REGISTRY_URL is not configured")
    client = SchemaRegistryClient({
        "url": settings.SCHEMA_REGISTRY_URL,
        "basic.auth.user.info": (
            f"{settings.SCHEMA_REGISTRY_API_KEY}:{settings.SCHEMA_REGISTRY_API_SECRET}"
        ),
    })
    for topic in _topics():
        for subject in (f"{topic}-key", f"{topic}-value"):
            try:
                client.delete_subject(subject)  # soft delete (required before permanent)
                client.delete_subject(subject, permanent=True)
                logger.info("Deleted schema subject %s", subject)
            except SchemaRegistryError as exc:
                if exc.http_status_code == 404:
                    logger.info("Schema subject %s does not exist — skipped", subject)
                else:
                    raise


def _confirm(args: argparse.Namespace) -> bool:
    print("This will permanently delete:")
    if not args.skip_db:
        action = "DROP" if args.drop_tables else "TRUNCATE"
        print(f"  database : {action} {', '.join(_TABLES)}  @ {_mask_dsn(settings.DATABASE_URL)}")
    if not args.skip_kafka:
        print(f"  topics   : {', '.join(_topics())}  @ {settings.KAFKA_BOOTSTRAP_SERVERS}")
        if args.delete_schemas:
            print("  schemas  : <topic>-key / <topic>-value subjects (soft + permanent)")
    if args.yes:
        return True
    return input("Type 'yes' to continue: ").strip().lower() == "yes"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Clean the C360 database and delete the CDC Kafka topics."
    )
    parser.add_argument("--skip-db", action="store_true", help="leave the database untouched")
    parser.add_argument("--skip-kafka", action="store_true", help="leave topics/schemas untouched")
    parser.add_argument(
        "--drop-tables", action="store_true",
        help="DROP the tables instead of TRUNCATE (use after a schema change)",
    )
    parser.add_argument(
        "--delete-schemas", action="store_true",
        help="also delete the Schema Registry subjects for the topics",
    )
    parser.add_argument("-y", "--yes", action="store_true", help="skip the confirmation prompt")
    args = parser.parse_args(argv)

    if args.skip_db and args.skip_kafka:
        parser.error("nothing to do: --skip-db and --skip-kafka are both set")
    if args.skip_db is False and not settings.DATABASE_URL:
        parser.error("DATABASE_URL is not configured (or pass --skip-db)")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if not _confirm(args):
        print("Aborted.")
        return 1

    if not args.skip_db:
        clean_database(drop=args.drop_tables)
    if not args.skip_kafka:
        delete_topics()
        if args.delete_schemas:
            delete_schemas()
    logger.info("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
