from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    prometheus_url: str = "http://prometheus-stack-kube-prom-prometheus.monitoring.svc.cluster.local:9090"
    target_namespace: str = "cascade-targets"
    request_timeout_seconds: float = 10.0
    telemetry_publish_enabled: bool = False
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_raw_topic: str = "telemetry.raw"
    telemetry_publish_interval_seconds: float = 10.0
    redpanda_health_url: str = "http://redpanda.cascade-system.svc.cluster.local:9644/v1/status/ready"
    clickhouse_health_url: str = "http://clickhouse.cascade-system.svc.cluster.local:8123/ping"
    qdrant_health_url: str = "http://qdrant.cascade-system.svc.cluster.local:6333/readyz"

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
