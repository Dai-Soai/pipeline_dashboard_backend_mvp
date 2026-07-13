# Pipeline Dashboard Backend v0.1.0

## Release Status

Pre-release documentation for M10.

Utility #30 of RADAR_SERVICE.

## Overview

Pipeline Dashboard Backend v0.1.0 provides an artifact-first runtime
observability backend for RADAR_SERVICE.

The release converts metrics, health, trend, and runtime JSON artifacts into
normalized dashboard snapshots that can be accessed through Python, HTTP, CLI,
and physical JSON reports.

## Major Capabilities

- Dashboard domain contracts
- Observability artifact loading
- Artifact type detection
- SHA256 source checksums
- Timestamp extraction and fallback
- Dashboard aggregation
- Normalized health status resolution
- Overview, metrics, health, trends, and runtime panels
- Read-only dashboard query service
- Dashboard snapshot builder
- FastAPI HTTP service
- OpenAPI and Swagger documentation
- Terminal CLI
- Physical JSON dashboard report artifacts
- Canonical payload checksum
- Artifact inspection and validation
- Tampered payload detection
- Typed package marker

## CLI Commands

~~~text
pipeline-dashboard-backend build
pipeline-dashboard-backend inspect
pipeline-dashboard-backend validate
pipeline-dashboard-backend serve
pipeline-dashboard-backend version
~~~

## API Endpoints

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
~~~

## Verified Quality Gate

~~~text
Ruff: PASS
mypy: PASS
pytest: 149 passed
~~~

## Known Dependency Warning

FastAPI `TestClient` currently emits a non-blocking
`StarletteDeprecationWarning` related to the dependency transition from
`httpx`.

Verified environment during development:

~~~text
FastAPI:   0.139.0
Starlette: 1.3.1
httpx:     0.28.1
~~~

The warning:

- originates from the FastAPI/Starlette test dependency stack
- does not cause test failure
- does not affect Uvicorn runtime operation
- is not hidden with a warning filter
- does not trigger installation of an unverified replacement package

Dependency migration will occur only after an official, stable compatibility
path is confirmed.

## Current Limitations

- Dashboard state is stored in memory.
- Restarting the API clears the latest snapshot.
- No authentication or authorization.
- No frontend dashboard.
- No persistent historical snapshot database.
- No production deployment configuration.
- No Docker or systemd service definition yet.

## Compatibility

- Python 3.11+
- Linux-first development and verification
- FastAPI ASGI application
- Uvicorn runtime server

## Distribution Artifacts

M10 will produce:

- Python wheel
- Source distribution
- Git tag `v0.1.0`
- GitHub Release
- Markdown snapshot
- YAML snapshot

## Upgrade Notes

This is the first public MVP release. There is no previous version requiring
migration.

## Release Decision

Status before M10:

~~~text
UNLOCKED / RELEASE CANDIDATE
~~~

The utility becomes `LOCKED` only after package verification, Git tag,
GitHub Release, snapshot generation, and snapshot repository push.
