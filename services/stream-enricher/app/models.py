from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


DerivedStatus = Literal["healthy", "warning", "degraded"]
AnomalyFlag = Literal["high_cpu", "high_memory", "unstable", "degraded"]


class Settings(BaseSettings):
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_raw_topic: str = "telemetry.raw"
    kafka_enriched_topic: str = "telemetry.enriched"
    kafka_consumer_group: str = "stream-enricher"
    high_memory_threshold_bytes: float = 512 * 1024 * 1024

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)


class TelemetryRawEvent(BaseModel):
    event_id: str
    timestamp: datetime
    namespace: str
    pod_name: str
    service_name: str | None = None
    cpu: float | None = None
    memory: float | None = None
    restart_count: float | None = None
    pod_phase: str | None = None
    source: str


class NormalizedFields(BaseModel):
    cpu_percent: float | None = Field(default=None, description="CPU cores normalized to percentage of one core.")
    memory_mib: float | None = Field(default=None, description="Memory bytes normalized to mebibytes.")
    restart_count: int = 0


class TelemetryEnrichedEvent(TelemetryRawEvent):
    anomaly_flags: list[AnomalyFlag]
    ingestion_timestamp: datetime
    normalized_fields: NormalizedFields
    derived_status: DerivedStatus


class HealthResponse(BaseModel):
    status: str
    service: str
