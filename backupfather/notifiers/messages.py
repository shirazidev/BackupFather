"""Human-readable notification text. No secrets, no stack traces — summaries only."""

from __future__ import annotations

from backupfather.models import BackupResult


def format_success(result: BackupResult) -> str:
    size = f"{result.artifact.size_mb:.2f} MB" if result.artifact else "n/a"
    dests = ", ".join(d.destination for d in result.deliveries if d.ok) or "none"
    return (
        f"✅ Backup OK: {result.db_name}\n"
        f"size: {size}\n"
        f"duration: {result.duration_seconds:.1f}s\n"
        f"destinations: {dests}"
    )


def format_failure(result: BackupResult) -> str:
    step = result.failed_step.value if result.failed_step else "unknown"
    # error_summary is already a short summary — full traces stay in the logs.
    return (
        f"❌ Backup FAILED: {result.db_name}\n"
        f"step: {step}\n"
        f"duration: {result.duration_seconds:.1f}s\n"
        f"error: {result.error_summary[:500]}"
    )
