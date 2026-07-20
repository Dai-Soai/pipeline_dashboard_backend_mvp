"""Read-only query services for dashboard snapshots."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pipeline_dashboard_backend.contracts import (
    DashboardMetric,
    DashboardPanel,
    DashboardPanelType,
    DashboardSnapshot,
    DashboardSource,
    DashboardStatus,
    JsonValue,
)
from pipeline_dashboard_backend.exceptions import DashboardBackendError


class DashboardQueryError(DashboardBackendError):
    """Base exception for dashboard query failures."""


class PanelNotFoundError(DashboardQueryError):
    """Raised when a requested dashboard panel cannot be found."""


class MetricNotFoundError(DashboardQueryError):
    """Raised when a requested dashboard metric cannot be found."""


class SourceNotFoundError(DashboardQueryError):
    """Raised when a requested dashboard source cannot be found."""


@dataclass(frozen=True, slots=True)
class MetricMatch:
    """A metric together with the panel that contains it."""

    panel_id: str
    panel_title: str
    panel_type: DashboardPanelType
    panel_status: DashboardStatus
    metric: DashboardMetric

    def to_dict(self) -> dict[str, JsonValue]:
        """Return a JSON-compatible representation."""

        return {
            "panel_id": self.panel_id,
            "panel_title": self.panel_title,
            "panel_type": self.panel_type.value,
            "panel_status": self.panel_status.value,
            "metric": self.metric.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class DashboardQuerySummary:
    """High-level summary calculated from a dashboard snapshot."""

    snapshot_id: str
    overall_status: DashboardStatus
    panel_count: int
    source_count: int
    metric_count: int
    panel_status_counts: Mapping[DashboardStatus, int]
    panel_type_counts: Mapping[DashboardPanelType, int]

    def __post_init__(self) -> None:
        if not self.snapshot_id.strip():
            raise ValueError("snapshot_id must be a non-empty string")

        for field_name, value in (
            ("panel_count", self.panel_count),
            ("source_count", self.source_count),
            ("metric_count", self.metric_count),
        ):
            if value < 0:
                raise ValueError(f"{field_name} must be greater than or equal to zero")

        for status, count in self.panel_status_counts.items():
            if count < 0:
                raise ValueError(f"panel status count for {status.value!r} must not be negative")

        for panel_type, count in self.panel_type_counts.items():
            if count < 0:
                raise ValueError(f"panel type count for {panel_type.value!r} must not be negative")

    def to_dict(self) -> dict[str, JsonValue]:
        """Return a JSON-compatible representation."""

        return {
            "snapshot_id": self.snapshot_id,
            "overall_status": self.overall_status.value,
            "panel_count": self.panel_count,
            "source_count": self.source_count,
            "metric_count": self.metric_count,
            "panel_status_counts": {
                status.value: count for status, count in self.panel_status_counts.items()
            },
            "panel_type_counts": {
                panel_type.value: count for panel_type, count in self.panel_type_counts.items()
            },
        }


class DashboardQueryService:
    """Provide immutable lookup and filtering operations for one snapshot."""

    def __init__(self, snapshot: DashboardSnapshot) -> None:
        self._snapshot = snapshot
        self._panels_by_id = {panel.panel_id: panel for panel in snapshot.panels}
        self._sources_by_id = {source.source_id: source for source in snapshot.sources}

    @property
    def snapshot(self) -> DashboardSnapshot:
        """Return the underlying immutable snapshot."""

        return self._snapshot

    def get_panel(self, panel_id: str) -> DashboardPanel:
        """Return one panel by exact panel ID."""

        normalized_panel_id = self._require_non_empty(
            panel_id,
            "panel_id",
        )

        try:
            return self._panels_by_id[normalized_panel_id]
        except KeyError as exc:
            raise PanelNotFoundError(f"dashboard panel not found: {normalized_panel_id}") from exc

    def list_panels(
        self,
        *,
        panel_type: DashboardPanelType | None = None,
        status: DashboardStatus | None = None,
    ) -> tuple[DashboardPanel, ...]:
        """List panels with optional type and status filters."""

        panels = self._snapshot.panels

        if panel_type is not None:
            panels = tuple(panel for panel in panels if panel.panel_type is panel_type)

        if status is not None:
            panels = tuple(panel for panel in panels if panel.status is status)

        return tuple(panels)

    def get_source(self, source_id: str) -> DashboardSource:
        """Return one source by exact source ID."""

        normalized_source_id = self._require_non_empty(
            source_id,
            "source_id",
        )

        try:
            return self._sources_by_id[normalized_source_id]
        except KeyError as exc:
            raise SourceNotFoundError(
                f"dashboard source not found: {normalized_source_id}"
            ) from exc

    def list_sources(
        self,
        *,
        source_ids: Sequence[str] | None = None,
    ) -> tuple[DashboardSource, ...]:
        """List all sources or a requested ordered subset."""

        if source_ids is None:
            return self._snapshot.sources

        results: list[DashboardSource] = []

        for source_id in source_ids:
            results.append(self.get_source(source_id))

        return tuple(results)

    def get_metric(
        self,
        name: str,
        *,
        panel_id: str | None = None,
    ) -> MetricMatch:
        """Return one exact metric match.

        Raise MetricNotFoundError when no match exists and DashboardQueryError
        when the metric name is ambiguous across multiple panels.
        """

        normalized_name = self._require_non_empty(name, "name")
        matches = self.find_metrics(
            exact_name=normalized_name,
            panel_id=panel_id,
        )

        if not matches:
            location = f" in panel {panel_id!r}" if panel_id is not None else ""
            raise MetricNotFoundError(f"dashboard metric not found: {normalized_name}{location}")

        if len(matches) > 1:
            panel_ids = ", ".join(match.panel_id for match in matches)
            raise DashboardQueryError(
                f"dashboard metric {normalized_name!r} is ambiguous across panels: {panel_ids}"
            )

        return matches[0]

    def find_metrics(
        self,
        *,
        exact_name: str | None = None,
        name_contains: str | None = None,
        panel_id: str | None = None,
        panel_type: DashboardPanelType | None = None,
        status: DashboardStatus | None = None,
        unit: str | None = None,
        minimum: int | float | None = None,
        maximum: int | float | None = None,
        labels: Mapping[str, str] | None = None,
    ) -> tuple[MetricMatch, ...]:
        """Find metrics using cumulative filters."""

        if exact_name is not None:
            exact_name = self._require_non_empty(
                exact_name,
                "exact_name",
            )

        if name_contains is not None:
            name_contains = self._require_non_empty(
                name_contains,
                "name_contains",
            )

        if panel_id is not None:
            panel_id = self._require_non_empty(
                panel_id,
                "panel_id",
            )

        if unit is not None:
            unit = self._require_non_empty(unit, "unit")

        if isinstance(minimum, bool):
            raise TypeError("minimum must be numeric, not bool")

        if isinstance(maximum, bool):
            raise TypeError("maximum must be numeric, not bool")

        if minimum is not None and maximum is not None and minimum > maximum:
            raise DashboardQueryError("minimum must be less than or equal to maximum")

        normalized_labels = self._normalize_labels(labels)
        panels = self._select_panels(
            panel_id=panel_id,
            panel_type=panel_type,
            status=status,
        )

        matches: list[MetricMatch] = []

        for panel in panels:
            for metric in panel.metrics:
                if exact_name is not None and metric.name != exact_name:
                    continue

                if name_contains is not None and name_contains.lower() not in metric.name.lower():
                    continue

                if unit is not None and metric.unit != unit:
                    continue

                if minimum is not None and metric.value < minimum:
                    continue

                if maximum is not None and metric.value > maximum:
                    continue

                if not self._labels_match(
                    metric.labels,
                    normalized_labels,
                ):
                    continue

                matches.append(
                    MetricMatch(
                        panel_id=panel.panel_id,
                        panel_title=panel.title,
                        panel_type=panel.panel_type,
                        panel_status=panel.status,
                        metric=metric,
                    )
                )

        return tuple(matches)

    def summarize(self) -> DashboardQuerySummary:
        """Calculate a high-level summary of the current snapshot."""

        panel_status_counts = {
            status: sum(panel.status is status for panel in self._snapshot.panels)
            for status in DashboardStatus
        }
        panel_type_counts = {
            panel_type: sum(panel.panel_type is panel_type for panel in self._snapshot.panels)
            for panel_type in DashboardPanelType
        }
        metric_count = sum(len(panel.metrics) for panel in self._snapshot.panels)

        return DashboardQuerySummary(
            snapshot_id=self._snapshot.snapshot_id,
            overall_status=self._snapshot.overall_status,
            panel_count=len(self._snapshot.panels),
            source_count=len(self._snapshot.sources),
            metric_count=metric_count,
            panel_status_counts=panel_status_counts,
            panel_type_counts=panel_type_counts,
        )

    def _select_panels(
        self,
        *,
        panel_id: str | None,
        panel_type: DashboardPanelType | None,
        status: DashboardStatus | None,
    ) -> tuple[DashboardPanel, ...]:
        panels: tuple[DashboardPanel, ...]

        if panel_id is not None:
            panels = (self.get_panel(panel_id),)
        else:
            panels = self._snapshot.panels

        return tuple(
            panel
            for panel in panels
            if (panel_type is None or panel.panel_type is panel_type)
            and (status is None or panel.status is status)
        )

    def _normalize_labels(
        self,
        labels: Mapping[str, str] | None,
    ) -> dict[str, str]:
        if labels is None:
            return {}

        normalized: dict[str, str] = {}

        for key, value in labels.items():
            normalized_key = self._require_non_empty(
                key,
                "label key",
            )
            normalized_value = self._require_non_empty(
                value,
                f"label value for {normalized_key!r}",
            )
            normalized[normalized_key] = normalized_value

        return normalized

    def _labels_match(
        self,
        metric_labels: Mapping[str, str],
        requested_labels: Mapping[str, str],
    ) -> bool:
        return all(metric_labels.get(key) == value for key, value in requested_labels.items())

    def _require_non_empty(
        self,
        value: str,
        field_name: str,
    ) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must be a non-empty string")

        return value.strip()
