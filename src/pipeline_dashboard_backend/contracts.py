"""Domain contracts for the Pipeline Dashboard Backend."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, TypeAlias

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


class DashboardSourceType(StrEnum):
    """Supported observability artifact types."""

    METRICS = "metrics"
    HEALTH = "health"
    TREND = "trend"
    RUNTIME = "runtime"


class DashboardPanelType(StrEnum):
    """Logical panel categories exposed by the dashboard backend."""

    OVERVIEW = "overview"
    METRICS = "metrics"
    HEALTH = "health"
    TRENDS = "trends"
    RUNTIME = "runtime"


class DashboardStatus(StrEnum):
    """Normalized dashboard health states."""

    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


def _require_non_empty(value: str, field_name: str) -> None:
    """Raise ValueError when a required string is empty."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_aware_datetime(value: datetime, field_name: str) -> None:
    """Require timezone-aware datetimes at contract boundaries."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _serialize_value(value: Any) -> JsonValue:
    """Convert supported domain values into JSON-compatible values."""

    if isinstance(value, StrEnum):
        return value.value

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, dict):
        return {str(key): _serialize_value(item) for key, item in value.items()}

    if isinstance(value, (list, tuple)):
        return [_serialize_value(item) for item in value]

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    raise TypeError(f"Unsupported value for JSON serialization: {type(value).__name__}")


@dataclass(frozen=True, slots=True)
class DashboardSource:
    """Reference to one observability artifact consumed by the backend."""

    source_id: str
    source_type: DashboardSourceType
    path: Path
    collected_at: datetime
    checksum_sha256: str | None = None
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_non_empty(self.source_id, "source_id")
        _require_aware_datetime(self.collected_at, "collected_at")

        if self.checksum_sha256 is not None:
            checksum = self.checksum_sha256.strip().lower()

            if len(checksum) != 64:
                raise ValueError("checksum_sha256 must contain exactly 64 hexadecimal characters")

            if any(character not in "0123456789abcdef" for character in checksum):
                raise ValueError("checksum_sha256 must contain only hexadecimal characters")

            object.__setattr__(self, "checksum_sha256", checksum)

    def to_dict(self) -> dict[str, JsonValue]:
        """Return a JSON-compatible representation."""

        return {
            "source_id": self.source_id,
            "source_type": self.source_type.value,
            "path": str(self.path),
            "collected_at": self.collected_at.isoformat(),
            "checksum_sha256": self.checksum_sha256,
            "metadata": _serialize_value(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class DashboardMetric:
    """Normalized metric displayed or queried through the dashboard."""

    name: str
    value: int | float
    unit: str | None = None
    timestamp: datetime | None = None
    labels: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_non_empty(self.name, "name")

        if isinstance(self.value, bool):
            raise TypeError("value must be an integer or float, not bool")

        if self.unit is not None and not self.unit.strip():
            raise ValueError("unit must be non-empty when provided")

        if self.timestamp is not None:
            _require_aware_datetime(self.timestamp, "timestamp")

        for key, value in self.labels.items():
            _require_non_empty(key, "label key")
            _require_non_empty(value, f"label value for {key!r}")

    def to_dict(self) -> dict[str, JsonValue]:
        """Return a JSON-compatible representation."""

        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "timestamp": (self.timestamp.isoformat() if self.timestamp is not None else None),
            "labels": dict(self.labels),
        }


@dataclass(frozen=True, slots=True)
class DashboardPanel:
    """A logical group of metrics and dashboard presentation data."""

    panel_id: str
    title: str
    panel_type: DashboardPanelType
    status: DashboardStatus = DashboardStatus.UNKNOWN
    metrics: tuple[DashboardMetric, ...] = ()
    source_ids: tuple[str, ...] = ()
    summary: dict[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_non_empty(self.panel_id, "panel_id")
        _require_non_empty(self.title, "title")

        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("source_ids must be unique within a panel")

        for source_id in self.source_ids:
            _require_non_empty(source_id, "source_id")

        metric_names = [metric.name for metric in self.metrics]

        if len(set(metric_names)) != len(metric_names):
            raise ValueError("metric names must be unique within a panel")

    def to_dict(self) -> dict[str, JsonValue]:
        """Return a JSON-compatible representation."""

        return {
            "panel_id": self.panel_id,
            "title": self.title,
            "panel_type": self.panel_type.value,
            "status": self.status.value,
            "metrics": [metric.to_dict() for metric in self.metrics],
            "source_ids": list(self.source_ids),
            "summary": _serialize_value(self.summary),
        }


@dataclass(frozen=True, slots=True)
class DashboardSnapshot:
    """Aggregated dashboard state at a specific point in time."""

    snapshot_id: str
    generated_at: datetime
    overall_status: DashboardStatus
    panels: tuple[DashboardPanel, ...] = ()
    sources: tuple[DashboardSource, ...] = ()
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_non_empty(self.snapshot_id, "snapshot_id")
        _require_aware_datetime(self.generated_at, "generated_at")

        panel_ids = [panel.panel_id for panel in self.panels]

        if len(set(panel_ids)) != len(panel_ids):
            raise ValueError("panel IDs must be unique within a snapshot")

        source_ids = [source.source_id for source in self.sources]

        if len(set(source_ids)) != len(source_ids):
            raise ValueError("source IDs must be unique within a snapshot")

        known_source_ids = set(source_ids)

        for panel in self.panels:
            missing_source_ids = set(panel.source_ids) - known_source_ids

            if missing_source_ids:
                missing = ", ".join(sorted(missing_source_ids))
                raise ValueError(f"panel {panel.panel_id!r} references unknown sources: {missing}")

    def to_dict(self) -> dict[str, JsonValue]:
        """Return a JSON-compatible representation."""

        return {
            "snapshot_id": self.snapshot_id,
            "generated_at": self.generated_at.isoformat(),
            "overall_status": self.overall_status.value,
            "panels": [panel.to_dict() for panel in self.panels],
            "sources": [source.to_dict() for source in self.sources],
            "metadata": _serialize_value(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class DashboardReport:
    """Top-level output contract produced by the dashboard backend."""

    schema_version: str
    backend_version: str
    snapshot: DashboardSnapshot
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty(self.schema_version, "schema_version")
        _require_non_empty(self.backend_version, "backend_version")

        for warning in self.warnings:
            _require_non_empty(warning, "warning")

        for error in self.errors:
            _require_non_empty(error, "error")

    @property
    def success(self) -> bool:
        """Return True when the report contains no errors."""

        return not self.errors

    def to_dict(self) -> dict[str, JsonValue]:
        """Return a JSON-compatible representation."""

        return {
            "schema_version": self.schema_version,
            "backend_version": self.backend_version,
            "success": self.success,
            "snapshot": self.snapshot.to_dict(),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }
