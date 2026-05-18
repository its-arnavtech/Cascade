from __future__ import annotations

from pydantic import BaseModel, Field


class CausalityAnalyzeRequest(BaseModel):
    target_service: str | None = None
    target_feature: str = Field(default="error_rate", min_length=1)
    source_feature: str | None = None
    service: str | None = None
    namespace: str | None = None
    limit: int = Field(default=250, ge=10, le=1000)
    max_lag_windows: int = Field(default=5, ge=0, le=24)
    min_correlation_samples: int = Field(default=8, ge=4, le=500)
    min_granger_samples: int = Field(default=30, ge=10, le=1000)
    granger_max_lag: int = Field(default=2, ge=1, le=6)

