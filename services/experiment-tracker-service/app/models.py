from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ExperimentStatus = Literal["started", "running", "completed", "failed", "cancelled"]


class Settings(BaseSettings):
    kafka_bootstrap_servers: str = "localhost:9092"
    experiment_topic: str = "experiments.events"

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)


class ExperimentCreate(BaseModel):
    experiment_id: str | None = None
    experiment_type: str
    target_service: str
    namespace: str
    duration_seconds: int = Field(gt=0)
    chaos_mesh_resource: str | None = None
    status: ExperimentStatus = "started"


class ExperimentRecord(BaseModel):
    experiment_id: str
    experiment_type: str
    target_service: str
    namespace: str
    started_at: datetime
    duration_seconds: int
    chaos_mesh_resource: str | None = None
    status: ExperimentStatus
    completed_at: datetime | None = None

    @classmethod
    def from_create(cls, payload: ExperimentCreate) -> "ExperimentRecord":
        return cls(
            experiment_id=payload.experiment_id or str(uuid4()),
            experiment_type=payload.experiment_type,
            target_service=payload.target_service,
            namespace=payload.namespace,
            started_at=datetime.now(UTC),
            duration_seconds=payload.duration_seconds,
            chaos_mesh_resource=payload.chaos_mesh_resource,
            status=payload.status,
        )

    def to_event(self) -> dict[str, object]:
        return {
            "experiment_id": self.experiment_id,
            "experiment_type": self.experiment_type,
            "target_service": self.target_service,
            "namespace": self.namespace,
            "started_at": self.started_at.isoformat(),
            "duration": self.duration_seconds,
            "chaos_mesh_resource": self.chaos_mesh_resource or "",
            "status": self.status,
        }


class HealthResponse(BaseModel):
    status: str
    service: str
