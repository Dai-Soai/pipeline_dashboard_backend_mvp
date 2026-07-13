# Pipeline Dashboard Backend MVP

Utility #30 of RADAR_SERVICE.

An artifact-first backend for loading, normalizing, aggregating, querying,
serving, and exporting RADAR_SERVICE runtime observability data.

## Status

- Version: `0.1.0`
- Phase: Runtime Observability
- Maturity: MVP / Alpha
- Platform focus: Linux
- Python: 3.11+
- Current state backend: In-memory
- Project status: DEVELOPMENT — awaiting M10 release

## Purpose

Pipeline Dashboard Backend converts observability artifacts produced by
RADAR_SERVICE utilities into a normalized dashboard snapshot.

It provides three access surfaces:

1. Python API
2. HTTP API through FastAPI
3. Terminal CLI

## Supported Observability Sources

- Pipeline Metrics Report
- Pipeline Health Report
- Pipeline Health Trend Report
- Runtime Event Report

Normalized source types:

- `metrics`
- `health`
- `trend`
- `runtime`

## Architecture

~~~text
Observability JSON Artifacts
            │
            ▼
ObservabilityArtifactLoader
            │
            ▼
LoadedArtifact[]
            │
            ▼
DashboardAggregationEngine
            │
            ▼
DashboardSnapshot
            │
            ├── DashboardQueryService
            ├── FastAPI
            ├── CLI
            └── JSON Dashboard Report
~~~

## Core Components

### Dashboard Domain Contract

Defines normalized dashboard entities:

- `DashboardSource`
- `DashboardMetric`
- `DashboardPanel`
- `DashboardSnapshot`
- `DashboardReport`

### Observability Artifact Loader

Loads JSON artifacts and provides:

- artifact type detection
- UTF-8 and JSON validation
- SHA256 checksums
- timestamp extraction
- source metadata
- batch failure isolation

### Dashboard Aggregation Engine

Transforms loaded artifacts into:

- Overview panel
- Metrics panel
- Health panel
- Trends panel
- Runtime panel
- Overall normalized dashboard status

### Dashboard Query Service

Provides immutable queries for:

- panels
- sources
- metrics
- labels
- units
- numeric ranges
- panel status and type
- dashboard summaries

### Dashboard Snapshot Builder

Coordinates:

- artifact loading
- required source validation
- aggregation
- warning and error collection
- empty snapshot generation
- dashboard report construction

### Dashboard API

Provides FastAPI endpoints for:

- health
- service information
- dashboard build
- latest dashboard
- latest snapshot
- panel listing and lookup
- metric search and lookup
- query summary
- OpenAPI documentation

### Dashboard CLI

Provides commands for:

- `build`
- `inspect`
- `validate`
- `serve`
- `version`

### JSON Dashboard Report

Physical reports include:

- build request
- load result
- dashboard report
- artifact metadata
- canonical payload SHA256
- validation and inspection metadata

## Installation

Create and activate a virtual environment:

~~~bash
python3 -m venv .venv
source .venv/bin/activate
~~~

Install the package in editable development mode:

~~~bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
~~~

Install a built wheel:

~~~bash
python -m pip install dist/pipeline_dashboard_backend-0.1.0-py3-none-any.whl
~~~

## Quality Gate

Run:

~~~bash
ruff check .
mypy src
pytest
~~~

Current verified result before release:

~~~text
Ruff: PASS
mypy: PASS
pytest: 149 passed
~~~

A non-blocking `StarletteDeprecationWarning` may appear during FastAPI
`TestClient` tests. It originates from the FastAPI/Starlette dependency
stack and does not affect runtime API operation.

## CLI Usage

Display version:

~~~bash
pipeline-dashboard-backend version
~~~

Build a dashboard report:

~~~bash
pipeline-dashboard-backend build \
  examples/metrics_report.json \
  --output reports/dashboard_report.json \
  --snapshot-id dashboard-demo
~~~

Require specific source types:

~~~bash
pipeline-dashboard-backend build \
  reports/metrics.json \
  reports/health.json \
  --require-source-type metrics \
  --require-source-type health \
  --output reports/dashboard_report.json
~~~

Inspect a report:

~~~bash
pipeline-dashboard-backend inspect \
  reports/dashboard_report.json
~~~

Validate a report:

~~~bash
pipeline-dashboard-backend validate \
  reports/dashboard_report.json
~~~

Run the API:

~~~bash
pipeline-dashboard-backend serve \
  --host 127.0.0.1 \
  --port 8000 \
  --reload
~~~

## HTTP API

Start the service:

~~~bash
uvicorn pipeline_dashboard_backend.api:app \
  --host 127.0.0.1 \
  --port 8000
~~~

Endpoints:

~~~text
GET  /health
GET  /api/v1/info
POST /api/v1/dashboard/build
GET  /api/v1/dashboard
GET  /api/v1/dashboard/snapshot
GET  /api/v1/dashboard/panels
GET  /api/v1/dashboard/panels/{panel_id}
GET  /api/v1/dashboard/metrics
GET  /api/v1/dashboard/metrics/{metric_name}
GET  /api/v1/dashboard/summary
GET  /docs
GET  /openapi.json
~~~

Swagger UI:

~~~text
http://127.0.0.1:8000/docs
~~~

## Example Source Artifact

~~~json
{
  "report_type": "metrics",
  "generated_at": "2026-07-13T18:00:00+00:00",
  "status": "healthy",
  "summary": {
    "pipeline_count": 12
  },
  "metrics": [
    {
      "name": "success_rate",
      "value": 99.0,
      "unit": "percent",
      "labels": {
        "environment": "production"
      }
    }
  ]
}
~~~

## Exit Codes

~~~text
0 = command completed successfully
1 = command or artifact I/O failure
2 = command completed but the dashboard report or validation is unsuccessful
~~~

## Security and Integrity

The MVP includes:

- SHA256 input checksums
- canonical JSON payload hashing
- output overwrite protection
- tampered payload detection
- strict request model validation
- immutable domain contracts

The MVP does not yet include:

- authentication
- authorization
- TLS termination
- persistent database storage
- distributed locking
- production rate limiting

## Non-Goals

Utility #30 does not:

- render a frontend dashboard
- execute pipelines
- mutate source artifacts
- retry failed pipelines
- perform runtime intelligence decisions
- persist dashboard history

## Repository Layout

~~~text
pipeline_dashboard_backend_mvp/
├── src/
│   └── pipeline_dashboard_backend/
├── tests/
├── examples/
├── reports/
├── docs/
├── README.md
├── CHANGELOG.md
├── RELEASE_NOTES.md
├── LICENSE
└── pyproject.toml
~~~

## Roadmap

Completed:

- M1 Bootstrap Project
- M2 Dashboard Domain Contract
- M3 Observability Artifact Loader
- M4 Dashboard Aggregation Engine
- M5 Dashboard Query Service
- M6 Dashboard Snapshot Builder
- M7 Dashboard API
- M8 CLI + JSON Dashboard Report

Current:

- M9 Packaging + README + Release Documentation

Next:

- M10 Release v0.1.0

## License

MIT License.
