import hashlib
import json
from pathlib import Path

import pytest

from pipeline_dashboard_backend import (
    ArtifactLoadError,
    ArtifactValidationError,
    DashboardSourceType,
    ObservabilityArtifactLoader,
    UnsupportedArtifactError,
)


def write_json(path: Path, payload: object) -> bytes:
    raw_bytes = json.dumps(payload, indent=2).encode("utf-8")
    path.write_bytes(raw_bytes)
    return raw_bytes


def test_load_metrics_artifact(tmp_path: Path) -> None:
    artifact_path = tmp_path / "pipeline_metrics_report.json"
    raw_bytes = write_json(
        artifact_path,
        {
            "schema_version": "1.0",
            "report_type": "metrics",
            "generated_at": "2026-07-13T08:00:00+00:00",
            "summary": {
                "pipeline_count": 10,
                "success_rate": 98.5,
            },
        },
    )

    artifact = ObservabilityArtifactLoader().load(artifact_path)

    assert artifact.source.source_type is DashboardSourceType.METRICS
    assert artifact.source.path == artifact_path
    assert artifact.source.checksum_sha256 == hashlib.sha256(raw_bytes).hexdigest()
    assert artifact.source.collected_at.utcoffset().total_seconds() == 0
    assert artifact.schema_version == "1.0"
    assert artifact.raw_size_bytes == len(raw_bytes)
    assert artifact.warnings == ()
    assert artifact.payload["report_type"] == "metrics"


def test_load_detects_health_type_from_filename(tmp_path: Path) -> None:
    artifact_path = tmp_path / "pipeline_health_report.json"
    write_json(
        artifact_path,
        {
            "generated_at": "2026-07-13T09:00:00Z",
            "summary": {"status": "healthy"},
        },
    )

    artifact = ObservabilityArtifactLoader().load(artifact_path)

    assert artifact.source.source_type is DashboardSourceType.HEALTH
    assert artifact.source.collected_at.isoformat() == "2026-07-13T09:00:00+00:00"


def test_load_uses_explicit_source_type(tmp_path: Path) -> None:
    artifact_path = tmp_path / "custom.json"
    write_json(
        artifact_path,
        {
            "generated_at": "2026-07-13T09:30:00+00:00",
            "summary": {},
        },
    )

    artifact = ObservabilityArtifactLoader().load(
        artifact_path,
        source_type=DashboardSourceType.RUNTIME,
    )

    assert artifact.source.source_type is DashboardSourceType.RUNTIME


def test_load_uses_file_timestamp_when_artifact_timestamp_missing(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "trend_report.json"
    write_json(
        artifact_path,
        {
            "report_type": "trend",
            "summary": {"direction": "stable"},
        },
    )

    artifact = ObservabilityArtifactLoader().load(artifact_path)

    assert artifact.source.collected_at.tzinfo is not None
    assert artifact.warnings == ("artifact timestamp missing; used file modification time",)


def test_load_uses_file_timestamp_when_artifact_timestamp_invalid(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "runtime_report.json"
    write_json(
        artifact_path,
        {
            "report_type": "runtime",
            "generated_at": "not-a-timestamp",
        },
    )

    artifact = ObservabilityArtifactLoader().load(artifact_path)

    assert artifact.source.collected_at.tzinfo is not None
    assert artifact.warnings == (
        "invalid artifact timestamp 'not-a-timestamp'; used file modification time",
    )


def test_load_rejects_missing_file(tmp_path: Path) -> None:
    artifact_path = tmp_path / "missing.json"

    with pytest.raises(ArtifactLoadError, match="does not exist"):
        ObservabilityArtifactLoader().load(artifact_path)


def test_load_rejects_directory(tmp_path: Path) -> None:
    with pytest.raises(ArtifactLoadError, match="not a file"):
        ObservabilityArtifactLoader().load(tmp_path)


def test_load_rejects_non_json_extension(tmp_path: Path) -> None:
    artifact_path = tmp_path / "metrics.txt"
    artifact_path.write_text("{}", encoding="utf-8")

    with pytest.raises(ArtifactLoadError, match=r"\.json extension"):
        ObservabilityArtifactLoader().load(artifact_path)


def test_load_rejects_invalid_json(tmp_path: Path) -> None:
    artifact_path = tmp_path / "health.json"
    artifact_path.write_text("{invalid", encoding="utf-8")

    with pytest.raises(ArtifactValidationError, match="invalid JSON"):
        ObservabilityArtifactLoader().load(artifact_path)


def test_load_rejects_non_object_json_root(tmp_path: Path) -> None:
    artifact_path = tmp_path / "metrics.json"
    write_json(artifact_path, [1, 2, 3])

    with pytest.raises(ArtifactValidationError, match="root must be a JSON object"):
        ObservabilityArtifactLoader().load(artifact_path)


def test_load_rejects_unknown_artifact_type(tmp_path: Path) -> None:
    artifact_path = tmp_path / "unknown.json"
    write_json(
        artifact_path,
        {
            "generated_at": "2026-07-13T10:00:00+00:00",
            "summary": {},
        },
    )

    with pytest.raises(UnsupportedArtifactError, match="unable to identify"):
        ObservabilityArtifactLoader().load(artifact_path)


def test_load_rejects_ambiguous_artifact_type(tmp_path: Path) -> None:
    artifact_path = tmp_path / "health_metrics_report.json"
    write_json(
        artifact_path,
        {
            "generated_at": "2026-07-13T10:00:00+00:00",
        },
    )

    with pytest.raises(UnsupportedArtifactError, match="ambiguous"):
        ObservabilityArtifactLoader().load(artifact_path)


def test_source_id_is_deterministic(tmp_path: Path) -> None:
    artifact_path = tmp_path / "metrics report.json"
    write_json(
        artifact_path,
        {
            "report_type": "metrics",
            "generated_at": "2026-07-13T10:00:00+00:00",
        },
    )

    loader = ObservabilityArtifactLoader()

    first = loader.load(artifact_path)
    second = loader.load(artifact_path)

    assert first.source.source_id == second.source.source_id
    assert first.source.source_id.startswith("metrics-metrics-report-")


def test_loaded_artifact_serialization(tmp_path: Path) -> None:
    artifact_path = tmp_path / "trend.json"
    write_json(
        artifact_path,
        {
            "report_type": "trend",
            "generated_at": "2026-07-13T10:00:00+00:00",
            "summary": {"direction": "improving"},
        },
    )

    result = ObservabilityArtifactLoader().load(artifact_path).to_dict()

    assert result["source"]["source_type"] == "trend"
    assert result["payload"]["summary"] == {"direction": "improving"}
    assert result["warnings"] == []
    assert result["raw_size_bytes"] > 0


def test_load_many_success(tmp_path: Path) -> None:
    metrics_path = tmp_path / "metrics.json"
    health_path = tmp_path / "health.json"

    write_json(
        metrics_path,
        {
            "report_type": "metrics",
            "generated_at": "2026-07-13T10:00:00+00:00",
        },
    )
    write_json(
        health_path,
        {
            "report_type": "health",
            "generated_at": "2026-07-13T10:01:00+00:00",
        },
    )

    result = ObservabilityArtifactLoader().load_many([metrics_path, health_path])

    assert result.success is True
    assert result.loaded_count == 2
    assert result.failed_count == 0


def test_load_many_isolates_failures(tmp_path: Path) -> None:
    metrics_path = tmp_path / "metrics.json"
    missing_path = tmp_path / "missing.json"

    write_json(
        metrics_path,
        {
            "report_type": "metrics",
            "generated_at": "2026-07-13T10:00:00+00:00",
        },
    )

    result = ObservabilityArtifactLoader().load_many([metrics_path, missing_path])

    assert result.success is False
    assert result.loaded_count == 1
    assert result.failed_count == 1
    assert "does not exist" in result.errors[0]


def test_load_many_raises_when_failure_isolation_disabled(
    tmp_path: Path,
) -> None:
    missing_path = tmp_path / "missing.json"

    with pytest.raises(ArtifactLoadError, match="does not exist"):
        ObservabilityArtifactLoader().load_many(
            [missing_path],
            continue_on_error=False,
        )


def test_load_result_serialization(tmp_path: Path) -> None:
    artifact_path = tmp_path / "runtime.json"
    write_json(
        artifact_path,
        {
            "report_type": "runtime",
            "generated_at": "2026-07-13T10:00:00+00:00",
        },
    )

    result = ObservabilityArtifactLoader().load_many([artifact_path]).to_dict()

    assert result["success"] is True
    assert result["loaded_count"] == 1
    assert result["failed_count"] == 0
    assert result["requested_paths"] == [str(artifact_path)]
