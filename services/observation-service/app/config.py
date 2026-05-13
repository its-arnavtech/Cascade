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

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
