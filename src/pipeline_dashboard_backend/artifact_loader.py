"""Load and validate RADAR_SERVICE observability artifacts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pipeline_dashboard_backend.contracts import (
    DashboardSource,
    DashboardSourceType,
    JsonValue,
)
from pipeline_dashboard_backend.exceptions import (
    ArtifactLoadError,
    ArtifactValidationError,
    DashboardBackendError,
    UnsupportedArtifactError,
)

_ARTIFACT_TYPE_KEYS: tuple[tuple[str, DashboardSourceType], ...] = (
    ("metrics", DashboardSourceType.METRICS),
    ("health", DashboardSourceType.HEALTH),
    ("trend", DashboardSourceType.TREND),
    ("runtime", DashboardSourceType.RUNTIME),
)

_TIMESTAMP_KEYS: tuple[str, ...] = (
    "generated_at",
    "collected_at",
    "created_at",
    "timestamp",
    "analyzed_at",
)


@dataclass(frozen=True, slots=True)
class LoadedArtifact:
    """One successfully loaded observability artifact."""

    source: DashboardSource
    payload: dict[str, JsonValue]
    schema_version: str | None = None
    warnings: tuple[str, ...] = ()
    raw_size_bytes: int = 0

    def __post_init__(self) -> None:
        if self.raw_size_bytes < 0:
            raise ValueError("raw_size_bytes must be greater than or equal to zero")

        for warning in self.warnings:
            if not warning.strip():
                raise ValueError("warnings must not contain empty strings")

    def to_dict(self) -> dict[str, JsonValue]:
        """Return a JSON-compatible representation."""

        return {
            "source": self.source.to_dict(),
            "payload": self.payload,
            "schema_version": self.schema_version,
            "warnings": list(self.warnings),
            "raw_size_bytes": self.raw_size_bytes,
        }


@dataclass(frozen=True, slots=True)
class ArtifactLoadResult:
    """Aggregate result for one or more artifact load attempts."""

    artifacts: tuple[LoadedArtifact, ...] = ()
    errors: tuple[str, ...] = ()
    requested_paths: tuple[Path, ...] = field(default_factory=tuple)

    @property
    def success(self) -> bool:
        """Return True when all requested artifacts loaded successfully."""

        return not self.errors and len(self.artifacts) == len(self.requested_paths)

    @property
    def loaded_count(self) -> int:
        """Number of loaded artifacts."""

        return len(self.artifacts)

    @property
    def failed_count(self) -> int:
        """Number of failed artifacts."""

        return len(self.errors)

    def to_dict(self) -> dict[str, JsonValue]:
        """Return a JSON-compatible representation."""

        return {
            "success": self.success,
            "loaded_count": self.loaded_count,
            "failed_count": self.failed_count,
            "requested_paths": [str(path) for path in self.requested_paths],
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "errors": list(self.errors),
        }


class ObservabilityArtifactLoader:
    """Load JSON observability artifacts from disk."""

    def load(
        self,
        path: str | Path,
        *,
        source_type: DashboardSourceType | None = None,
    ) -> LoadedArtifact:
        """Load one artifact from disk."""

        artifact_path = Path(path)

        if not artifact_path.exists():
            raise ArtifactLoadError(f"artifact does not exist: {artifact_path}")

        if not artifact_path.is_file():
            raise ArtifactLoadError(f"artifact path is not a file: {artifact_path}")

        if artifact_path.suffix.lower() != ".json":
            raise ArtifactLoadError(
                f"artifact must use the .json extension: {artifact_path}"
            )

        try:
            raw_bytes = artifact_path.read_bytes()
        except OSError as exc:
            raise ArtifactLoadError(
                f"unable to read artifact {artifact_path}: {exc}"
            ) from exc

        try:
            decoded = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ArtifactValidationError(
                f"artifact is not valid UTF-8: {artifact_path}"
            ) from exc

        try:
            parsed = json.loads(decoded)
        except json.JSONDecodeError as exc:
            raise ArtifactValidationError(
                f"artifact contains invalid JSON at line {exc.lineno}, "
                f"column {exc.colno}: {artifact_path}"
            ) from exc

        if not isinstance(parsed, dict):
            raise ArtifactValidationError(
                f"artifact root must be a JSON object: {artifact_path}"
            )

        payload = self._normalize_payload(parsed)
        resolved_type = source_type or self._detect_source_type(
            artifact_path,
            payload,
        )
        collected_at, timestamp_warning = self._extract_collected_at(
            artifact_path,
            payload,
        )
        checksum = hashlib.sha256(raw_bytes).hexdigest()
        schema_version = self._extract_schema_version(payload)

        warnings: list[str] = []

        if timestamp_warning is not None:
            warnings.append(timestamp_warning)

        source = DashboardSource(
            source_id=self._build_source_id(
                artifact_path,
                resolved_type,
                checksum,
            ),
            source_type=resolved_type,
            path=artifact_path,
            collected_at=collected_at,
            checksum_sha256=checksum,
            metadata={
                "filename": artifact_path.name,
                "suffix": artifact_path.suffix.lower(),
                "raw_size_bytes": len(raw_bytes),
            },
        )

        return LoadedArtifact(
            source=source,
            payload=payload,
            schema_version=schema_version,
            warnings=tuple(warnings),
            raw_size_bytes=len(raw_bytes),
        )

    def load_many(
        self,
        paths: list[str | Path] | tuple[str | Path, ...],
        *,
        continue_on_error: bool = True,
    ) -> ArtifactLoadResult:
        """Load multiple artifacts with optional failure isolation."""

        requested_paths = tuple(Path(path) for path in paths)
        artifacts: list[LoadedArtifact] = []
        errors: list[str] = []

        for path in requested_paths:
            try:
                artifacts.append(self.load(path))
            except DashboardBackendError as exc:
                if not continue_on_error:
                    raise

                errors.append(str(exc))

        return ArtifactLoadResult(
            artifacts=tuple(artifacts),
            errors=tuple(errors),
            requested_paths=requested_paths,
        )

    def _detect_source_type(
        self,
        path: Path,
        payload: Mapping[str, JsonValue],
    ) -> DashboardSourceType:
        candidates = self._collect_type_candidates(path, payload)

        if len(candidates) == 1:
            return next(iter(candidates))

        if not candidates:
            raise UnsupportedArtifactError(
                f"unable to identify observability artifact type: {path}"
            )

        candidate_values = ", ".join(
            sorted(candidate.value for candidate in candidates)
        )
        raise UnsupportedArtifactError(
            f"artifact type is ambiguous ({candidate_values}): {path}"
        )

    def _collect_type_candidates(
        self,
        path: Path,
        payload: Mapping[str, JsonValue],
    ) -> set[DashboardSourceType]:
        candidates: set[DashboardSourceType] = set()
        searchable_values: list[str] = [
            path.name.lower(),
            path.stem.lower(),
        ]

        for key in (
            "report_type",
            "artifact_type",
            "source_type",
            "kind",
            "type",
        ):
            value = payload.get(key)

            if isinstance(value, str):
                searchable_values.append(value.lower())

        metadata = payload.get("metadata")

        if isinstance(metadata, dict):
            for key in (
                "report_type",
                "artifact_type",
                "source_type",
                "kind",
                "type",
            ):
                value = metadata.get(key)

                if isinstance(value, str):
                    searchable_values.append(value.lower())

        for value in searchable_values:
            for keyword, source_type in _ARTIFACT_TYPE_KEYS:
                if keyword in value:
                    candidates.add(source_type)

        return candidates

    def _extract_collected_at(
        self,
        path: Path,
        payload: Mapping[str, JsonValue],
    ) -> tuple[datetime, str | None]:
        timestamp_value = self._find_timestamp_value(payload)

        if timestamp_value is not None:
            parsed_timestamp = self._parse_timestamp(timestamp_value)

            if parsed_timestamp is not None:
                return parsed_timestamp, None

            return (
                self._file_modified_at(path),
                f"invalid artifact timestamp {timestamp_value!r}; "
                "used file modification time",
            )

        return (
            self._file_modified_at(path),
            "artifact timestamp missing; used file modification time",
        )

    def _find_timestamp_value(
        self,
        payload: Mapping[str, JsonValue],
    ) -> str | None:
        for key in _TIMESTAMP_KEYS:
            value = payload.get(key)

            if isinstance(value, str):
                return value

        metadata = payload.get("metadata")

        if isinstance(metadata, dict):
            for key in _TIMESTAMP_KEYS:
                value = metadata.get(key)

                if isinstance(value, str):
                    return value

        summary = payload.get("summary")

        if isinstance(summary, dict):
            for key in _TIMESTAMP_KEYS:
                value = summary.get(key)

                if isinstance(value, str):
                    return value

        return None

    def _parse_timestamp(self, value: str) -> datetime | None:
        normalized = value.strip()

        if not normalized:
            return None

        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"

        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None

        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None

        return parsed

    def _file_modified_at(self, path: Path) -> datetime:
        try:
            modified_timestamp = path.stat().st_mtime
        except OSError as exc:
            raise ArtifactLoadError(
                f"unable to read artifact metadata {path}: {exc}"
            ) from exc

        return datetime.fromtimestamp(modified_timestamp, tz=UTC)

    def _extract_schema_version(
        self,
        payload: Mapping[str, JsonValue],
    ) -> str | None:
        direct_version = payload.get("schema_version")

        if isinstance(direct_version, str) and direct_version.strip():
            return direct_version.strip()

        metadata = payload.get("metadata")

        if isinstance(metadata, dict):
            nested_version = metadata.get("schema_version")

            if isinstance(nested_version, str) and nested_version.strip():
                return nested_version.strip()

        return None

    def _build_source_id(
        self,
        path: Path,
        source_type: DashboardSourceType,
        checksum: str,
    ) -> str:
        normalized_stem = "".join(
            character if character.isalnum() else "-" for character in path.stem.lower()
        ).strip("-")
        normalized_stem = normalized_stem or "artifact"

        return f"{source_type.value}-{normalized_stem}-{checksum[:12]}"

    def _normalize_payload(
        self,
        payload: Mapping[str, Any],
    ) -> dict[str, JsonValue]:
        normalized: dict[str, JsonValue] = {}

        for key, value in payload.items():
            normalized[str(key)] = self._normalize_value(value)

        return normalized

    def _normalize_value(self, value: Any) -> JsonValue:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value

        if isinstance(value, Mapping):
            return {
                str(key): self._normalize_value(item) for key, item in value.items()
            }

        if isinstance(value, (list, tuple)):
            return [self._normalize_value(item) for item in value]

        raise ArtifactValidationError(
            f"artifact contains unsupported JSON value: {type(value).__name__}"
        )
