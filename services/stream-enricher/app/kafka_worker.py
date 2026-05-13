from __future__ import annotations

import asyncio
import logging
from typing import Any

from pydantic import ValidationError

from app.enricher import enrich_event
from app.models import Settings, TelemetryRawEvent
from services.shared.kafka.config import KafkaSettings
from services.shared.kafka.consumer import KafkaConsumer
from services.shared.kafka.producer import KafkaProducer

logger = logging.getLogger(__name__)


class StreamEnricherWorker:
    def __init__(self, settings: Settings) -> None:
        kafka_settings = KafkaSettings(
            kafka_bootstrap_servers=settings.kafka_bootstrap_servers,
            kafka_client_id="stream-enricher",
        )
        self.settings = settings
        self.consumer = KafkaConsumer(
            topic=settings.kafka_raw_topic,
            group_id=settings.kafka_consumer_group,
            settings=kafka_settings,
        )
        self.producer = KafkaProducer(kafka_settings)
        self.processed_count = 0
        self.enriched_count = 0

    async def run(self) -> None:
        while True:
            try:
                await self.consumer.start()
                await self.producer.start()
                async for payload in self.consumer.messages():
                    await self._process_message(payload)
            except asyncio.CancelledError:
                logger.info(
                    "Stream enricher worker cancelled processed=%s enriched=%s",
                    self.processed_count,
                    self.enriched_count,
                )
                raise
            except Exception as exc:
                logger.exception("Stream enricher worker failed and will retry: %s", exc)
                await asyncio.sleep(5)
            finally:
                await self.producer.stop()
                await self.consumer.stop()

    async def _process_message(self, payload: dict[str, Any]) -> None:
        self.processed_count += 1
        try:
            raw_event = TelemetryRawEvent.model_validate(payload)
        except ValidationError as exc:
            logger.warning("Skipping invalid telemetry.raw event error=%s payload=%s", exc, payload)
            return

        enriched_event = enrich_event(raw_event, self.settings)
        await self.producer.send(
            self.settings.kafka_enriched_topic,
            enriched_event.model_dump(mode="json"),
            key=raw_event.pod_name,
        )
        self.enriched_count += 1
        logger.info(
            "Enriched telemetry event pod=%s derived_status=%s anomalies=%s processed=%s enriched=%s",
            raw_event.pod_name,
            enriched_event.derived_status,
            enriched_event.anomaly_flags,
            self.processed_count,
            self.enriched_count,
        )
