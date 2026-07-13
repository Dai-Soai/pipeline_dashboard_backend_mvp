import json
from pathlib import Path
from unittest.mock import patch

from pipeline_dashboard_backend.cli import main


def write_metrics_artifact(
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
                    "pipeline_count": 4,
                },
            }
        ),
        encoding="utf-8",
    )


def test_version_command(
    capsys,
) -> None:
    exit_code = main(["version"])

    assert exit_code == 0
    assert capsys.readouterr().out.strip() == "0.1.0"


def test_build_command_creates_report(
    tmp_path: Path,
    capsys,
) -> None:
    source_path = tmp_path / "metrics.json"
    output_path = tmp_path / "dashboard.json"

    write_metrics_artifact(source_path)

    exit_code = main(
        [
            "build",
            str(source_path),
            "--output",
            str(output_path),
            "--generated-at",
            "2026-07-13T18:00:00+00:00",
            "--snapshot-id",
            "dashboard-cli-test",
        ]
    )

    payload = json.loads(
        capsys.readouterr().out
    )

    assert exit_code == 0
    assert output_path.exists()
    assert payload["success"] is True
    assert payload["snapshot_id"] == (
        "dashboard-cli-test"
    )


def test_build_command_returns_two_for_failed_report(
    tmp_path: Path,
    capsys,
) -> None:
    output_path = tmp_path / "dashboard.json"

    exit_code = main(
        [
            "build",
            str(tmp_path / "missing.json"),
            "--output",
            str(output_path),
        ]
    )

    payload = json.loads(
        capsys.readouterr().out
    )

    assert exit_code == 2
    assert payload["success"] is False
    assert output_path.exists()


def test_build_command_fail_fast_returns_one(
    tmp_path: Path,
    capsys,
) -> None:
    exit_code = main(
        [
            "build",
            str(tmp_path / "missing.json"),
            "--fail-fast",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert json.loads(captured.err)["success"] is False


def test_build_command_rejects_naive_datetime(
    tmp_path: Path,
    capsys,
) -> None:
    source_path = tmp_path / "metrics.json"
    write_metrics_artifact(source_path)

    exit_code = main(
        [
            "build",
            str(source_path),
            "--generated-at",
            "2026-07-13T18:00:00",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert "timezone-aware" in captured.err


def test_build_command_requires_source_type(
    tmp_path: Path,
    capsys,
) -> None:
    source_path = tmp_path / "metrics.json"
    output_path = tmp_path / "dashboard.json"

    write_metrics_artifact(source_path)

    exit_code = main(
        [
            "build",
            str(source_path),
            "--output",
            str(output_path),
            "--require-source-type",
            "health",
        ]
    )

    payload = json.loads(
        capsys.readouterr().out
    )

    assert exit_code == 2
    assert payload["success"] is False
    assert payload["error_count"] == 1


def test_build_command_protects_existing_output(
    tmp_path: Path,
    capsys,
) -> None:
    source_path = tmp_path / "metrics.json"
    output_path = tmp_path / "dashboard.json"

    write_metrics_artifact(source_path)
    output_path.write_text(
        "{}",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "build",
            str(source_path),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 1
    assert "already exists" in capsys.readouterr().err


def test_build_command_overwrites_output(
    tmp_path: Path,
    capsys,
) -> None:
    source_path = tmp_path / "metrics.json"
    output_path = tmp_path / "dashboard.json"

    write_metrics_artifact(source_path)
    output_path.write_text(
        "{}",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "build",
            str(source_path),
            "--output",
            str(output_path),
            "--overwrite",
        ]
    )

    assert exit_code == 0
    assert json.loads(
        output_path.read_text(encoding="utf-8")
    )["artifact_type"] == "pipeline_dashboard_report"

    capsys.readouterr()


def test_inspect_command(
    tmp_path: Path,
    capsys,
) -> None:
    source_path = tmp_path / "metrics.json"
    output_path = tmp_path / "dashboard.json"

    write_metrics_artifact(source_path)

    assert main(
        [
            "build",
            str(source_path),
            "--output",
            str(output_path),
        ]
    ) == 0

    capsys.readouterr()

    exit_code = main(
        ["inspect", str(output_path)]
    )
    payload = json.loads(
        capsys.readouterr().out
    )

    assert exit_code == 0
    assert payload["checksum_valid"] is True
    assert payload["source_count"] == 1


def test_validate_command_accepts_valid_report(
    tmp_path: Path,
    capsys,
) -> None:
    source_path = tmp_path / "metrics.json"
    output_path = tmp_path / "dashboard.json"

    write_metrics_artifact(source_path)

    assert main(
        [
            "build",
            str(source_path),
            "--output",
            str(output_path),
        ]
    ) == 0

    capsys.readouterr()

    exit_code = main(
        ["validate", str(output_path)]
    )
    payload = json.loads(
        capsys.readouterr().out
    )

    assert exit_code == 0
    assert payload["valid"] is True


def test_validate_command_rejects_tampered_report(
    tmp_path: Path,
    capsys,
) -> None:
    source_path = tmp_path / "metrics.json"
    output_path = tmp_path / "dashboard.json"

    write_metrics_artifact(source_path)

    assert main(
        [
            "build",
            str(source_path),
            "--output",
            str(output_path),
        ]
    ) == 0

    capsys.readouterr()

    document = json.loads(
        output_path.read_text(encoding="utf-8")
    )
    document["payload"]["success"] = False
    output_path.write_text(
        json.dumps(document),
        encoding="utf-8",
    )

    exit_code = main(
        ["validate", str(output_path)]
    )
    payload = json.loads(
        capsys.readouterr().out
    )

    assert exit_code == 2
    assert payload["valid"] is False


def test_serve_command_calls_uvicorn() -> None:
    with patch(
        "pipeline_dashboard_backend.cli.uvicorn.run"
    ) as run:
        exit_code = main(
            [
                "serve",
                "--host",
                "0.0.0.0",
                "--port",
                "9000",
                "--reload",
            ]
        )

    assert exit_code == 0
    run.assert_called_once_with(
        "pipeline_dashboard_backend.api:app",
        host="0.0.0.0",
        port=9000,
        reload=True,
    )


def test_serve_command_rejects_invalid_port(
    capsys,
) -> None:
    exit_code = main(
        [
            "serve",
            "--port",
            "70000",
        ]
    )

    assert exit_code == 1
    assert "between 1 and 65535" in (
        capsys.readouterr().err
    )
