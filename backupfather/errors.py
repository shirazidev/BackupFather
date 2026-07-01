"""Typed exceptions with distinct process exit codes."""

from __future__ import annotations

# Exit codes: 0 success, 2 config error, 1 generic runtime error.
EXIT_OK = 0
EXIT_RUNTIME = 1
EXIT_CONFIG = 2


class BackupError(Exception):
    """Base class for expected, handled failures."""

    exit_code = EXIT_RUNTIME


class ConfigError(BackupError):
    """Invalid or missing configuration — fail fast at startup."""

    exit_code = EXIT_CONFIG


class SourceError(BackupError):
    """A backup source (e.g. pg_dump) failed."""


class ProcessorError(BackupError):
    """Compression or encryption failed."""


class DeliveryError(BackupError):
    """A destination failed to deliver the artifact."""
