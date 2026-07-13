"""Command-line interface for the Pipeline Dashboard Backend."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import datetime
from typing import IO

import uvicorn

from pipeline_dashboard_backend._version import __version__
from pipeline_dashboard_backend.builder import DashboardSnapshotBuilder
from pipeline_dashboard_backend.contracts import DashboardSourceType, JsonValue
from pipeline_dashboard_backend.exceptions import DashboardBackendError
from pipeline_dashboard_backend.report_io import (
    DashboardReportArtifactReader,
    DashboardReportArtifactWriter,
)


def build_parser() -> argparse.ArgumentParser:
    """Create the root CLI argument parser."""

    parser = argparse.ArgumentParser(
        prog="pipeline-dashboard-backend",
        description=(
            "Build, inspect, validate, and serve " "RADAR_SERVICE dashboard reports."
        ),
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    build_command = subparsers.add_parser(
        "build",
        help="Build a dashboard report from observability artifacts.",
    )
    build_command.add_argument(
        "artifact_paths",
        nargs="+",
        help="Input observability JSON artifact paths.",
    )
    build_command.add_argument(
        "-o",
        "--output",
        default="reports/dashboard_report.json",
        help=(
            "Output dashboard JSON artifact path "
            "(default: reports/dashboard_report.json)."
        ),
    )
    build_command.add_argument(
        "--generated-at",
        help="Timezone-aware ISO-8601 dashboard generation time.",
    )
    build_command.add_argument(
        "--snapshot-id",
        help="Optional explicit dashboard snapshot ID.",
    )
    build_command.add_argument(
        "--require-source-type",
        action="append",
        choices=[source_type.value for source_type in DashboardSourceType],
        default=[],
        help=(
            "Require an observability source type. " "May be supplied multiple times."
        ),
    )
    build_command.add_argument(
        "--schema-version",
        default="1.0",
        help="Dashboard report schema version.",
    )
    build_command.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop immediately when any input artifact fails.",
    )
    build_command.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing output artifact.",
    )

    inspect_command = subparsers.add_parser(
        "inspect",
        help="Inspect a dashboard JSON report.",
    )
    inspect_command.add_argument(
        "artifact_path",
        help="Dashboard JSON artifact path.",
    )

    validate_command = subparsers.add_parser(
        "validate",
        help="Validate a dashboard JSON report.",
    )
    validate_command.add_argument(
        "artifact_path",
        help="Dashboard JSON artifact path.",
    )

    serve_command = subparsers.add_parser(
        "serve",
        help="Run the dashboard API with Uvicorn.",
    )
    serve_command.add_argument(
        "--host",
        default="127.0.0.1",
        help="Server bind host.",
    )
    serve_command.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Server bind port.",
    )
    serve_command.add_argument(
        "--reload",
        action="store_true",
        help="Enable development auto-reload.",
    )

    subparsers.add_parser(
        "version",
        help="Display the package version.",
    )

    return parser


def main(
    argv: Sequence[str] | None = None,
) -> int:
    """Run the CLI and return a process exit code."""

    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "build":
            return _run_build(args)

        if args.command == "inspect":
            return _run_inspect(args)

        if args.command == "validate":
            return _run_validate(args)

        if args.command == "serve":
            return _run_serve(args)

        if args.command == "version":
            print(__version__)
            return 0

        parser.error(f"unsupported command: {args.command}")
    except (DashboardBackendError, ValueError) as exc:
        _print_json(
            {
                "success": False,
                "error": str(exc),
            },
            stream=sys.stderr,
        )
        return 1

    return 1


def entrypoint() -> None:
    """Console script entrypoint."""

    raise SystemExit(main())


def _run_build(
    args: argparse.Namespace,
) -> int:
    generated_at = _parse_datetime(args.generated_at)
    required_source_types = frozenset(
        DashboardSourceType(value) for value in args.require_source_type
    )

    build_result = DashboardSnapshotBuilder().build_from_paths(
        args.artifact_paths,
        generated_at=generated_at,
        snapshot_id=args.snapshot_id,
        continue_on_error=not args.fail_fast,
        require_source_types=required_source_types,
        schema_version=args.schema_version,
    )

    write_result = DashboardReportArtifactWriter().write(
        build_result,
        args.output,
        overwrite=args.overwrite,
    )

    output: dict[str, JsonValue] = {
        "success": build_result.success,
        "snapshot_id": (build_result.report.snapshot.snapshot_id),
        "overall_status": (build_result.report.snapshot.overall_status.value),
        "artifact": write_result.to_dict(),
        "warning_count": len(build_result.report.warnings),
        "error_count": len(build_result.report.errors),
    }

    _print_json(output)

    return 0 if build_result.success else 2


def _run_inspect(
    args: argparse.Namespace,
) -> int:
    inspection = DashboardReportArtifactReader().inspect(args.artifact_path)
    _print_json(inspection.to_dict())

    return 0 if inspection.checksum_valid else 2


def _run_validate(
    args: argparse.Namespace,
) -> int:
    validation = DashboardReportArtifactReader().validate(args.artifact_path)
    _print_json(validation.to_dict())

    return 0 if validation.valid else 2


def _run_serve(
    args: argparse.Namespace,
) -> int:
    if not 1 <= args.port <= 65535:
        raise ValueError("port must be between 1 and 65535")

    uvicorn.run(
        "pipeline_dashboard_backend.api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )

    return 0


def _parse_datetime(
    value: str | None,
) -> datetime | None:
    if value is None:
        return None

    normalized = value.strip()

    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"invalid ISO-8601 datetime: {value}") from exc

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("generated-at must be timezone-aware")

    return parsed


def _print_json(
    payload: dict[str, JsonValue],
    *,
    stream: IO[str] | None = None,
) -> None:
    target_stream = stream if stream is not None else sys.stdout

    print(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        ),
        file=target_stream,
    )
