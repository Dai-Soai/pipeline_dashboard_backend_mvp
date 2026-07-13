# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

- High-level dashboard snapshot builder.
- Dashboard build request and result contracts.
- End-to-end artifact loading and aggregation workflow.
- Partial artifact failure isolation.
- Required source type validation.
- Empty dashboard report generation.
- Build warning and error deduplication.

- Read-only dashboard query service.
- Panel and source lookup by stable identifiers.
- Panel filtering by type and normalized status.
- Exact and partial dashboard metric search.
- Metric filtering by panel, unit, numeric range, and labels.
- Ambiguous metric detection.
- Dashboard query summary and panel distribution counts.
- Initial project structure and packaging configuration.
- Dashboard source, metric, panel, snapshot, and report contracts.
- Normalized dashboard status and source type enumerations.
- Contract validation for IDs, timestamps, checksums, and references.
- JSON-compatible serialization for dashboard domain contracts.
- Observability JSON artifact loader.
- Artifact type detection for metrics, health, trend, and runtime reports.
- SHA256 checksum, timestamp extraction, and source metadata.
- Batch artifact loading with optional failure isolation.
- Dashboard backend exception hierarchy.
- Dashboard aggregation engine.
- Source-specific dashboard panel generation.
- Numeric metric extraction from summaries and metric records.
- Dashboard status normalization and severity resolution.
- Runtime observability overview panel.
- Deterministic dashboard snapshot identifiers.
- Aggregation warnings and invalid metric isolation.
- FastAPI dashboard service.
- Thread-safe in-memory dashboard state.
- Dashboard build HTTP endpoint.
- Latest dashboard and snapshot endpoints.
- Panel listing and lookup endpoints.
- Metric search and lookup endpoints.
- Dashboard query summary endpoint.
- Health, service information, and OpenAPI endpoints.
