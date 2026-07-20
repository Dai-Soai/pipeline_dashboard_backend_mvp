"""FastAPI application for the Pipeline Dashboard Backend."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from pipeline_dashboard_backend._version import __version__
from pipeline_dashboard_backend.builder import (
    DashboardBuildResult,
    DashboardSnapshotBuilder,
)
from pipeline_dashboard_backend.contracts import (
    DashboardPanelType,
    DashboardSourceType,
    DashboardStatus,
)
from pipeline_dashboard_backend.exceptions import DashboardBackendError
from pipeline_dashboard_backend.query import (
    DashboardQueryError,
    DashboardQueryService,
    MetricNotFoundError,
    PanelNotFoundError,
)


class DashboardApiBuildRequest(BaseModel):
    """HTTP request body for building one dashboard snapshot."""

    model_config = ConfigDict(extra="forbid")

    artifact_paths: list[str] = Field(min_length=1)
    generated_at: datetime | None = None
    snapshot_id: str | None = Field(default=None, min_length=1)
    continue_on_error: bool = True
    require_source_types: list[DashboardSourceType] = Field(default_factory=list)
    schema_version: str = Field(default="1.0", min_length=1)


class DashboardApiState:
    """Thread-safe in-memory state for the latest dashboard build."""

    def __init__(
        self,
        *,
        builder: DashboardSnapshotBuilder | None = None,
    ) -> None:
        self._builder = builder or DashboardSnapshotBuilder()
        self._latest_result: DashboardBuildResult | None = None
        self._lock = RLock()

    def build(
        self,
        request: DashboardApiBuildRequest,
    ) -> DashboardBuildResult:
        """Build and store the latest dashboard result."""

        result = self._builder.build_from_paths(
            [Path(path) for path in request.artifact_paths],
            generated_at=request.generated_at,
            snapshot_id=request.snapshot_id,
            continue_on_error=request.continue_on_error,
            require_source_types=frozenset(request.require_source_types),
            schema_version=request.schema_version,
        )

        with self._lock:
            self._latest_result = result

        return result

    def latest(self) -> DashboardBuildResult | None:
        """Return the latest build result."""

        with self._lock:
            return self._latest_result


def create_app(
    *,
    api_state: DashboardApiState | None = None,
) -> FastAPI:
    """Create and configure the dashboard FastAPI application."""

    state_store = api_state or DashboardApiState()

    application = FastAPI(
        title="Pipeline Dashboard Backend",
        description=("Artifact-first runtime observability dashboard API for RADAR_SERVICE."),
        version=__version__,
    )

    def require_latest_result() -> DashboardBuildResult:
        latest_result = state_store.latest()

        if latest_result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="no dashboard snapshot has been built",
            )

        return latest_result

    def query_service() -> DashboardQueryService:
        latest_result = require_latest_result()

        return DashboardQueryService(latest_result.report.snapshot)

    @application.get("/health")
    def health() -> dict[str, Any]:
        """Return basic process health."""

        return {
            "status": "ok",
            "service": "pipeline-dashboard-backend",
            "version": __version__,
        }

    @application.get("/api/v1/info")
    def service_info() -> dict[str, Any]:
        """Return service identity and capability information."""

        return {
            "service": "pipeline-dashboard-backend",
            "version": __version__,
            "api_version": "v1",
            "state_backend": "memory",
            "capabilities": [
                "dashboard_build",
                "dashboard_snapshot",
                "panel_query",
                "metric_query",
                "query_summary",
            ],
        }

    @application.post("/api/v1/dashboard/build")
    def build_dashboard(
        request: DashboardApiBuildRequest,
    ) -> dict[str, Any]:
        """Build and retain a dashboard from observability artifacts."""

        try:
            result = state_store.build(request)
        except (DashboardBackendError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

        return result.to_dict()

    @application.get("/api/v1/dashboard")
    def get_dashboard() -> dict[str, Any]:
        """Return the latest complete dashboard build result."""

        return require_latest_result().to_dict()

    @application.get("/api/v1/dashboard/snapshot")
    def get_snapshot() -> dict[str, Any]:
        """Return the latest dashboard snapshot."""

        return require_latest_result().report.snapshot.to_dict()

    @application.get("/api/v1/dashboard/panels")
    def list_panels(
        panel_type: DashboardPanelType | None = None,
        panel_status: Annotated[
            DashboardStatus | None,
            Query(alias="status"),
        ] = None,
    ) -> dict[str, Any]:
        """List dashboard panels with optional filters."""

        panels = query_service().list_panels(
            panel_type=panel_type,
            status=panel_status,
        )

        return {
            "count": len(panels),
            "panels": [panel.to_dict() for panel in panels],
        }

    @application.get("/api/v1/dashboard/panels/{panel_id}")
    def get_panel(panel_id: str) -> dict[str, Any]:
        """Return one panel by ID."""

        try:
            panel = query_service().get_panel(panel_id)
        except PanelNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

        return panel.to_dict()

    @application.get("/api/v1/dashboard/metrics")
    def find_metrics(
        exact_name: str | None = None,
        name_contains: str | None = None,
        panel_id: str | None = None,
        panel_type: DashboardPanelType | None = None,
        panel_status: Annotated[
            DashboardStatus | None,
            Query(alias="status"),
        ] = None,
        unit: str | None = None,
        minimum: float | None = None,
        maximum: float | None = None,
    ) -> dict[str, Any]:
        """Search dashboard metrics using cumulative filters."""

        try:
            matches = query_service().find_metrics(
                exact_name=exact_name,
                name_contains=name_contains,
                panel_id=panel_id,
                panel_type=panel_type,
                status=panel_status,
                unit=unit,
                minimum=minimum,
                maximum=maximum,
            )
        except (DashboardQueryError, ValueError, TypeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

        return {
            "count": len(matches),
            "metrics": [match.to_dict() for match in matches],
        }

    @application.get("/api/v1/dashboard/metrics/{metric_name}")
    def get_metric(
        metric_name: str,
        panel_id: str | None = None,
    ) -> dict[str, Any]:
        """Return one exact metric match."""

        try:
            match = query_service().get_metric(
                metric_name,
                panel_id=panel_id,
            )
        except MetricNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        except DashboardQueryError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

        return match.to_dict()

    @application.get("/api/v1/dashboard/summary")
    def get_summary() -> dict[str, Any]:
        """Return the latest dashboard query summary."""

        return query_service().summarize().to_dict()

    return application


app = create_app()
