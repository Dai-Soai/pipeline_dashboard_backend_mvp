# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

- Package distribution verification workflow.
- Comprehensive README and release documentation.
- PEP 561 `py.typed` package marker.
- License inclusion in distribution artifacts.

## [0.1.0] - 2026-07-13

### Added

- Initial project structure and packaging configuration.
- Dashboard source, metric, panel, snapshot, and report contracts.
- Normalized dashboard status and source type enumerations.
- Contract validation for IDs, timestamps, checksums, and references.
- JSON-compatible dashboard serialization.
- Observability JSON artifact loader.
- Artifact type detection for metrics, health, trend, and runtime reports.
- SHA256 source checksum and timestamp extraction.
- Batch loading with optional failure isolation.
- Dashboard aggregation engine.
- Source-specific panel generation.
- Numeric metric extraction.
- Dashboard status normalization and severity resolution.
- Runtime observability overview panel.
- Deterministic dashboard snapshot identifiers.
- Read-only dashboard query service.
- Panel, source, and metric queries.
- Dashboard snapshot builder.
- Required source type validation.
- Empty dashboard report generation.
- FastAPI dashboard service.
- Dashboard build, panel, metric, snapshot, and summary endpoints.
- OpenAPI and Swagger documentation.
- Thread-safe in-memory API state.
- Dashboard command-line interface.
- Build, inspect, validate, serve, and version commands.
- Physical JSON dashboard report artifacts.
- Canonical payload SHA256 integrity metadata.
- Artifact overwrite protection.
- Dashboard report inspection and validation.
- Tampered payload detection.
- Installed console entrypoint.
