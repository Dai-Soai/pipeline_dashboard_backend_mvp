import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pipeline_dashboard_backend import (
    ArtifactLoadError,
    DashboardBuildRequest,
    DashboardSnapshotBuilder,
    DashboardSourceType,
    DashboardStatus,
)

NOW = datetime(2026, 7, 13, 17, 0, tzinfo=UTC)


def write_json(
    path: Path,
    payload: object,
) -> None:
    path.write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def test_build_request_serialization(
    tmp_path: Path,
) -> None:
    path = tmp_path / "metrics.json"

    request = DashboardBuildRequest(
        artifact_paths=(path,),
        generated_at=NOW,
        snapshot_id="snapshot-test",
        continue_on_error=False,
        require_source_types=frozenset(
            {DashboardSourceType.METRICS}
        ),
        schema_version="1.0",
    )

    result = request.to_dict()

    assert result["artifact_paths"] == [str(path)]
    assert result["generated_at"] == NOW.isoformat()
    assert result["snapshot_id"] == "snapshot-test"
    assert result["continue_on_error"] is False
    assert result["require_source_types"] == ["metrics"]


def test_build_request_rejects_empty_paths() -> None:
    with pytest.raises(ValueError, match="at least one"):
        DashboardBuildRequest(
            artifact_paths=(),
        )


def test_build_request_rejects_duplicate_paths(
    tmp_path: Path,
) -> None:
    path = tmp_path / "metrics.json"

    with pytest.raises(ValueError, match="unique"):
        DashboardBuildRequest(
            artifact_paths=(path, path),
        )


def test_build_request_rejects_naive_datetime(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        DashboardBuildRequest(
            artifact_paths=(tmp_path / "metrics.json",),
            generated_at=datetime(2026, 7, 13, 17, 0),
        )


def test_builder_builds_successful_report(
    tmp_path: Path,
) -> None:
    metrics_path = tmp_path / "metrics_report.json"
    health_path = tmp_path / "health_report.json"

    write_json(
        metrics_path,
        {
            "report_type": "metrics",
            "generated_at": "2026-07-13T16:00:00+00:00",
            "status": "healthy",
            "summary": {
                "pipeline_count": 10,
                "success_rate": 99.0,
            },
        },
    )
    write_json(
        health_path,
        {
            "report_type": "health",
            "generated_at": "2026-07-13T16:01:00+00:00",
            "status": "healthy",
            "summary": {
                "healthy_count": 10,
                "failed_count": 0,
            },
        },
    )

    result = DashboardSnapshotBuilder().build_from_paths(
        [metrics_path, health_path],
        generated_at=NOW,
    )

    assert result.success is True
    assert result.report.success is True
    assert result.report.backend_version == "0.1.0"
    assert result.report.snapshot.overall_status is DashboardStatus.HEALTHY
    assert len(result.report.snapshot.sources) == 2
    assert len(result.report.snapshot.panels) == 3


def test_builder_preserves_explicit_snapshot_id(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime.json"

    write_json(
        path,
        {
            "report_type": "runtime",
            "generated_at": "2026-07-13T16:00:00+00:00",
            "status": "healthy",
        },
    )

    result = DashboardSnapshotBuilder().build_from_paths(
        [path],
        generated_at=NOW,
        snapshot_id="dashboard-custom",
    )

    assert result.report.snapshot.snapshot_id == "dashboard-custom"


def test_builder_reports_partial_load_failure(
    tmp_path: Path,
) -> None:
    metrics_path = tmp_path / "metrics.json"
    missing_path = tmp_path / "missing.json"

    write_json(
        metrics_path,
        {
            "report_type": "metrics",
            "generated_at": "2026-07-13T16:00:00+00:00",
            "status": "healthy",
        },
    )

    result = DashboardSnapshotBuilder().build_from_paths(
        [metrics_path, missing_path],
        generated_at=NOW,
    )

    assert result.success is False
    assert result.load_result.loaded_count == 1
    assert result.load_result.failed_count == 1
    assert len(result.report.snapshot.sources) == 1
    assert "does not exist" in result.report.errors[0]


def test_builder_raises_when_failure_isolation_disabled(
    tmp_path: Path,
) -> None:
    missing_path = tmp_path / "missing.json"

    with pytest.raises(ArtifactLoadError, match="does not exist"):
        DashboardSnapshotBuilder().build_from_paths(
            [missing_path],
            continue_on_error=False,
        )


def test_builder_creates_empty_report_when_all_loads_fail(
    tmp_path: Path,
) -> None:
    first = tmp_path / "missing-one.json"
    second = tmp_path / "missing-two.json"

    result = DashboardSnapshotBuilder().build_from_paths(
        [first, second],
        generated_at=NOW,
    )

    assert result.success is False
    assert result.report.snapshot.snapshot_id == "dashboard-empty"
    assert result.report.snapshot.overall_status is DashboardStatus.UNKNOWN
    assert result.report.snapshot.metadata["empty_snapshot"] is True
    assert result.report.snapshot.sources == ()
    assert len(result.report.snapshot.panels) == 1
    assert len(result.report.errors) == 2


def test_builder_uses_custom_empty_snapshot_id(
    tmp_path: Path,
) -> None:
    result = DashboardSnapshotBuilder().build_from_paths(
        [tmp_path / "missing.json"],
        generated_at=NOW,
        snapshot_id="empty-custom",
    )

    assert result.report.snapshot.snapshot_id == "empty-custom"


def test_builder_validates_required_source_types(
    tmp_path: Path,
) -> None:
    metrics_path = tmp_path / "metrics.json"

    write_json(
        metrics_path,
        {
            "report_type": "metrics",
            "generated_at": "2026-07-13T16:00:00+00:00",
            "status": "healthy",
        },
    )

    result = DashboardSnapshotBuilder().build_from_paths(
        [metrics_path],
        generated_at=NOW,
        require_source_types=frozenset(
            {
                DashboardSourceType.METRICS,
                DashboardSourceType.HEALTH,
            }
        ),
    )

    assert result.success is False
    assert result.report.snapshot.overall_status is DashboardStatus.HEALTHY
    assert result.report.errors == (
        "required observability source types are missing: health",
    )


def test_builder_succeeds_when_required_sources_exist(
    tmp_path: Path,
) -> None:
    metrics_path = tmp_path / "metrics.json"
    health_path = tmp_path / "health.json"

    write_json(
        metrics_path,
        {
            "report_type": "metrics",
            "generated_at": "2026-07-13T16:00:00+00:00",
        },
    )
    write_json(
        health_path,
        {
            "report_type": "health",
            "generated_at": "2026-07-13T16:00:00+00:00",
        },
    )

    result = DashboardSnapshotBuilder().build_from_paths(
        [metrics_path, health_path],
        generated_at=NOW,
        require_source_types=frozenset(
            {
                DashboardSourceType.METRICS,
                DashboardSourceType.HEALTH,
            }
        ),
    )

    assert result.success is True
    assert result.report.errors == ()


def test_builder_preserves_loader_warning(
    tmp_path: Path,
) -> None:
    path = tmp_path / "trend.json"

    write_json(
        path,
        {
            "report_type": "trend",
            "summary": {
                "sample_count": 5,
            },
        },
    )

    result = DashboardSnapshotBuilder().build_from_paths(
        [path],
        generated_at=NOW,
    )

    assert result.success is True
    assert result.report.warnings == (
        "artifact timestamp missing; used file modification time",
    )


def test_builder_deduplicates_warnings(
    tmp_path: Path,
) -> None:
    first = tmp_path / "metrics_one.json"
    second = tmp_path / "metrics_two.json"

    write_json(
        first,
        {
            "report_type": "metrics",
        },
    )
    write_json(
        second,
        {
            "report_type": "metrics",
        },
    )

    result = DashboardSnapshotBuilder().build_from_paths(
        [first, second],
        generated_at=NOW,
    )

    assert result.report.warnings == (
        "artifact timestamp missing; used file modification time",
    )


def test_builder_uses_custom_schema_version(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime.json"

    write_json(
        path,
        {
            "report_type": "runtime",
            "generated_at": "2026-07-13T16:00:00+00:00",
        },
    )

    result = DashboardSnapshotBuilder().build_from_paths(
        [path],
        generated_at=NOW,
        schema_version="1.1",
    )

    assert result.report.schema_version == "1.1"


def test_build_result_serialization(
    tmp_path: Path,
) -> None:
    path = tmp_path / "health.json"

    write_json(
        path,
        {
            "report_type": "health",
            "generated_at": "2026-07-13T16:00:00+00:00",
            "status": "degraded",
        },
    )

    result = DashboardSnapshotBuilder().build_from_paths(
        [path],
        generated_at=NOW,
    ).to_dict()

    assert result["success"] is True
    assert result["request"]["artifact_paths"] == [str(path)]
    assert result["load_result"]["loaded_count"] == 1
    assert result["report"]["snapshot"]["overall_status"] == "degraded"


def test_build_result_contains_timezone_aware_built_at(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime.json"

    write_json(
        path,
        {
            "report_type": "runtime",
            "generated_at": "2026-07-13T16:00:00+00:00",
        },
    )

    result = DashboardSnapshotBuilder().build_from_paths(
        [path],
        generated_at=NOW,
    )

    assert result.built_at.tzinfo is not None
    assert result.built_at.utcoffset() is not None
