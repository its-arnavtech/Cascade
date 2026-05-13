from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from aiokafka import AIOKafkaConsumer

from services.shared.kafka.config import KafkaSettings, get_kafka_settings
from services.shared.kafka.serialization import deserialize_json

logger = logging.getLogger(__name__)


class KafkaConsumer:
    """Async JSON Kafka consumer wrapper for service workers."""

    def __init__(
        self,
        topic: str,
        group_id: str,
        settings: KafkaSettings | None = None,
        auto_offset_reset: str = "latest",
    ) -> None:
        self.topic = topic
        self.group_id = group_id
        self.settings = settings or get_kafka_settings()
        self.auto_offset_reset = auto_offset_reset
        self._consumer: AIOKafkaConsumer | None = None

    async def start(self) -> None:
        if self._consumer is not None:
            return

        self._consumer = AIOKafkaConsumer(
            self.topic,
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            client_id=self.settings.kafka_client_id,
            group_id=self.group_id,
            auto_offset_reset=self.auto_offset_reset,
            enable_auto_commit=False,
            value_deserializer=deserialize_json,
        )
        await self._consumer.start()
        logger.info(
            "Kafka consumer started topic=%s group_id=%s bootstrap_servers=%s",
            self.topic,
            self.group_id,
            self.settings.kafka_bootstrap_servers,
        )

    async def stop(self) -> None:
        if self._consumer is None:
            return

        await self._consumer.stop()
        self._consumer = None
        logger.info("Kafka consumer stopped topic=%s group_id=%s", self.topic, self.group_id)

    async def messages(self) -> AsyncIterator[dict[str, Any]]:
        if self._consumer is None:
            raise RuntimeError("Kafka consumer has not been started")

        async for message in self._consumer:
            logger.info(
                "Consumed Kafka event topic=%s partition=%s offset=%s",
                message.topic,
                message.partition,
                message.offset,
            )
            yield message.value
            await self._consumer.commit()
