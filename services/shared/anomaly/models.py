from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelResult:
    model_name: str
    detector_type: str
    is_anomaly: bool
    score: float
    risk_score: float
    explanation: str
    evidence: dict[str, Any] = field(default_factory=dict)

