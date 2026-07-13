from importlib.metadata import (
    PackageNotFoundError,
    metadata,
    version,
)
from pathlib import Path

import pipeline_dashboard_backend


def test_installed_distribution_version() -> None:
    assert version("pipeline-dashboard-backend") == "0.1.0"


def test_package_version_matches_distribution() -> None:
    assert pipeline_dashboard_backend.__version__ == version(
        "pipeline-dashboard-backend"
    )


def test_distribution_metadata() -> None:
    package_metadata = metadata(
        "pipeline-dashboard-backend"
    )

    assert package_metadata["Name"] == (
        "pipeline-dashboard-backend"
    )
    assert package_metadata["Version"] == "0.1.0"
    assert package_metadata["Requires-Python"] == ">=3.11"


def test_readme_exists() -> None:
    assert Path("README.md").is_file()


def test_release_notes_exist() -> None:
    assert Path("RELEASE_NOTES.md").is_file()


def test_typed_package_marker_exists() -> None:
    marker = (
        Path("src")
        / "pipeline_dashboard_backend"
        / "py.typed"
    )

    assert marker.is_file()


def test_distribution_is_installed() -> None:
    try:
        installed_version = version(
            "pipeline-dashboard-backend"
        )
    except PackageNotFoundError as exc:
        raise AssertionError(
            "pipeline-dashboard-backend distribution "
            "is not installed"
        ) from exc

    assert installed_version == "0.1.0"
