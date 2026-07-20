from datetime import UTC, datetime
from pathlib import Path

import pytest

from pipeline_dashboard_backend import (
    DashboardMetric,
    DashboardPanel,
    DashboardPanelType,
    DashboardQueryError,
    DashboardQueryService,
    DashboardSnapshot,
    DashboardSource,
    DashboardSourceType,
    DashboardStatus,
    MetricNotFoundError,
    PanelNotFoundError,
    SourceNotFoundError,
)

NOW = datetime(2026, 7, 13, 16, 0, tzinfo=UTC)


def make_snapshot() -> DashboardSnapshot:
    metrics_source = DashboardSource(
        source_id="metrics-main",
        source_type=DashboardSourceType.METRICS,
        path=Path("reports/metrics.json"),
        collected_at=NOW,
        checksum_sha256="a" * 64,
    )
    health_source = DashboardSource(
        source_id="health-main",
        source_type=DashboardSourceType.HEALTH,
        path=Path("reports/health.json"),
        collected_at=NOW,
        checksum_sha256="b" * 64,
    )

    overview = DashboardPanel(
        panel_id="overview",
        title="Overview",
        panel_type=DashboardPanelType.OVERVIEW,
        status=DashboardStatus.DEGRADED,
        metrics=(
            DashboardMetric(
                name="artifact_count",
                value=2,
                unit="count",
            ),
        ),
        source_ids=("metrics-main", "health-main"),
    )
    metrics = DashboardPanel(
        panel_id="metrics",
        title="Pipeline Metrics",
        panel_type=DashboardPanelType.METRICS,
        status=DashboardStatus.HEALTHY,
        metrics=(
            DashboardMetric(
                name="success_rate",
                value=98.5,
                unit="percent",
                timestamp=NOW,
                labels={
                    "environment": "production",
                    "region": "vn",
                },
            ),
            DashboardMetric(
                name="average_latency_ms",
                value=24.0,
                unit="milliseconds",
                timestamp=NOW,
                labels={"environment": "production"},
            ),
        ),
        source_ids=("metrics-main",),
    )
    health = DashboardPanel(
        panel_id="health",
        title="Pipeline Health",
        panel_type=DashboardPanelType.HEALTH,
        status=DashboardStatus.DEGRADED,
        metrics=(
            DashboardMetric(
                name="failed_pipeline_count",
                value=1,
                unit="count",
                timestamp=NOW,
                labels={"environment": "production"},
            ),
            DashboardMetric(
                name="success_rate",
                value=90.0,
                unit="percent",
                timestamp=NOW,
                labels={"environment": "staging"},
            ),
        ),
        source_ids=("health-main",),
    )

    return DashboardSnapshot(
        snapshot_id="dashboard-query-test",
        generated_at=NOW,
        overall_status=DashboardStatus.DEGRADED,
        panels=(overview, metrics, health),
        sources=(metrics_source, health_source),
    )


def make_service() -> DashboardQueryService:
    return DashboardQueryService(make_snapshot())


def test_get_panel_returns_exact_panel() -> None:
    panel = make_service().get_panel("metrics")

    assert panel.title == "Pipeline Metrics"
    assert panel.panel_type is DashboardPanelType.METRICS


def test_get_panel_strips_whitespace() -> None:
    panel = make_service().get_panel("  health  ")

    assert panel.panel_id == "health"


def test_get_panel_rejects_missing_panel() -> None:
    with pytest.raises(PanelNotFoundError, match="not found"):
        make_service().get_panel("runtime")


def test_get_panel_rejects_empty_id() -> None:
    with pytest.raises(ValueError, match="panel_id"):
        make_service().get_panel("")


def test_list_panels_returns_all_panels() -> None:
    panels = make_service().list_panels()

    assert [panel.panel_id for panel in panels] == [
        "overview",
        "metrics",
        "health",
    ]


def test_list_panels_filters_by_type() -> None:
    panels = make_service().list_panels(panel_type=DashboardPanelType.HEALTH)

    assert len(panels) == 1
    assert panels[0].panel_id == "health"


def test_list_panels_filters_by_status() -> None:
    panels = make_service().list_panels(status=DashboardStatus.DEGRADED)

    assert [panel.panel_id for panel in panels] == [
        "overview",
        "health",
    ]


def test_get_source_returns_source() -> None:
    source = make_service().get_source("metrics-main")

    assert source.source_type is DashboardSourceType.METRICS


def test_get_source_rejects_missing_source() -> None:
    with pytest.raises(SourceNotFoundError, match="not found"):
        make_service().get_source("runtime-main")


def test_list_sources_preserves_requested_order() -> None:
    sources = make_service().list_sources(source_ids=("health-main", "metrics-main"))

    assert [source.source_id for source in sources] == [
        "health-main",
        "metrics-main",
    ]


def test_get_metric_returns_unique_metric_in_panel() -> None:
    match = make_service().get_metric(
        "success_rate",
        panel_id="metrics",
    )

    assert match.panel_id == "metrics"
    assert match.metric.value == 98.5


def test_get_metric_rejects_missing_metric() -> None:
    with pytest.raises(MetricNotFoundError, match="not found"):
        make_service().get_metric("event_count")


def test_get_metric_rejects_ambiguous_metric() -> None:
    with pytest.raises(DashboardQueryError, match="ambiguous"):
        make_service().get_metric("success_rate")


def test_find_metrics_filters_by_exact_name() -> None:
    matches = make_service().find_metrics(exact_name="success_rate")

    assert [match.panel_id for match in matches] == [
        "metrics",
        "health",
    ]


def test_find_metrics_filters_by_partial_name_case_insensitive() -> None:
    matches = make_service().find_metrics(name_contains="LATENCY")

    assert len(matches) == 1
    assert matches[0].metric.name == "average_latency_ms"


def test_find_metrics_filters_by_panel_type_and_status() -> None:
    matches = make_service().find_metrics(
        panel_type=DashboardPanelType.HEALTH,
        status=DashboardStatus.DEGRADED,
    )

    assert len(matches) == 2
    assert all(match.panel_id == "health" for match in matches)


def test_find_metrics_filters_by_unit_and_numeric_range() -> None:
    matches = make_service().find_metrics(
        unit="percent",
        minimum=95,
        maximum=100,
    )

    assert len(matches) == 1
    assert matches[0].metric.value == 98.5


def test_find_metrics_filters_by_labels() -> None:
    matches = make_service().find_metrics(
        labels={
            "environment": "production",
            "region": "vn",
        }
    )

    assert len(matches) == 1
    assert matches[0].metric.name == "success_rate"


def test_find_metrics_combines_filters() -> None:
    matches = make_service().find_metrics(
        name_contains="rate",
        panel_id="health",
        unit="percent",
        minimum=80,
        labels={"environment": "staging"},
    )

    assert len(matches) == 1
    assert matches[0].panel_id == "health"
    assert matches[0].metric.value == 90.0


def test_find_metrics_rejects_invalid_range() -> None:
    with pytest.raises(
        DashboardQueryError,
        match="minimum must be less",
    ):
        make_service().find_metrics(
            minimum=10,
            maximum=5,
        )


def test_find_metrics_rejects_boolean_bounds() -> None:
    with pytest.raises(TypeError, match="not bool"):
        make_service().find_metrics(minimum=True)


def test_metric_match_serialization() -> None:
    result = make_service().get_metric("average_latency_ms").to_dict()

    assert result["panel_id"] == "metrics"
    assert result["panel_type"] == "metrics"
    assert result["panel_status"] == "healthy"
    assert result["metric"]["value"] == 24.0


def test_summarize_returns_snapshot_counts() -> None:
    summary = make_service().summarize()

    assert summary.snapshot_id == "dashboard-query-test"
    assert summary.overall_status is DashboardStatus.DEGRADED
    assert summary.panel_count == 3
    assert summary.source_count == 2
    assert summary.metric_count == 5


def test_summarize_counts_panel_statuses() -> None:
    summary = make_service().summarize()

    assert summary.panel_status_counts[DashboardStatus.HEALTHY] == 1
    assert summary.panel_status_counts[DashboardStatus.DEGRADED] == 2
    assert summary.panel_status_counts[DashboardStatus.UNHEALTHY] == 0


def test_summarize_counts_panel_types() -> None:
    summary = make_service().summarize()

    assert summary.panel_type_counts[DashboardPanelType.OVERVIEW] == 1
    assert summary.panel_type_counts[DashboardPanelType.METRICS] == 1
    assert summary.panel_type_counts[DashboardPanelType.HEALTH] == 1
    assert summary.panel_type_counts[DashboardPanelType.RUNTIME] == 0


def test_query_summary_serialization() -> None:
    result = make_service().summarize().to_dict()

    assert result["snapshot_id"] == "dashboard-query-test"
    assert result["overall_status"] == "degraded"
    assert result["panel_status_counts"]["healthy"] == 1
    assert result["panel_type_counts"]["health"] == 1


def test_snapshot_property_returns_original_snapshot() -> None:
    snapshot = make_snapshot()
    service = DashboardQueryService(snapshot)

    assert service.snapshot is snapshot
