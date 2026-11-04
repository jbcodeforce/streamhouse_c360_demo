"""Database bootstrap: create schema + CDC publication and seed from CSV.

Defined once and reused by the FastAPI startup lifespan (see ``main.py``) and
by local tooling. Run directly against any PostgreSQL — RDS included — with
``DATABASE_URL`` set:

    DATABASE_URL=postgresql://... python bootstrap.py

Everything here is idempotent: tables use ``CREATE TABLE IF NOT EXISTS``,
each table adds itself to the CDC publication only if absent, and seeding
runs only when a table is empty.
"""

from __future__ import annotations

import logging

from accounts import (
    db_sink as accounts_db_sink,
    inventory as accounts_inventory,
)
from customers import (
    db_sink as customers_db_sink,
    inventory as customers_inventory,
)
from transactions import (
    db_sink as transactions_db_sink,
    inventory as transactions_inventory,
)

logger = logging.getLogger("c360.bootstrap")


def init_and_seed() -> None:
    """Create all tables + the CDC publication and seed each table if empty.

    Order matters: customers before accounts before transactions so the
    foreign keys resolve during seeding.
    """
    customers_db_sink.init_db()
    customers = customers_inventory.load()
    customers_db_sink.seed_from_csv(customers)

    accounts_db_sink.init_db()
    accounts = accounts_inventory.load()
    accounts_db_sink.seed_from_csv(accounts)

    transactions_db_sink.init_db()
    transactions = transactions_inventory.load()
    transactions_db_sink.seed_from_csv(transactions)

    logger.info(
        "Postgres ready — schema initialised, CDC publication set, tables seeded if empty"
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )
    init_and_seed()
