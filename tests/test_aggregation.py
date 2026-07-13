from datetime import UTC, datetime
from pathlib import Path

import pytest

from pipeline_dashboard_backend import (
    AggregationError,
    DashboardAggregationEngine,
    DashboardPanelType,
    DashboardSource,
    DashboardSourceType,
    DashboardStatus,
    LoadedArtifact,
)

NOW = datetime(2026, 7, 13, 15, 0, tzinfo=UTC)


def make_artifact(
    source_id: str,
    source_type: DashboardSourceType,
    payload: dict,
    *,
    warnings: tuple[str, ...] = (),
) -> LoadedArtifact:
    source = DashboardSource(
        source_id=source_id,
        source_type=source_type,
        path=Path(f"reports/{source_id}.json"),
        collected_at=NOW,
        checksum_sha256="a" * 64,
    )

    return LoadedArtifact(
        source=source,
        payload=payload,
        schema_version="1.0",
        warnings=warnings,
        raw_size_bytes=100,
    )


def test_aggregate_builds_overview_and_metrics_panel() -> None:
    artifact = make_artifact(
        "metrics-main",
        DashboardSourceType.METRICS,
        {
            "status": "healthy",
            "summary": {
                "pipeline_count": 10,
                "success_rate": 98.5,
            },
        },
    )

    result = DashboardAggregationEngine().aggregate(
        [artifact],
        generated_at=NOW,
    )

    assert result.snapshot.overall_status is DashboardStatus.HEALTHY
    assert len(result.snapshot.panels) == 2
    assert result.snapshot.panels[0].panel_id == "overview"
    assert result.snapshot.panels[1].panel_id == "metrics"


def test_aggregate_creates_panel_for_each_source_type() -> None:
    artifacts = [
        make_artifact(
            "metrics-main",
            DashboardSourceType.METRICS,
            {"status": "healthy", "summary": {"rate": 99}},
        ),
        make_artifact(
            "health-main",
            DashboardSourceType.HEALTH,
            {"status": "degraded", "summary": {"failed": 1}},
        ),
        make_artifact(
            "trend-main",
            DashboardSourceType.TREND,
            {"status": "stable", "summary": {"samples": 12}},
        ),
        make_artifact(
            "runtime-main",
            DashboardSourceType.RUNTIME,
            {"status": "healthy", "summary": {"events": 25}},
        ),
    ]

    snapshot = DashboardAggregationEngine().aggregate(
        artifacts,
        generated_at=NOW,
    ).snapshot

    assert [panel.panel_type for panel in snapshot.panels] == [
        DashboardPanelType.OVERVIEW,
        DashboardPanelType.METRICS,
        DashboardPanelType.HEALTH,
        DashboardPanelType.TRENDS,
        DashboardPanelType.RUNTIME,
    ]


def test_aggregate_extracts_nested_summary_metrics() -> None:
    artifact = make_artifact(
        "metrics-main",
        DashboardSourceType.METRICS,
        {
            "summary": {
                "pipeline_count": 8,
                "latency": {
                    "average_ms": 12.5,
                    "maximum_ms": 40,
                },
                "enabled": True,
            },
        },
    )

    panel = DashboardAggregationEngine().aggregate(
        [artifact],
        generated_at=NOW,
    ).snapshot.panels[1]

    names = {metric.name for metric in panel.metrics}

    assert names == {
        "pipeline_count",
        "latency.average_ms",
        "latency.maximum_ms",
    }


def test_aggregate_parses_metric_records() -> None:
    artifact = make_artifact(
        "metrics-main",
        DashboardSourceType.METRICS,
        {
            "metrics": [
                {
                    "name": "success_rate",
                    "value": 99.5,
                    "unit": "percent",
                    "labels": {"environment": "test"},
                }
            ]
        },
    )

    panel = DashboardAggregationEngine().aggregate(
        [artifact],
        generated_at=NOW,
    ).snapshot.panels[1]

    metric = panel.metrics[0]

    assert metric.name == "success_rate"
    assert metric.value == 99.5
    assert metric.unit == "percent"
    assert metric.labels["environment"] == "test"
    assert metric.labels["source_id"] == "metrics-main"


def test_aggregate_warns_about_invalid_metric_records() -> None:
    artifact = make_artifact(
        "metrics-main",
        DashboardSourceType.METRICS,
        {
            "metrics": [
                "invalid",
                {"name": "", "value": 1},
                {"name": "latency", "value": "fast"},
            ]
        },
    )

    result = DashboardAggregationEngine().aggregate(
        [artifact],
        generated_at=NOW,
    )

    assert len(result.warnings) == 3
    assert "metrics[0] is not an object" in result.warnings[0]
    assert "missing a valid name or value" in result.warnings[1]


def test_aggregate_preserves_loader_warnings() -> None:
    artifact = make_artifact(
        "runtime-main",
        DashboardSourceType.RUNTIME,
        {"summary": {"events": 2}},
        warnings=("artifact timestamp missing",),
    )

    result = DashboardAggregationEngine().aggregate(
        [artifact],
        generated_at=NOW,
    )

    assert result.warnings == ("artifact timestamp missing",)


@pytest.mark.parametrize(
    ("raw_status", "expected"),
    [
        ("healthy", DashboardStatus.HEALTHY),
        ("SUCCESS", DashboardStatus.HEALTHY),
        ("warning", DashboardStatus.DEGRADED),
        ("recovering", DashboardStatus.DEGRADED),
        ("critical", DashboardStatus.UNHEALTHY),
        ("failed", DashboardStatus.UNHEALTHY),
        ("something-new", DashboardStatus.UNKNOWN),
    ],
)
def test_aggregate_normalizes_status(
    raw_status: str,
    expected: DashboardStatus,
) -> None:
    artifact = make_artifact(
        "health-main",
        DashboardSourceType.HEALTH,
        {"status": raw_status},
    )

    snapshot = DashboardAggregationEngine().aggregate(
        [artifact],
        generated_at=NOW,
    ).snapshot

    assert snapshot.panels[1].status is expected
    assert snapshot.overall_status is expected


def test_overall_status_uses_worst_panel_status() -> None:
    artifacts = [
        make_artifact(
            "metrics-main",
            DashboardSourceType.METRICS,
            {"status": "healthy"},
        ),
        make_artifact(
            "health-main",
            DashboardSourceType.HEALTH,
            {"status": "critical"},
        ),
    ]

    snapshot = DashboardAggregationEngine().aggregate(
        artifacts,
        generated_at=NOW,
    ).snapshot

    assert snapshot.overall_status is DashboardStatus.UNHEALTHY
    assert snapshot.panels[0].status is DashboardStatus.UNHEALTHY


def test_overall_status_ignores_unknown_when_known_status_exists() -> None:
    artifacts = [
        make_artifact(
            "metrics-main",
            DashboardSourceType.METRICS,
            {"summary": {"count": 1}},
        ),
        make_artifact(
            "health-main",
            DashboardSourceType.HEALTH,
            {"status": "healthy"},
        ),
    ]

    snapshot = DashboardAggregationEngine().aggregate(
        artifacts,
        generated_at=NOW,
    ).snapshot

    assert snapshot.overall_status is DashboardStatus.HEALTHY


def test_overview_contains_aggregate_counts() -> None:
    artifacts = [
        make_artifact(
            "metrics-main",
            DashboardSourceType.METRICS,
            {"status": "healthy"},
        ),
        make_artifact(
            "health-main",
            DashboardSourceType.HEALTH,
            {"status": "degraded"},
        ),
    ]

    overview = DashboardAggregationEngine().aggregate(
        artifacts,
        generated_at=NOW,
    ).snapshot.panels[0]

    metric_values = {
        metric.name: metric.value
        for metric in overview.metrics
    }

    assert metric_values["artifact_count"] == 2
    assert metric_values["data_panel_count"] == 2
    assert metric_values["healthy_panel_count"] == 1
    assert metric_values["degraded_panel_count"] == 1


def test_duplicate_metric_names_are_namespaced() -> None:
    first = make_artifact(
        "metrics-one",
        DashboardSourceType.METRICS,
        {"summary": {"count": 1}},
    )
    second = make_artifact(
        "metrics-two",
        DashboardSourceType.METRICS,
        {"summary": {"count": 2}},
    )

    panel = DashboardAggregationEngine().aggregate(
        [first, second],
        generated_at=NOW,
    ).snapshot.panels[1]

    names = [metric.name for metric in panel.metrics]

    assert names == [
        "count",
        "metrics-two.count",
    ]


def test_snapshot_id_is_deterministic() -> None:
    artifact = make_artifact(
        "metrics-main",
        DashboardSourceType.METRICS,
        {"summary": {"count": 1}},
    )
    engine = DashboardAggregationEngine()

    first = engine.aggregate(
        [artifact],
        generated_at=NOW,
    )
    second = engine.aggregate(
        [artifact],
        generated_at=NOW,
    )

    assert first.snapshot.snapshot_id == second.snapshot.snapshot_id
    assert first.snapshot.snapshot_id.startswith("dashboard-")


def test_explicit_snapshot_id_is_preserved() -> None:
    artifact = make_artifact(
        "runtime-main",
        DashboardSourceType.RUNTIME,
        {"summary": {"events": 5}},
    )

    snapshot = DashboardAggregationEngine().aggregate(
        [artifact],
        generated_at=NOW,
        snapshot_id="snapshot-custom",
    ).snapshot

    assert snapshot.snapshot_id == "snapshot-custom"


def test_aggregate_rejects_empty_artifact_collection() -> None:
    with pytest.raises(AggregationError, match="at least one"):
        DashboardAggregationEngine().aggregate(
            [],
            generated_at=NOW,
        )


def test_aggregate_rejects_naive_generated_at() -> None:
    artifact = make_artifact(
        "metrics-main",
        DashboardSourceType.METRICS,
        {},
    )

    with pytest.raises(AggregationError, match="timezone-aware"):
        DashboardAggregationEngine().aggregate(
            [artifact],
            generated_at=datetime(2026, 7, 13, 15, 0),
        )


def test_aggregate_rejects_duplicate_source_ids() -> None:
    artifact = make_artifact(
        "metrics-main",
        DashboardSourceType.METRICS,
        {},
    )

    with pytest.raises(AggregationError, match="unique source IDs"):
        DashboardAggregationEngine().aggregate(
            [artifact, artifact],
            generated_at=NOW,
        )


def test_aggregation_result_serialization() -> None:
    artifact = make_artifact(
        "runtime-main",
        DashboardSourceType.RUNTIME,
        {
            "status": "healthy",
            "summary": {"event_count": 3},
        },
    )

    result = DashboardAggregationEngine().aggregate(
        [artifact],
        generated_at=NOW,
    ).to_dict()

    assert result["snapshot"]["overall_status"] == "healthy"
    assert result["snapshot"]["metadata"]["artifact_count"] == 1
    assert result["warnings"] == []
