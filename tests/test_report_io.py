import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pipeline_dashboard_backend import (
    DashboardReportArtifactReader,
    DashboardReportArtifactWriter,
    DashboardReportIOError,
    DashboardReportValidationError,
    DashboardSnapshotBuilder,
)

NOW = datetime(2026, 7, 13, 18, 0, tzinfo=UTC)


def write_source_artifact(
    path: Path,
) -> None:
    path.write_text(
        json.dumps(
            {
                "report_type": "metrics",
                "generated_at": (
                    "2026-07-13T17:00:00+00:00"
                ),
                "status": "healthy",
                "summary": {
                    "pipeline_count": 5,
                },
            }
        ),
        encoding="utf-8",
    )


def make_build_result(
    tmp_path: Path,
):
    source_path = tmp_path / "metrics.json"
    write_source_artifact(source_path)

    return DashboardSnapshotBuilder().build_from_paths(
        [source_path],
        generated_at=NOW,
        snapshot_id="dashboard-report-io-test",
    )


def test_writer_creates_json_artifact(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "dashboard.json"

    result = DashboardReportArtifactWriter().write(
        make_build_result(tmp_path),
        output_path,
    )

    assert output_path.exists()
    assert result.path == output_path
    assert result.size_bytes == output_path.stat().st_size
    assert len(result.payload_sha256) == 64


def test_writer_creates_parent_directories(
    tmp_path: Path,
) -> None:
    output_path = (
        tmp_path
        / "nested"
        / "reports"
        / "dashboard.json"
    )

    DashboardReportArtifactWriter().write(
        make_build_result(tmp_path),
        output_path,
    )

    assert output_path.exists()


def test_writer_rejects_existing_artifact(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "dashboard.json"
    output_path.write_text(
        "{}",
        encoding="utf-8",
    )

    with pytest.raises(
        DashboardReportIOError,
        match="already exists",
    ):
        DashboardReportArtifactWriter().write(
            make_build_result(tmp_path),
            output_path,
        )


def test_writer_overwrites_when_enabled(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "dashboard.json"
    output_path.write_text(
        "{}",
        encoding="utf-8",
    )

    DashboardReportArtifactWriter().write(
        make_build_result(tmp_path),
        output_path,
        overwrite=True,
    )

    payload = json.loads(
        output_path.read_text(encoding="utf-8")
    )

    assert payload["artifact_type"] == (
        "pipeline_dashboard_report"
    )


def test_writer_rejects_non_json_extension(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        DashboardReportIOError,
        match=r"\.json extension",
    ):
        DashboardReportArtifactWriter().write(
            make_build_result(tmp_path),
            tmp_path / "dashboard.txt",
        )


def test_reader_reads_written_artifact(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "dashboard.json"

    DashboardReportArtifactWriter().write(
        make_build_result(tmp_path),
        output_path,
    )

    document = DashboardReportArtifactReader().read(
        output_path
    )

    assert document["artifact_type"] == (
        "pipeline_dashboard_report"
    )
    assert document["artifact_version"] == "1.0"
    assert isinstance(document["payload"], dict)


def test_reader_rejects_missing_file(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        DashboardReportIOError,
        match="does not exist",
    ):
        DashboardReportArtifactReader().read(
            tmp_path / "missing.json"
        )


def test_reader_rejects_invalid_json(
    tmp_path: Path,
) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(
        "{invalid",
        encoding="utf-8",
    )

    with pytest.raises(
        DashboardReportValidationError,
        match="invalid JSON",
    ):
        DashboardReportArtifactReader().read(path)


def test_inspection_reports_dashboard_metadata(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "dashboard.json"

    DashboardReportArtifactWriter().write(
        make_build_result(tmp_path),
        output_path,
    )

    inspection = DashboardReportArtifactReader().inspect(
        output_path
    )

    assert inspection.checksum_valid is True
    assert inspection.build_success is True
    assert inspection.snapshot_id == (
        "dashboard-report-io-test"
    )
    assert inspection.overall_status == "healthy"
    assert inspection.source_count == 1
    assert inspection.panel_count == 2
    assert inspection.error_count == 0


def test_inspection_serialization(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "dashboard.json"

    DashboardReportArtifactWriter().write(
        make_build_result(tmp_path),
        output_path,
    )

    result = DashboardReportArtifactReader().inspect(
        output_path
    ).to_dict()

    assert result["checksum_valid"] is True
    assert result["snapshot_id"] == (
        "dashboard-report-io-test"
    )
    assert result["size_bytes"] > 0


def test_validation_accepts_valid_artifact(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "dashboard.json"

    DashboardReportArtifactWriter().write(
        make_build_result(tmp_path),
        output_path,
    )

    validation = DashboardReportArtifactReader().validate(
        output_path
    )

    assert validation.valid is True
    assert validation.checksum_valid is True
    assert validation.errors == ()


def test_validation_detects_payload_tampering(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "dashboard.json"

    DashboardReportArtifactWriter().write(
        make_build_result(tmp_path),
        output_path,
    )

    document = json.loads(
        output_path.read_text(encoding="utf-8")
    )
    document["payload"]["success"] = False
    output_path.write_text(
        json.dumps(document),
        encoding="utf-8",
    )

    validation = DashboardReportArtifactReader().validate(
        output_path
    )

    assert validation.valid is False
    assert validation.checksum_valid is False
    assert validation.errors == (
        "dashboard payload checksum mismatch",
    )


def test_validation_detects_wrong_artifact_type(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "dashboard.json"

    DashboardReportArtifactWriter().write(
        make_build_result(tmp_path),
        output_path,
    )

    document = json.loads(
        output_path.read_text(encoding="utf-8")
    )
    document["artifact_type"] = "unknown_report"
    output_path.write_text(
        json.dumps(document),
        encoding="utf-8",
    )

    validation = DashboardReportArtifactReader().validate(
        output_path
    )

    assert validation.valid is False
    assert "unsupported artifact type" in (
        validation.errors[0]
    )


def test_validation_returns_error_for_missing_file(
    tmp_path: Path,
) -> None:
    validation = DashboardReportArtifactReader().validate(
        tmp_path / "missing.json"
    )

    assert validation.valid is False
    assert validation.checksum_valid is False
    assert "does not exist" in validation.errors[0]


def test_write_result_serialization(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "dashboard.json"

    result = DashboardReportArtifactWriter().write(
        make_build_result(tmp_path),
        output_path,
    ).to_dict()

    assert result["path"] == str(output_path)
    assert result["size_bytes"] > 0
    assert len(result["payload_sha256"]) == 64
