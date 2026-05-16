# Cascade Command Center

React + TypeScript + Vite operator UI for Cascade Phase 9.

## Local development

Start the Phase 9 API proxy on port `8031`, then run:

```powershell
npm install
npm run dev
```

The Vite dev server proxies `/api/*` to `http://localhost:8031`.

## Environment

```text
VITE_API_BASE_URL=/api
VITE_REFRESH_INTERVAL_MS=10000
VITE_ENABLE_DANGEROUS_ACTIONS=false
```
