"""Aggregate loaded observability artifacts into dashboard snapshots."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from pipeline_dashboard_backend.artifact_loader import LoadedArtifact
from pipeline_dashboard_backend.contracts import (
    DashboardMetric,
    DashboardPanel,
    DashboardPanelType,
    DashboardSnapshot,
    DashboardSourceType,
    DashboardStatus,
    JsonValue,
)
from pipeline_dashboard_backend.exceptions import DashboardBackendError

_PANEL_METADATA: dict[
    DashboardSourceType,
    tuple[str, DashboardPanelType],
] = {
    DashboardSourceType.METRICS: (
        "Pipeline Metrics",
        DashboardPanelType.METRICS,
    ),
    DashboardSourceType.HEALTH: (
        "Pipeline Health",
        DashboardPanelType.HEALTH,
    ),
    DashboardSourceType.TREND: (
        "Health Trends",
        DashboardPanelType.TRENDS,
    ),
    DashboardSourceType.RUNTIME: (
        "Runtime Activity",
        DashboardPanelType.RUNTIME,
    ),
}

_STATUS_SEVERITY: dict[DashboardStatus, int] = {
    DashboardStatus.UNKNOWN: 0,
    DashboardStatus.HEALTHY: 1,
    DashboardStatus.DEGRADED: 2,
    DashboardStatus.UNHEALTHY: 3,
}

_HEALTHY_TOKENS = {
    "healthy",
    "success",
    "successful",
    "ok",
    "operational",
    "available",
    "passed",
    "stable",
    "normal",
}

_DEGRADED_TOKENS = {
    "degraded",
    "warning",
    "warn",
    "partial",
    "unstable",
    "recovering",
    "retrying",
}

_UNHEALTHY_TOKENS = {
    "unhealthy",
    "failed",
    "failure",
    "error",
    "critical",
    "down",
    "unavailable",
    "blocked",
}


class AggregationError(DashboardBackendError):
    """Raised when dashboard aggregation cannot be completed."""


@dataclass(frozen=True, slots=True)
class AggregationResult:
    """Result of aggregating observability artifacts."""

    snapshot: DashboardSnapshot
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for warning in self.warnings:
            if not warning.strip():
                raise ValueError("warnings must not contain empty strings")

    def to_dict(self) -> dict[str, JsonValue]:
        """Return a JSON-compatible representation."""

        return {
            "snapshot": self.snapshot.to_dict(),
            "warnings": list(self.warnings),
        }


class DashboardAggregationEngine:
    """Build normalized dashboard snapshots from loaded artifacts."""

    def aggregate(
        self,
        artifacts: Sequence[LoadedArtifact],
        *,
        generated_at: datetime | None = None,
        snapshot_id: str | None = None,
    ) -> AggregationResult:
        """Aggregate loaded artifacts into one dashboard snapshot."""

        if not artifacts:
            raise AggregationError("at least one loaded artifact is required for aggregation")

        resolved_generated_at = generated_at or datetime.now(tz=UTC)

        if resolved_generated_at.tzinfo is None or resolved_generated_at.utcoffset() is None:
            raise AggregationError("generated_at must be timezone-aware")

        self._validate_unique_sources(artifacts)

        grouped_artifacts = self._group_artifacts(artifacts)
        warnings: list[str] = []

        data_panels: list[DashboardPanel] = []

        for source_type in DashboardSourceType:
            source_artifacts = grouped_artifacts.get(source_type, ())

            if not source_artifacts:
                continue

            panel, panel_warnings = self._build_source_panel(
                source_type,
                source_artifacts,
            )
            data_panels.append(panel)
            warnings.extend(panel_warnings)

        overall_status = self._resolve_overall_status(data_panels)
        overview_panel = self._build_overview_panel(
            artifacts,
            data_panels,
            overall_status,
        )

        panels = (overview_panel, *data_panels)
        sources = tuple(artifact.source for artifact in artifacts)

        resolved_snapshot_id = snapshot_id or self._build_snapshot_id(
            artifacts,
            resolved_generated_at,
        )

        snapshot = DashboardSnapshot(
            snapshot_id=resolved_snapshot_id,
            generated_at=resolved_generated_at,
            overall_status=overall_status,
            panels=panels,
            sources=sources,
            metadata={
                "artifact_count": len(artifacts),
                "panel_count": len(panels),
                "aggregation_version": "1.0",
            },
        )

        return AggregationResult(
            snapshot=snapshot,
            warnings=tuple(warnings),
        )

    def _validate_unique_sources(
        self,
        artifacts: Sequence[LoadedArtifact],
    ) -> None:
        source_ids = [artifact.source.source_id for artifact in artifacts]

        if len(set(source_ids)) != len(source_ids):
            raise AggregationError("loaded artifacts must have unique source IDs")

    def _group_artifacts(
        self,
        artifacts: Sequence[LoadedArtifact],
    ) -> dict[DashboardSourceType, tuple[LoadedArtifact, ...]]:
        grouped: dict[DashboardSourceType, list[LoadedArtifact]] = {}

        for artifact in artifacts:
            grouped.setdefault(
                artifact.source.source_type,
                [],
            ).append(artifact)

        return {source_type: tuple(items) for source_type, items in grouped.items()}

    def _build_source_panel(
        self,
        source_type: DashboardSourceType,
        artifacts: Sequence[LoadedArtifact],
    ) -> tuple[DashboardPanel, tuple[str, ...]]:
        title, panel_type = _PANEL_METADATA[source_type]

        metrics: list[DashboardMetric] = []
        warnings: list[str] = []
        statuses: list[DashboardStatus] = []
        metric_names: set[str] = set()

        for artifact in artifacts:
            artifact_status = self._extract_status(artifact.payload)
            statuses.append(artifact_status)

            extracted_metrics, metric_warnings = self._extract_metrics(artifact)

            for metric in extracted_metrics:
                unique_metric = self._ensure_unique_metric_name(
                    metric,
                    metric_names,
                    artifact.source.source_id,
                )
                metrics.append(unique_metric)
                metric_names.add(unique_metric.name)

            warnings.extend(metric_warnings)
            warnings.extend(artifact.warnings)

        panel_status = self._worst_status(statuses)

        return (
            DashboardPanel(
                panel_id=source_type.value,
                title=title,
                panel_type=panel_type,
                status=panel_status,
                metrics=tuple(metrics),
                source_ids=tuple(artifact.source.source_id for artifact in artifacts),
                summary={
                    "artifact_count": len(artifacts),
                    "metric_count": len(metrics),
                    "status": panel_status.value,
                },
            ),
            tuple(warnings),
        )

    def _extract_metrics(
        self,
        artifact: LoadedArtifact,
    ) -> tuple[list[DashboardMetric], list[str]]:
        metrics: list[DashboardMetric] = []
        warnings: list[str] = []

        summary = artifact.payload.get("summary")

        if isinstance(summary, dict):
            metrics.extend(
                self._extract_numeric_mapping(
                    summary,
                    timestamp=artifact.source.collected_at,
                )
            )

        raw_metrics = artifact.payload.get("metrics")

        if isinstance(raw_metrics, list):
            for index, item in enumerate(raw_metrics):
                if not isinstance(item, dict):
                    warnings.append(
                        f"{artifact.source.source_id}: metrics[{index}] is not an object"
                    )
                    continue

                metric = self._parse_metric_record(
                    item,
                    artifact,
                    index,
                )

                if metric is None:
                    warnings.append(
                        f"{artifact.source.source_id}: "
                        f"metrics[{index}] is missing a valid name or value"
                    )
                    continue

                metrics.append(metric)

        return metrics, warnings

    def _extract_numeric_mapping(
        self,
        values: Mapping[str, JsonValue],
        *,
        timestamp: datetime,
        prefix: str = "",
    ) -> list[DashboardMetric]:
        metrics: list[DashboardMetric] = []

        for key, value in values.items():
            metric_name = f"{prefix}.{key}" if prefix else key

            if isinstance(value, bool):
                continue

            if isinstance(value, (int, float)):
                metrics.append(
                    DashboardMetric(
                        name=metric_name,
                        value=value,
                        timestamp=timestamp,
                    )
                )
                continue

            if isinstance(value, dict):
                metrics.extend(
                    self._extract_numeric_mapping(
                        value,
                        timestamp=timestamp,
                        prefix=metric_name,
                    )
                )

        return metrics

    def _parse_metric_record(
        self,
        item: Mapping[str, JsonValue],
        artifact: LoadedArtifact,
        index: int,
    ) -> DashboardMetric | None:
        name = item.get("name")
        value = item.get("value")

        if not isinstance(name, str) or not name.strip():
            return None

        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None

        unit_value = item.get("unit")
        unit = unit_value if isinstance(unit_value, str) else None

        labels_value = item.get("labels")
        labels: dict[str, str] = {}

        if isinstance(labels_value, dict):
            labels = {
                str(key): str(label_value)
                for key, label_value in labels_value.items()
                if str(key).strip() and str(label_value).strip()
            }

        labels.setdefault("source_id", artifact.source.source_id)
        labels.setdefault("metric_index", str(index))

        return DashboardMetric(
            name=name.strip(),
            value=value,
            unit=unit,
            timestamp=artifact.source.collected_at,
            labels=labels,
        )

    def _ensure_unique_metric_name(
        self,
        metric: DashboardMetric,
        existing_names: set[str],
        source_id: str,
    ) -> DashboardMetric:
        if metric.name not in existing_names:
            return metric

        candidate = f"{source_id}.{metric.name}"
        counter = 2

        while candidate in existing_names:
            candidate = f"{source_id}.{metric.name}.{counter}"
            counter += 1

        return DashboardMetric(
            name=candidate,
            value=metric.value,
            unit=metric.unit,
            timestamp=metric.timestamp,
            labels=metric.labels,
        )

    def _extract_status(
        self,
        payload: Mapping[str, JsonValue],
    ) -> DashboardStatus:
        candidate_keys = (
            "overall_status",
            "health_status",
            "status",
            "state",
        )

        for key in candidate_keys:
            value = payload.get(key)

            if isinstance(value, str):
                normalized = self._normalize_status(value)

                if normalized is not DashboardStatus.UNKNOWN:
                    return normalized

        for container_key in ("summary", "metadata", "health"):
            nested = payload.get(container_key)

            if not isinstance(nested, dict):
                continue

            for key in candidate_keys:
                value = nested.get(key)

                if isinstance(value, str):
                    normalized = self._normalize_status(value)

                    if normalized is not DashboardStatus.UNKNOWN:
                        return normalized

        return DashboardStatus.UNKNOWN

    def _normalize_status(self, value: str) -> DashboardStatus:
        normalized = value.strip().lower().replace("-", "_")

        if normalized in _HEALTHY_TOKENS:
            return DashboardStatus.HEALTHY

        if normalized in _DEGRADED_TOKENS:
            return DashboardStatus.DEGRADED

        if normalized in _UNHEALTHY_TOKENS:
            return DashboardStatus.UNHEALTHY

        return DashboardStatus.UNKNOWN

    def _resolve_overall_status(
        self,
        panels: Sequence[DashboardPanel],
    ) -> DashboardStatus:
        if not panels:
            return DashboardStatus.UNKNOWN

        statuses = [panel.status for panel in panels]
        known_statuses = [status for status in statuses if status is not DashboardStatus.UNKNOWN]

        if not known_statuses:
            return DashboardStatus.UNKNOWN

        return self._worst_status(known_statuses)

    def _worst_status(
        self,
        statuses: Sequence[DashboardStatus],
    ) -> DashboardStatus:
        if not statuses:
            return DashboardStatus.UNKNOWN

        return max(
            statuses,
            key=lambda status: _STATUS_SEVERITY[status],
        )

    def _build_overview_panel(
        self,
        artifacts: Sequence[LoadedArtifact],
        data_panels: Sequence[DashboardPanel],
        overall_status: DashboardStatus,
    ) -> DashboardPanel:
        status_counts = {
            status: sum(panel.status is status for panel in data_panels)
            for status in DashboardStatus
        }

        metrics = (
            DashboardMetric(
                name="artifact_count",
                value=len(artifacts),
                unit="count",
            ),
            DashboardMetric(
                name="data_panel_count",
                value=len(data_panels),
                unit="count",
            ),
            DashboardMetric(
                name="healthy_panel_count",
                value=status_counts[DashboardStatus.HEALTHY],
                unit="count",
            ),
            DashboardMetric(
                name="degraded_panel_count",
                value=status_counts[DashboardStatus.DEGRADED],
                unit="count",
            ),
            DashboardMetric(
                name="unhealthy_panel_count",
                value=status_counts[DashboardStatus.UNHEALTHY],
                unit="count",
            ),
            DashboardMetric(
                name="unknown_panel_count",
                value=status_counts[DashboardStatus.UNKNOWN],
                unit="count",
            ),
        )

        return DashboardPanel(
            panel_id="overview",
            title="Runtime Observability Overview",
            panel_type=DashboardPanelType.OVERVIEW,
            status=overall_status,
            metrics=metrics,
            source_ids=tuple(artifact.source.source_id for artifact in artifacts),
            summary={
                "overall_status": overall_status.value,
                "artifact_count": len(artifacts),
                "data_panel_count": len(data_panels),
            },
        )

    def _build_snapshot_id(
        self,
        artifacts: Sequence[LoadedArtifact],
        generated_at: datetime,
    ) -> str:
        source_identity = "|".join(
            sorted(
                f"{artifact.source.source_id}:{artifact.source.checksum_sha256 or ''}"
                for artifact in artifacts
            )
        )
        seed = f"{generated_at.isoformat()}|{source_identity}"
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]

        return f"dashboard-{digest}"
