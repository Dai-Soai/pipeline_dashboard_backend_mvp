"""Pipeline Dashboard Backend MVP."""

from pipeline_dashboard_backend._version import __version__
from pipeline_dashboard_backend.aggregation import (
    AggregationError,
    AggregationResult,
    DashboardAggregationEngine,
)
from pipeline_dashboard_backend.artifact_loader import (
    ArtifactLoadResult,
    LoadedArtifact,
    ObservabilityArtifactLoader,
)
from pipeline_dashboard_backend.contracts import (
    DashboardMetric,
    DashboardPanel,
    DashboardPanelType,
    DashboardReport,
    DashboardSnapshot,
    DashboardSource,
    DashboardSourceType,
    DashboardStatus,
    JsonScalar,
    JsonValue,
)
from pipeline_dashboard_backend.exceptions import (
    ArtifactLoadError,
    ArtifactValidationError,
    DashboardBackendError,
    UnsupportedArtifactError,
)

__all__ = [
    "__version__",
    "AggregationError",
    "AggregationResult",
    "ArtifactLoadError",
    "ArtifactLoadResult",
    "ArtifactValidationError",
    "DashboardAggregationEngine",
    "DashboardBackendError",
    "DashboardMetric",
    "DashboardPanel",
    "DashboardPanelType",
    "DashboardReport",
    "DashboardSnapshot",
    "DashboardSource",
    "DashboardSourceType",
    "DashboardStatus",
    "JsonScalar",
    "JsonValue",
    "LoadedArtifact",
    "ObservabilityArtifactLoader",
    "UnsupportedArtifactError",
]
