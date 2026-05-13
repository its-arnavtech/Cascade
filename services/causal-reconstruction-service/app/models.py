from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    kafka_bootstrap_servers: str = "localhost:9092"
    experiment_topic: str = "experiments.events"
    enriched_topic: str = "telemetry.enriched"
    kafka_consumer_group: str = "causal-reconstruction-service"

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)


class HealthResponse(BaseModel):
    status: str
    service: str


class ReconstructRequest(BaseModel):
    experiment_id: str
    lookback_seconds: int = Field(default=60, gt=0)
    window_seconds: int = Field(default=300, gt=0)


class IncidentRecord(BaseModel):
    incident_id: str = Field(default_factory=lambda: str(uuid4()))
    experiment_id: str
    root_cause_service: str | None
    causal_chain: list[str]
    affected_services: list[str]
    confidence: str
    evidence: list[dict[str, object]]
    started_at: datetime
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
