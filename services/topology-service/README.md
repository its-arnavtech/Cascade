# Topology Service

Provides a static Online Boutique service dependency graph for Phase 2.

## Endpoints

- `GET /health`
- `GET /topology`
- `GET /topology/{service_name}/downstream`
- `GET /topology/{service_name}/upstream`
- `POST /topology/impact`
