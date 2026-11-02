"""C360 Backend — application entrypoint."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import bootstrap
from api.account_resource import router as account_router
from api.analytics_resource import router as analytics_router
from api.chat_resource import router as chat_router
from api.customer_resource import router as customers_router
from api.data_product_resource import router as data_product_router
from api.scenario_resource import router as scenario_router
from api.transaction_resource import router as transaction_router
from config import settings
from customers import inventory as customers_inventory
from accounts  import inventory as account_inventory
from transactions import inventory as transaction_inventory

logger = logging.getLogger("c360.main")


def _configure_logging() -> None:
    """Make the app's own traces visible under uvicorn (which leaves root alone).

    Covers ``c360.*`` plus the package loggers that use ``__name__`` — notably
    ``analytics.*`` (Flink snapshot / Lightning clients) and ``data_products.*``
    — so their INFO traces and WARNING diagnostics (e.g. which Flink setting is
    missing, or a Flink/Lightning API error body) actually reach the console.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    for name in ("c360", "analytics", "data_products"):
        log = logging.getLogger(name)
        log.setLevel(logging.INFO)
        if not any(isinstance(h, logging.StreamHandler) for h in log.handlers):
            log.addHandler(handler)


_configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.log_summary(logger)
    if settings.CDC_CONNECTOR_ENABLED:
        logger.info("[bypass] OFF — a CDC connector owns the cdc.public.* topics")
    elif settings.KAFKA_PRODUCE_ENABLED or settings.KAFKA_SEED_ON_START or settings.SINK == "kafka":
        logger.info(
            "[bypass] ON — backend writes Debezium-shaped events directly to Kafka "
            "(produce=%s, seed_on_start=%s, sink=%s)",
            settings.KAFKA_PRODUCE_ENABLED, settings.KAFKA_SEED_ON_START, settings.SINK,
        )
    else:
        logger.info("[bypass] OFF — KAFKA_PRODUCE_ENABLED and KAFKA_SEED_ON_START are false")
    if settings.SINK == "postgres":
        bootstrap.init_and_seed()
    elif settings.SINK == "kafka":
        customers = customers_inventory.load()
        account_inventory.load()
        transaction_inventory.load()
        logger.info("Kafka sink ready — %d customers loaded from CSV", len(customers))
    if settings.KAFKA_SEED_ON_START:
        if settings.CDC_CONNECTOR_ENABLED:
            logger.warning(
                "KAFKA_SEED_ON_START ignored — a CDC connector owns the Kafka topics"
            )
        else:
            bootstrap.seed_kafka()
    yield
    # Close any cached chat (RTCE MCP) sessions on shutdown.
    try:
        from chat import agent as chat_agent

        await chat_agent.shutdown()
    except Exception:
        logger.exception("error shutting down chat sessions")


app = FastAPI(title="C360 Backend", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(customers_router, prefix="/api/v1")
app.include_router(account_router, prefix="/api/v1")
app.include_router(transaction_router, prefix="/api/v1")
app.include_router(data_product_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")
app.include_router(scenario_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok", "sink": settings.SINK}
