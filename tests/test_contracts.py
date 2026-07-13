from datetime import UTC, datetime
from pathlib import Path

import pytest

from pipeline_dashboard_backend import (
    DashboardMetric,
    DashboardPanel,
    DashboardPanelType,
    DashboardReport,
    DashboardSnapshot,
    DashboardSource,
    DashboardSourceType,
    DashboardStatus,
)

NOW = datetime(2026, 7, 13, 8, 0, tzinfo=UTC)


def make_source() -> DashboardSource:
    return DashboardSource(
        source_id="metrics-main",
        source_type=DashboardSourceType.METRICS,
        path=Path("reports/metrics_report.json"),
        collected_at=NOW,
        checksum_sha256="a" * 64,
        metadata={"utility": 26},
    )


def make_metric() -> DashboardMetric:
    return DashboardMetric(
        name="pipeline_success_rate",
        value=98.5,
        unit="percent",
        timestamp=NOW,
        labels={"environment": "production"},
    )


def make_panel() -> DashboardPanel:
    return DashboardPanel(
        panel_id="pipeline-overview",
        title="Pipeline Overview",
        panel_type=DashboardPanelType.OVERVIEW,
        status=DashboardStatus.HEALTHY,
        metrics=(make_metric(),),
        source_ids=("metrics-main",),
        summary={"pipeline_count": 12},
    )


def make_snapshot() -> DashboardSnapshot:
    return DashboardSnapshot(
        snapshot_id="snapshot-001",
        generated_at=NOW,
        overall_status=DashboardStatus.HEALTHY,
        panels=(make_panel(),),
        sources=(make_source(),),
        metadata={"environment": "production"},
    )


def test_source_serializes_to_json_compatible_dict() -> None:
    result = make_source().to_dict()

    assert result["source_id"] == "metrics-main"
    assert result["source_type"] == "metrics"
    assert result["path"] == "reports/metrics_report.json"
    assert result["collected_at"] == NOW.isoformat()
    assert result["checksum_sha256"] == "a" * 64


def test_source_normalizes_checksum_to_lowercase() -> None:
    source = DashboardSource(
        source_id="health-main",
        source_type=DashboardSourceType.HEALTH,
        path=Path("reports/health.json"),
        collected_at=NOW,
        checksum_sha256="A" * 64,
    )

    assert source.checksum_sha256 == "a" * 64


def test_source_rejects_invalid_checksum() -> None:
    with pytest.raises(ValueError, match="64 hexadecimal"):
        DashboardSource(
            source_id="invalid-source",
            source_type=DashboardSourceType.METRICS,
            path=Path("invalid.json"),
            collected_at=NOW,
            checksum_sha256="abc",
        )


def test_source_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        DashboardSource(
            source_id="metrics-main",
            source_type=DashboardSourceType.METRICS,
            path=Path("metrics.json"),
            collected_at=datetime(2026, 7, 13, 8, 0),
        )


def test_metric_serialization() -> None:
    result = make_metric().to_dict()

    assert result == {
        "name": "pipeline_success_rate",
        "value": 98.5,
        "unit": "percent",
        "timestamp": NOW.isoformat(),
        "labels": {"environment": "production"},
    }


def test_metric_rejects_boolean_value() -> None:
    with pytest.raises(TypeError, match="not bool"):
        DashboardMetric(name="invalid", value=True)


def test_metric_rejects_empty_name() -> None:
    with pytest.raises(ValueError, match="name must be a non-empty string"):
        DashboardMetric(name="", value=1)


def test_panel_serialization() -> None:
    result = make_panel().to_dict()

    assert result["panel_id"] == "pipeline-overview"
    assert result["panel_type"] == "overview"
    assert result["status"] == "healthy"
    assert result["source_ids"] == ["metrics-main"]
    assert len(result["metrics"]) == 1


def test_panel_rejects_duplicate_metric_names() -> None:
    metric = make_metric()

    with pytest.raises(ValueError, match="metric names must be unique"):
        DashboardPanel(
            panel_id="duplicate-metrics",
            title="Duplicate Metrics",
            panel_type=DashboardPanelType.METRICS,
            metrics=(metric, metric),
        )


def test_snapshot_serialization() -> None:
    result = make_snapshot().to_dict()

    assert result["snapshot_id"] == "snapshot-001"
    assert result["overall_status"] == "healthy"
    assert len(result["panels"]) == 1
    assert len(result["sources"]) == 1


def test_snapshot_rejects_duplicate_panel_ids() -> None:
    panel = make_panel()

    with pytest.raises(ValueError, match="panel IDs must be unique"):
        DashboardSnapshot(
            snapshot_id="snapshot-duplicate-panels",
            generated_at=NOW,
            overall_status=DashboardStatus.UNKNOWN,
            panels=(panel, panel),
            sources=(make_source(),),
        )


def test_snapshot_rejects_unknown_panel_source() -> None:
    panel = DashboardPanel(
        panel_id="health",
        title="Health",
        panel_type=DashboardPanelType.HEALTH,
        source_ids=("missing-source",),
    )

    with pytest.raises(ValueError, match="references unknown sources"):
        DashboardSnapshot(
            snapshot_id="snapshot-invalid-reference",
            generated_at=NOW,
            overall_status=DashboardStatus.UNKNOWN,
            panels=(panel,),
            sources=(make_source(),),
        )


def test_report_success_is_true_without_errors() -> None:
    report = DashboardReport(
        schema_version="1.0",
        backend_version="0.1.0",
        snapshot=make_snapshot(),
    )

    assert report.success is True
    assert report.to_dict()["success"] is True


def test_report_success_is_false_with_errors() -> None:
    report = DashboardReport(
        schema_version="1.0",
        backend_version="0.1.0",
        snapshot=make_snapshot(),
        errors=("metrics artifact unavailable",),
    )

    assert report.success is False
    assert report.to_dict()["errors"] == ["metrics artifact unavailable"]


def test_report_rejects_empty_schema_version() -> None:
    with pytest.raises(ValueError, match="schema_version"):
        DashboardReport(
            schema_version="",
            backend_version="0.1.0",
            snapshot=make_snapshot(),
        )
