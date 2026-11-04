"""kafka_setup creates topics / schemas only when they are missing."""

from __future__ import annotations

from concurrent.futures import Future
from unittest.mock import MagicMock, patch

import pytest
from confluent_kafka import KafkaError, KafkaException
from confluent_kafka.schema_registry.error import SchemaRegistryError

import kafka_setup


def _future(exc: Exception | None = None) -> Future:
    f: Future = Future()
    if exc is None:
        f.set_result(None)
    else:
        f.set_exception(exc)
    return f


def _kafka_exc(code: int) -> KafkaException:
    err = MagicMock()
    err.code.return_value = code
    return KafkaException(err)


def test_ensure_topic_creates_when_missing():
    admin = MagicMock()
    admin.create_topics.return_value = {"t": _future()}
    with patch.object(kafka_setup, "AdminClient", return_value=admin):
        kafka_setup.ensure_topic({"bootstrap.servers": "x"}, "t")
    admin.create_topics.assert_called_once()
    assert admin.create_topics.call_args.args[0][0].topic == "t"


def test_ensure_topic_ignores_already_exists():
    admin = MagicMock()
    admin.create_topics.return_value = {
        "t": _future(_kafka_exc(KafkaError.TOPIC_ALREADY_EXISTS))
    }
    with patch.object(kafka_setup, "AdminClient", return_value=admin):
        kafka_setup.ensure_topic({"bootstrap.servers": "x"}, "t")


def test_ensure_topic_raises_other_errors():
    admin = MagicMock()
    admin.create_topics.return_value = {
        "t": _future(_kafka_exc(KafkaError.TOPIC_AUTHORIZATION_FAILED))
    }
    with patch.object(kafka_setup, "AdminClient", return_value=admin):
        with pytest.raises(KafkaException):
            kafka_setup.ensure_topic({"bootstrap.servers": "x"}, "t")


def test_ensure_schema_skips_when_registered():
    sr = MagicMock()
    kafka_setup.ensure_schema(sr, "t-key", "{}")
    sr.lookup_schema.assert_called_once()
    sr.register_schema.assert_not_called()


def test_ensure_schema_registers_on_404():
    sr = MagicMock()
    sr.lookup_schema.side_effect = SchemaRegistryError(404, 40401, "not found")
    kafka_setup.ensure_schema(sr, "t-key", "{}")
    sr.register_schema.assert_called_once()
    assert sr.register_schema.call_args.args[0] == "t-key"


def test_ensure_schema_raises_other_errors():
    sr = MagicMock()
    sr.lookup_schema.side_effect = SchemaRegistryError(401, 40101, "unauthorized")
    with pytest.raises(SchemaRegistryError):
        kafka_setup.ensure_schema(sr, "t-key", "{}")
    sr.register_schema.assert_not_called()


def test_ensure_kafka_resources_covers_topic_key_and_value():
    sr = MagicMock()
    with patch.object(kafka_setup, "ensure_topic") as topic, \
         patch.object(kafka_setup, "ensure_schema") as schema:
        kafka_setup.ensure_kafka_resources({"a": 1}, sr, "t", "K", "V")
    topic.assert_called_once_with({"a": 1}, "t")
    assert [c.args for c in schema.call_args_list] == [
        (sr, "t-key", "K"),
        (sr, "t-value", "V"),
    ]


# ---------------------------------------------------------------------------
# Bypass traces
# ---------------------------------------------------------------------------

def test_traces_topic_and_schema_creation(caplog):
    admin = MagicMock()
    admin.create_topics.return_value = {"t": _future()}
    sr = MagicMock()
    sr.lookup_schema.side_effect = SchemaRegistryError(404, 40401, "not found")
    sr.register_schema.return_value = 7
    with patch.object(kafka_setup, "AdminClient", return_value=admin), \
         caplog.at_level("INFO", logger="c360.kafka_setup"):
        kafka_setup.ensure_kafka_resources({"bootstrap.servers": "x"}, sr, "t", "K", "V")
    text = caplog.text
    assert "CREATED Kafka topic t" in text
    assert "REGISTERED schema subject t-key (id=7)" in text
    assert "REGISTERED schema subject t-value (id=7)" in text


def test_traces_when_resources_already_exist(caplog):
    admin = MagicMock()
    admin.create_topics.return_value = {
        "t": _future(_kafka_exc(KafkaError.TOPIC_ALREADY_EXISTS))
    }
    sr = MagicMock()
    with patch.object(kafka_setup, "AdminClient", return_value=admin), \
         caplog.at_level("INFO", logger="c360.kafka_setup"):
        kafka_setup.ensure_kafka_resources({"bootstrap.servers": "x"}, sr, "t", "K", "V")
    assert "topic t already exists" in caplog.text
    assert "subject t-key already registered" in caplog.text
