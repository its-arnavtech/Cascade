import asyncio
import logging
import re
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, status

from app.config import Settings, get_settings
from app.models import HealthResponse, RawMetricsResponse, SnapshotResponse, TelemetryPodSnapshot
from app.normalizer import build_snapshot_queries, normalize_snapshot
from app.prometheus_client import PrometheusClient, PrometheusError
from services.shared.kafka.config import KafkaSettings
from services.shared.kafka.producer import KafkaProducer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    publisher_task = None
    if settings.telemetry_publish_enabled:
        publisher_task = asyncio.create_task(_publish_telemetry_loop(settings))
        logger.info("Telemetry Kafka publisher enabled")
    else:
        logger.info("Telemetry Kafka publisher disabled")

    try:
        yield
    finally:
        if publisher_task is not None:
            publisher_task.cancel()
            try:
                await publisher_task
            except asyncio.CancelledError:
                logger.info("Telemetry publisher loop stopped")


app = FastAPI(title="Cascade Observation Service", version="0.2.0", lifespan=lifespan)


def get_prometheus_client(settings: Settings = Depends(get_settings)) -> PrometheusClient:
    return PrometheusClient(settings.prometheus_url, settings.request_timeout_seconds)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service="observation-service")


@app.get("/snapshot", response_model=SnapshotResponse)
async def snapshot(
    settings: Settings = Depends(get_settings),
    prometheus: PrometheusClient = Depends(get_prometheus_client),
) -> SnapshotResponse:
    return await collect_snapshot(settings, prometheus)


async def collect_snapshot(settings: Settings, prometheus: PrometheusClient) -> SnapshotResponse:
    queries = build_snapshot_queries(settings.target_namespace)
    query_results = await asyncio.gather(
        *(prometheus.query(query) for query in queries.values()),
        return_exceptions=True,
    )

    normalized_results: dict[str, dict[str, Any] | None] = {}
    for metric_name, result in zip(queries.keys(), query_results, strict=True):
        if isinstance(result, Exception):
            logger.warning("Snapshot metric '%s' is unavailable: %s", metric_name, result)
            normalized_results[metric_name] = None
        else:
            normalized_results[metric_name] = result

    return normalize_snapshot(settings.target_namespace, normalized_results)


@app.get("/metrics/raw", response_model=RawMetricsResponse)
async def raw_metrics(
    query: str = Query(..., min_length=1, max_length=2000),
    prometheus: PrometheusClient = Depends(get_prometheus_client),
) -> RawMetricsResponse:
    safe_query = _validate_promql(query)
    try:
        payload = await prometheus.query(safe_query)
    except PrometheusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return RawMetricsResponse(query=safe_query, prometheus=payload)


def _validate_promql(query: str) -> str:
    normalized_query = query.strip()
    if not normalized_query:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Query must not be empty")

    # This endpoint only permits a single instant query expression.
    if re.search(r"[;\r\n]", normalized_query):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query must be a single PromQL expression",
        )

    return normalized_query


async def _publish_telemetry_loop(settings: Settings) -> None:
    kafka_settings = KafkaSettings(
        kafka_bootstrap_servers=settings.kafka_bootstrap_servers,
        kafka_client_id="observation-service",
    )
    prometheus = PrometheusClient(settings.prometheus_url, settings.request_timeout_seconds)

    while True:
        producer = KafkaProducer(kafka_settings)
        try:
            await producer.start()
            while True:
                snapshot_response = await collect_snapshot(settings, prometheus)
                published_count = 0
                for pod in snapshot_response.pods:
                    event = _build_raw_telemetry_event(snapshot_response.timestamp, pod)
                    await producer.send(settings.kafka_raw_topic, event, key=pod.pod_name)
                    published_count += 1

                logger.info(
                    "Telemetry publisher emitted events topic=%s count=%s namespace=%s",
                    settings.kafka_raw_topic,
                    published_count,
                    settings.target_namespace,
                )

                await asyncio.sleep(settings.telemetry_publish_interval_seconds)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Telemetry publisher loop failed and will retry: %s", exc)
            await asyncio.sleep(settings.telemetry_publish_interval_seconds)
        finally:
            await producer.stop()


def _build_raw_telemetry_event(timestamp: datetime, pod: TelemetryPodSnapshot) -> dict[str, Any]:
    event_timestamp = timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=UTC)
    return {
        "event_id": str(uuid4()),
        "timestamp": event_timestamp.isoformat(),
        "namespace": pod.namespace,
        "pod_name": pod.pod_name,
        "service_name": pod.service_name,
        "cpu": pod.cpu_usage_cores,
        "memory": pod.memory_working_set_bytes,
        "restart_count": pod.restart_count,
        "pod_phase": pod.pod_phase,
        "source": "observation-service",
    }
