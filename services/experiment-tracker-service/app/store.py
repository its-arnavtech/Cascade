from __future__ import annotations

from datetime import UTC, datetime

from app.models import ExperimentRecord


class ExperimentStore:
    def __init__(self) -> None:
        self._records: dict[str, ExperimentRecord] = {}

    def add(self, record: ExperimentRecord) -> ExperimentRecord:
        self._records[record.experiment_id] = record
        return record

    def list(self) -> list[ExperimentRecord]:
        return sorted(self._records.values(), key=lambda item: item.started_at)

    def get(self, experiment_id: str) -> ExperimentRecord | None:
        return self._records.get(experiment_id)

    def complete(self, experiment_id: str) -> ExperimentRecord | None:
        record = self._records.get(experiment_id)
        if record is None:
            return None
        record.status = "completed"
        record.completed_at = datetime.now(UTC)
        self._records[experiment_id] = record
        return record
