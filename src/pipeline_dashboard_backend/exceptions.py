"""Custom exceptions for the Pipeline Dashboard Backend."""


class DashboardBackendError(Exception):
    """Base exception for dashboard backend failures."""


class ArtifactLoadError(DashboardBackendError):
    """Raised when an observability artifact cannot be loaded."""


class ArtifactValidationError(DashboardBackendError):
    """Raised when an observability artifact has invalid content."""


class UnsupportedArtifactError(DashboardBackendError):
    """Raised when the artifact type cannot be identified or supported."""
