"""High-level dashboard snapshot building workflow."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pipeline_dashboard_backend._version import __version__
from pipeline_dashboard_backend.aggregation import (
    DashboardAggregationEngine,
)
from pipeline_dashboard_backend.artifact_loader import (
    ArtifactLoadResult,
    LoadedArtifact,
    ObservabilityArtifactLoader,
)
from pipeline_dashboard_backend.contracts import (
    DashboardPanel,
    DashboardPanelType,
    DashboardReport,
    DashboardSnapshot,
    DashboardSourceType,
    DashboardStatus,
    JsonValue,
)
from pipeline_dashboard_backend.exceptions import DashboardBackendError


class DashboardBuildError(DashboardBackendError):
    """Raised when a dashboard report cannot be built."""


@dataclass(frozen=True, slots=True)
class DashboardBuildRequest:
    """Configuration for one dashboard build operation."""

    artifact_paths: tuple[Path, ...]
    generated_at: datetime | None = None
    snapshot_id: str | None = None
    continue_on_error: bool = True
    require_source_types: frozenset[DashboardSourceType] = frozenset()
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if not self.artifact_paths:
            raise ValueError("artifact_paths must contain at least one path")

        if len(set(self.artifact_paths)) != len(self.artifact_paths):
            raise ValueError("artifact_paths must be unique")

        if self.generated_at is not None:
            if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
                raise ValueError("generated_at must be timezone-aware")

        if self.snapshot_id is not None and not self.snapshot_id.strip():
            raise ValueError("snapshot_id must be non-empty when provided")

        if not self.schema_version.strip():
            raise ValueError("schema_version must be a non-empty string")

    def to_dict(self) -> dict[str, JsonValue]:
        """Return a JSON-compatible representation."""

        required_source_types: list[JsonValue] = [
            source_type.value
            for source_type in sorted(
                self.require_source_types,
                key=lambda item: item.value,
            )
        ]

        return {
            "artifact_paths": [str(path) for path in self.artifact_paths],
            "generated_at": (
                self.generated_at.isoformat() if self.generated_at is not None else None
            ),
            "snapshot_id": self.snapshot_id,
            "continue_on_error": self.continue_on_error,
            "require_source_types": required_source_types,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class DashboardBuildResult:
    """Complete result of one dashboard build workflow."""

    request: DashboardBuildRequest
    report: DashboardReport
    load_result: ArtifactLoadResult
    built_at: datetime

    def __post_init__(self) -> None:
        if self.built_at.tzinfo is None or self.built_at.utcoffset() is None:
            raise ValueError("built_at must be timezone-aware")

    @property
    def success(self) -> bool:
        """Return the report success state."""

        return self.report.success

    def to_dict(self) -> dict[str, JsonValue]:
        """Return a JSON-compatible representation."""

        return {
            "success": self.success,
            "built_at": self.built_at.isoformat(),
            "request": self.request.to_dict(),
            "load_result": self.load_result.to_dict(),
            "report": self.report.to_dict(),
        }


class DashboardSnapshotBuilder:
    """Coordinate artifact loading and dashboard aggregation."""

    def __init__(
        self,
        *,
        loader: ObservabilityArtifactLoader | None = None,
        aggregation_engine: DashboardAggregationEngine | None = None,
    ) -> None:
        self._loader = loader or ObservabilityArtifactLoader()
        self._aggregation_engine = aggregation_engine or DashboardAggregationEngine()

    def build(
        self,
        request: DashboardBuildRequest,
    ) -> DashboardBuildResult:
        """Build a dashboard report from artifact paths."""

        built_at = datetime.now(tz=UTC)

        load_result = self._loader.load_many(
            request.artifact_paths,
            continue_on_error=request.continue_on_error,
        )

        artifacts = load_result.artifacts
        warnings = self._collect_loader_warnings(artifacts)
        errors = list(load_result.errors)

        missing_source_types = self._find_missing_source_types(
            artifacts,
            request.require_source_types,
        )

        if missing_source_types:
            formatted_types = ", ".join(source_type.value for source_type in missing_source_types)
            errors.append(f"required observability source types are missing: {formatted_types}")

        if not artifacts:
            report = self._build_empty_report(
                request=request,
                generated_at=request.generated_at or built_at,
                warnings=warnings,
                errors=errors or ["no observability artifacts were loaded"],
            )

            return DashboardBuildResult(
                request=request,
                report=report,
                load_result=load_result,
                built_at=built_at,
            )

        aggregation_result = self._aggregation_engine.aggregate(
            artifacts,
            generated_at=request.generated_at,
            snapshot_id=request.snapshot_id,
        )

        warnings.extend(aggregation_result.warnings)

        report = DashboardReport(
            schema_version=request.schema_version,
            backend_version=__version__,
            snapshot=aggregation_result.snapshot,
            warnings=self._deduplicate_messages(warnings),
            errors=self._deduplicate_messages(errors),
        )

        return DashboardBuildResult(
            request=request,
            report=report,
            load_result=load_result,
            built_at=built_at,
        )

    def build_from_paths(
        self,
        paths: Sequence[str | Path],
        *,
        generated_at: datetime | None = None,
        snapshot_id: str | None = None,
        continue_on_error: bool = True,
        require_source_types: frozenset[DashboardSourceType] = frozenset(),
        schema_version: str = "1.0",
    ) -> DashboardBuildResult:
        """Convenience wrapper for building directly from paths."""

        request = DashboardBuildRequest(
            artifact_paths=tuple(Path(path) for path in paths),
            generated_at=generated_at,
            snapshot_id=snapshot_id,
            continue_on_error=continue_on_error,
            require_source_types=require_source_types,
            schema_version=schema_version,
        )

        return self.build(request)

    def _collect_loader_warnings(
        self,
        artifacts: Sequence[LoadedArtifact],
    ) -> list[str]:
        warnings: list[str] = []

        for artifact in artifacts:
            warnings.extend(artifact.warnings)

        return warnings

    def _find_missing_source_types(
        self,
        artifacts: Sequence[LoadedArtifact],
        required_source_types: frozenset[DashboardSourceType],
    ) -> tuple[DashboardSourceType, ...]:
        available_source_types = {artifact.source.source_type for artifact in artifacts}

        return tuple(
            source_type
            for source_type in DashboardSourceType
            if (source_type in required_source_types and source_type not in available_source_types)
        )

    def _build_empty_report(
        self,
        *,
        request: DashboardBuildRequest,
        generated_at: datetime,
        warnings: Sequence[str],
        errors: Sequence[str],
    ) -> DashboardReport:
        snapshot = DashboardSnapshot(
            snapshot_id=(request.snapshot_id or "dashboard-empty"),
            generated_at=generated_at,
            overall_status=DashboardStatus.UNKNOWN,
            panels=(
                DashboardPanel(
                    panel_id="overview",
                    title="Runtime Observability Overview",
                    panel_type=DashboardPanelType.OVERVIEW,
                    status=DashboardStatus.UNKNOWN,
                    metrics=(),
                    source_ids=(),
                    summary={
                        "overall_status": "unknown",
                        "artifact_count": 0,
                        "data_panel_count": 0,
                    },
                ),
            ),
            sources=(),
            metadata={
                "artifact_count": 0,
                "panel_count": 1,
                "aggregation_version": "1.0",
                "empty_snapshot": True,
            },
        )

        return DashboardReport(
            schema_version=request.schema_version,
            backend_version=__version__,
            snapshot=snapshot,
            warnings=self._deduplicate_messages(warnings),
            errors=self._deduplicate_messages(errors),
        )

    def _deduplicate_messages(
        self,
        messages: Sequence[str],
    ) -> tuple[str, ...]:
        seen: set[str] = set()
        results: list[str] = []

        for message in messages:
            normalized = message.strip()

            if not normalized or normalized in seen:
                continue

            seen.add(normalized)
            results.append(normalized)

        return tuple(results)
