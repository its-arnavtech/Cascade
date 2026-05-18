# Topology Service

Provides target-catalog-backed service dependency topology with a static fallback graph for Telemetry pipeline callers.

## Endpoints

- `GET /health`
- `GET /topology`
- `GET /topology/graph`
- `GET /topology/{service_name}/downstream`
- `GET /topology/{service_name}/upstream`
- `GET /topology/{service_name}/dependencies?hops=2&direction=downstream`
- `POST /topology/impact`
- `POST /topology/blast-radius`
- `POST /topology/critical-paths`
