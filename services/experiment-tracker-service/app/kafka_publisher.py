from __future__ import annotations

import logging

from app.models import ExperimentRecord, Settings
from services.shared.kafka.config import KafkaSettings
from services.shared.kafka.producer import KafkaProducer

logger = logging.getLogger(__name__)


class ExperimentPublisher:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.producer = KafkaProducer(
            KafkaSettings(
                kafka_bootstrap_servers=settings.kafka_bootstrap_servers,
                kafka_client_id="experiment-tracker-service",
            )
        )

    async def start(self) -> None:
        await self.producer.start()

    async def stop(self) -> None:
        await self.producer.stop()

    async def publish(self, record: ExperimentRecord) -> None:
        await self.producer.send(
            self.settings.experiment_topic,
            record.to_event(),
            key=record.experiment_id,
        )
        logger.info("Published experiment event experiment_id=%s status=%s", record.experiment_id, record.status)
