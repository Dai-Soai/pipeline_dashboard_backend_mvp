"""Read, write, inspect, and validate dashboard report artifacts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pipeline_dashboard_backend.builder import DashboardBuildResult
from pipeline_dashboard_backend.contracts import JsonValue
from pipeline_dashboard_backend.exceptions import DashboardBackendError


class DashboardReportIOError(DashboardBackendError):
    """Raised when dashboard report artifact I/O fails."""


class DashboardReportValidationError(DashboardReportIOError):
    """Raised when a dashboard report artifact is structurally invalid."""


@dataclass(frozen=True, slots=True)
class DashboardArtifactWriteResult:
    """Result of writing one dashboard report artifact."""

    path: Path
    payload_sha256: str
    size_bytes: int
    written_at: datetime

    def __post_init__(self) -> None:
        if len(self.payload_sha256) != 64:
            raise ValueError(
                "payload_sha256 must contain exactly 64 characters"
            )

        if self.size_bytes < 0:
            raise ValueError(
                "size_bytes must be greater than or equal to zero"
            )

        if (
            self.written_at.tzinfo is None
            or self.written_at.utcoffset() is None
        ):
            raise ValueError("written_at must be timezone-aware")

    def to_dict(self) -> dict[str, JsonValue]:
        """Return a JSON-compatible representation."""

        return {
            "path": str(self.path),
            "payload_sha256": self.payload_sha256,
            "size_bytes": self.size_bytes,
            "written_at": self.written_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class DashboardArtifactInspection:
    """Summary extracted from one dashboard report artifact."""

    path: Path
    artifact_type: str
    artifact_version: str
    payload_sha256: str
    calculated_payload_sha256: str
    checksum_valid: bool
    build_success: bool | None
    snapshot_id: str | None
    overall_status: str | None
    source_count: int | None
    panel_count: int | None
    warning_count: int
    error_count: int
    size_bytes: int

    def to_dict(self) -> dict[str, JsonValue]:
        """Return a JSON-compatible representation."""

        return {
            "path": str(self.path),
            "artifact_type": self.artifact_type,
            "artifact_version": self.artifact_version,
            "payload_sha256": self.payload_sha256,
            "calculated_payload_sha256": (
                self.calculated_payload_sha256
            ),
            "checksum_valid": self.checksum_valid,
            "build_success": self.build_success,
            "snapshot_id": self.snapshot_id,
            "overall_status": self.overall_status,
            "source_count": self.source_count,
            "panel_count": self.panel_count,
            "warning_count": self.warning_count,
            "error_count": self.error_count,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True, slots=True)
class DashboardArtifactValidation:
    """Validation result for one dashboard report artifact."""

    path: Path
    valid: bool
    checksum_valid: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, JsonValue]:
        """Return a JSON-compatible representation."""

        return {
            "path": str(self.path),
            "valid": self.valid,
            "checksum_valid": self.checksum_valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


class DashboardReportArtifactWriter:
    """Write dashboard build results as integrity-protected JSON artifacts."""

    artifact_type = "pipeline_dashboard_report"
    artifact_version = "1.0"

    def write(
        self,
        build_result: DashboardBuildResult,
        output_path: str | Path,
        *,
        overwrite: bool = False,
    ) -> DashboardArtifactWriteResult:
        """Write one dashboard report artifact."""

        path = Path(output_path)

        if path.exists() and not overwrite:
            raise DashboardReportIOError(
                f"output artifact already exists: {path}"
            )

        if path.exists() and not path.is_file():
            raise DashboardReportIOError(
                f"output path exists and is not a file: {path}"
            )

        if path.suffix.lower() != ".json":
            raise DashboardReportIOError(
                f"output artifact must use the .json extension: {path}"
            )

        payload = build_result.to_dict()
        payload_sha256 = self._calculate_payload_sha256(payload)
        written_at = datetime.now(tz=UTC)

        document: dict[str, JsonValue] = {
            "artifact_type": self.artifact_type,
            "artifact_version": self.artifact_version,
            "written_at": written_at.isoformat(),
            "integrity": {
                "algorithm": "sha256",
                "payload_sha256": payload_sha256,
            },
            "payload": payload,
        }

        serialized = json.dumps(
            document,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        raw_bytes = f"{serialized}\n".encode()

        try:
            path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            path.write_bytes(raw_bytes)
        except OSError as exc:
            raise DashboardReportIOError(
                f"unable to write dashboard artifact {path}: {exc}"
            ) from exc

        return DashboardArtifactWriteResult(
            path=path,
            payload_sha256=payload_sha256,
            size_bytes=len(raw_bytes),
            written_at=written_at,
        )

    def _calculate_payload_sha256(
        self,
        payload: Mapping[str, Any],
    ) -> str:
        canonical_payload = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

        return hashlib.sha256(canonical_payload).hexdigest()


class DashboardReportArtifactReader:
    """Read, inspect, and validate dashboard report artifacts."""

    expected_artifact_type = "pipeline_dashboard_report"
    supported_artifact_versions = frozenset({"1.0"})

    def read(
        self,
        path: str | Path,
    ) -> dict[str, JsonValue]:
        """Read one dashboard report artifact."""

        artifact_path = Path(path)

        if not artifact_path.exists():
            raise DashboardReportIOError(
                f"dashboard artifact does not exist: {artifact_path}"
            )

        if not artifact_path.is_file():
            raise DashboardReportIOError(
                f"dashboard artifact path is not a file: {artifact_path}"
            )

        if artifact_path.suffix.lower() != ".json":
            raise DashboardReportIOError(
                "dashboard artifact must use the .json extension: "
                f"{artifact_path}"
            )

        try:
            raw_text = artifact_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise DashboardReportIOError(
                f"unable to read dashboard artifact {artifact_path}: {exc}"
            ) from exc
        except UnicodeDecodeError as exc:
            raise DashboardReportValidationError(
                f"dashboard artifact is not valid UTF-8: {artifact_path}"
            ) from exc

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise DashboardReportValidationError(
                "dashboard artifact contains invalid JSON at "
                f"line {exc.lineno}, column {exc.colno}: {artifact_path}"
            ) from exc

        if not isinstance(parsed, dict):
            raise DashboardReportValidationError(
                f"dashboard artifact root must be an object: {artifact_path}"
            )

        return self._normalize_mapping(parsed)

    def inspect(
        self,
        path: str | Path,
    ) -> DashboardArtifactInspection:
        """Inspect one dashboard report artifact."""

        artifact_path = Path(path)
        document = self.read(artifact_path)

        artifact_type = self._required_string(
            document,
            "artifact_type",
        )
        artifact_version = self._required_string(
            document,
            "artifact_version",
        )
        payload = self._required_mapping(
            document,
            "payload",
        )
        integrity = self._required_mapping(
            document,
            "integrity",
        )
        payload_sha256 = self._required_string(
            integrity,
            "payload_sha256",
        )
        calculated_checksum = self._calculate_payload_sha256(
            payload
        )

        report = payload.get("report")
        snapshot: Mapping[str, JsonValue] = {}
        warnings: list[JsonValue] = []
        errors: list[JsonValue] = []

        if isinstance(report, dict):
            snapshot_value = report.get("snapshot")

            if isinstance(snapshot_value, dict):
                snapshot = snapshot_value

            warnings_value = report.get("warnings")

            if isinstance(warnings_value, list):
                warnings = warnings_value

            errors_value = report.get("errors")

            if isinstance(errors_value, list):
                errors = errors_value

        sources = snapshot.get("sources")
        panels = snapshot.get("panels")

        return DashboardArtifactInspection(
            path=artifact_path,
            artifact_type=artifact_type,
            artifact_version=artifact_version,
            payload_sha256=payload_sha256,
            calculated_payload_sha256=calculated_checksum,
            checksum_valid=(
                payload_sha256 == calculated_checksum
            ),
            build_success=self._optional_bool(
                payload.get("success")
            ),
            snapshot_id=self._optional_string(
                snapshot.get("snapshot_id")
            ),
            overall_status=self._optional_string(
                snapshot.get("overall_status")
            ),
            source_count=(
                len(sources)
                if isinstance(sources, list)
                else None
            ),
            panel_count=(
                len(panels)
                if isinstance(panels, list)
                else None
            ),
            warning_count=len(warnings),
            error_count=len(errors),
            size_bytes=artifact_path.stat().st_size,
        )

    def validate(
        self,
        path: str | Path,
    ) -> DashboardArtifactValidation:
        """Validate artifact structure, version, and payload checksum."""

        artifact_path = Path(path)
        errors: list[str] = []
        warnings: list[str] = []
        checksum_valid = False

        try:
            inspection = self.inspect(artifact_path)
        except DashboardReportIOError as exc:
            return DashboardArtifactValidation(
                path=artifact_path,
                valid=False,
                checksum_valid=False,
                errors=(str(exc),),
            )

        if (
            inspection.artifact_type
            != self.expected_artifact_type
        ):
            errors.append(
                "unsupported artifact type: "
                f"{inspection.artifact_type}"
            )

        if (
            inspection.artifact_version
            not in self.supported_artifact_versions
        ):
            errors.append(
                "unsupported artifact version: "
                f"{inspection.artifact_version}"
            )

        checksum_valid = inspection.checksum_valid

        if not checksum_valid:
            errors.append("dashboard payload checksum mismatch")

        if inspection.snapshot_id is None:
            errors.append(
                "dashboard snapshot_id is missing"
            )

        if inspection.overall_status is None:
            errors.append(
                "dashboard overall_status is missing"
            )

        if inspection.build_success is False:
            warnings.append(
                "dashboard build completed with report errors"
            )

        return DashboardArtifactValidation(
            path=artifact_path,
            valid=not errors,
            checksum_valid=checksum_valid,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

    def _calculate_payload_sha256(
        self,
        payload: Mapping[str, JsonValue],
    ) -> str:
        canonical_payload = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

        return hashlib.sha256(canonical_payload).hexdigest()

    def _required_string(
        self,
        mapping: Mapping[str, JsonValue],
        key: str,
    ) -> str:
        value = mapping.get(key)

        if not isinstance(value, str) or not value.strip():
            raise DashboardReportValidationError(
                f"dashboard artifact field {key!r} "
                "must be a non-empty string"
            )

        return value.strip()

    def _required_mapping(
        self,
        mapping: Mapping[str, JsonValue],
        key: str,
    ) -> dict[str, JsonValue]:
        value = mapping.get(key)

        if not isinstance(value, dict):
            raise DashboardReportValidationError(
                f"dashboard artifact field {key!r} "
                "must be an object"
            )

        return value

    def _optional_string(
        self,
        value: JsonValue,
    ) -> str | None:
        if isinstance(value, str) and value.strip():
            return value

        return None

    def _optional_bool(
        self,
        value: JsonValue,
    ) -> bool | None:
        if isinstance(value, bool):
            return value

        return None

    def _normalize_mapping(
        self,
        mapping: Mapping[str, Any],
    ) -> dict[str, JsonValue]:
        return {
            str(key): self._normalize_value(value)
            for key, value in mapping.items()
        }

    def _normalize_value(
        self,
        value: Any,
    ) -> JsonValue:
        if value is None or isinstance(
            value,
            (str, int, float, bool),
        ):
            return value

        if isinstance(value, Mapping):
            return self._normalize_mapping(value)

        if isinstance(value, list):
            return [
                self._normalize_value(item)
                for item in value
            ]

        raise DashboardReportValidationError(
            "dashboard artifact contains unsupported value: "
            f"{type(value).__name__}"
        )
