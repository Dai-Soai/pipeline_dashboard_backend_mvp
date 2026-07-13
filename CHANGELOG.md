# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

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
