from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class KafkaSettings(BaseSettings):
    """Kafka configuration shared by Cascade services."""

    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_client_id: str = "cascade-service"
    kafka_retry_attempts: int = 5
    kafka_retry_backoff_seconds: float = 1.0

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)


@lru_cache
def get_kafka_settings() -> KafkaSettings:
    return KafkaSettings()
