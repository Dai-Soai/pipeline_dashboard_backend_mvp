# Operations Guide

## Development Server

~~~bash
pipeline-dashboard-backend serve \
  --host 127.0.0.1 \
  --port 8000 \
  --reload
~~~

## Production-Like Local Server

~~~bash
pipeline-dashboard-backend serve \
  --host 127.0.0.1 \
  --port 8000
~~~

Do not use development reload mode for production deployment.

## Health Check

~~~bash
curl http://127.0.0.1:8000/health
~~~

Expected result:

~~~json
{
  "status": "ok",
  "service": "pipeline-dashboard-backend",
  "version": "0.1.0"
}
~~~

## Build Dashboard Artifact

~~~bash
pipeline-dashboard-backend build \
  reports/metrics.json \
  reports/health.json \
  --output reports/dashboard_report.json
~~~

## Inspect Artifact

~~~bash
pipeline-dashboard-backend inspect \
  reports/dashboard_report.json
~~~

## Validate Artifact

~~~bash
pipeline-dashboard-backend validate \
  reports/dashboard_report.json
~~~

## Exit Codes

- `0`: success
- `1`: command or artifact I/O failure
- `2`: unsuccessful dashboard report or invalid artifact

## Current Storage Model

The HTTP API stores only the latest dashboard build in memory.

Restarting the service clears the latest dashboard state.

## Known Warning

FastAPI `TestClient` may emit a Starlette dependency deprecation warning during
tests. The warning does not affect Uvicorn runtime operation.
