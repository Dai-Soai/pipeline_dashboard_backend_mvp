"""Pipeline Dashboard Backend MVP."""

from pipeline_dashboard_backend._version import __version__
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

__all__ = [
    "__version__",
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
]
