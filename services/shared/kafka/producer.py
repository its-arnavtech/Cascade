from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiokafka import AIOKafkaProducer

from services.shared.kafka.config import KafkaSettings, get_kafka_settings
from services.shared.kafka.serialization import serialize_json

logger = logging.getLogger(__name__)


class KafkaProducer:
    """Async JSON Kafka producer with bounded retry handling."""

    def __init__(self, settings: KafkaSettings | None = None) -> None:
        self.settings = settings or get_kafka_settings()
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        if self._producer is not None:
            return

        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            client_id=self.settings.kafka_client_id,
            value_serializer=serialize_json,
        )
        await self._producer.start()
        logger.info("Kafka producer started bootstrap_servers=%s", self.settings.kafka_bootstrap_servers)

    async def stop(self) -> None:
        if self._producer is None:
            return

        await self._producer.stop()
        self._producer = None
        logger.info("Kafka producer stopped")

    async def send(self, topic: str, payload: dict[str, Any], key: str | None = None) -> None:
        if self._producer is None:
            raise RuntimeError("Kafka producer has not been started")

        encoded_key = key.encode("utf-8") if key else None
        last_error: Exception | None = None
        for attempt in range(1, self.settings.kafka_retry_attempts + 1):
            try:
                metadata = await self._producer.send_and_wait(topic, payload, key=encoded_key)
                logger.info(
                    "Published Kafka event topic=%s partition=%s offset=%s key=%s",
                    metadata.topic,
                    metadata.partition,
                    metadata.offset,
                    key,
                )
                return
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Kafka publish failed topic=%s attempt=%s/%s error=%s",
                    topic,
                    attempt,
                    self.settings.kafka_retry_attempts,
                    exc,
                )
                await asyncio.sleep(self.settings.kafka_retry_backoff_seconds * attempt)

        raise RuntimeError(f"Failed to publish Kafka event to {topic}") from last_error
