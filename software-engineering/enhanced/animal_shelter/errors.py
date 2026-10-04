"""Stable, application-facing errors; messages never include driver details."""

class ShelterError(Exception):
    """Base exception callers may handle at the application boundary."""

class ConfigurationError(ShelterError):
    """Missing or invalid connection configuration."""

class ValidationError(ShelterError):
    """Input violates the service contract."""

class RepositoryError(ShelterError):
    """A database operation failed; this is not an empty result."""

class ResourceClosedError(ShelterError):
    """An operation was attempted after the service or repository closed."""
