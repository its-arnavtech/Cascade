from __future__ import annotations

import asyncio
import logging
from typing import Any

from services.shared.kafka.config import KafkaSettings
from services.shared.kafka.consumer import KafkaConsumer

logger = logging.getLogger(__name__)


class EventBuffer:
    def __init__(self, max_items: int = 2000) -> None:
        self.experiments: list[dict[str, Any]] = []
        self.telemetry: list[dict[str, Any]] = []
        self.max_items = max_items

    def add_experiment(self, event: dict[str, Any]) -> None:
        self.experiments.append(event)
        self.experiments = self.experiments[-self.max_items :]

    def add_telemetry(self, event: dict[str, Any]) -> None:
        self.telemetry.append(event)
        self.telemetry = self.telemetry[-self.max_items :]


async def consume_topic(topic: str, group_id: str, settings: KafkaSettings, sink) -> None:
    while True:
        consumer = KafkaConsumer(topic=topic, group_id=group_id, settings=settings, auto_offset_reset="earliest")
        try:
            await consumer.start()
            async for payload in consumer.messages():
                sink(payload)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Causal reader failed topic=%s error=%s", topic, exc)
            await asyncio.sleep(5)
        finally:
            await consumer.stop()
