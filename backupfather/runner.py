"""BackupRunner — orchestrates dump -> process -> deliver -> notify per database.

Depends only on abstractions (BackupSource/BackupProcessor/BackupDestination/
Notifier), wired in from the CLI. Each database is independent: one failing does
not abort the others.
"""

from __future__ import annotations

import time
from pathlib import Path

from backupfather.config import DatabaseConfig, Settings
from backupfather.destinations.base import BackupDestination
from backupfather.errors import BackupError
from backupfather.health import HealthState
from backupfather.models import BackupArtifact, BackupResult, DeliveryResult, Step
from backupfather.notifiers.base import Notifier
from backupfather.processors.base import BackupProcessor
from backupfather.processors.factory import build_processors
from backupfather.retention import apply_retention
from backupfather.sources.postgres import PostgresSource
from backupfather.utils.logger import get_logger

log = get_logger(__name__)


class BackupRunner:
    def __init__(
        self,
        settings: Settings,
        destinations: list[BackupDestination],
        notifiers: list[Notifier],
        health_state: HealthState | None = None,
    ) -> None:
        self.settings = settings
        self.destinations = destinations
        self.notifiers = notifiers
        self.health_state = health_state
        self.backup_dir = Path(settings.local_backup_dir)

    def run_all(self) -> list[BackupResult]:
        results = [self._run_one(db) for db in self.settings.databases]
        return results

    def _run_one(self, db: DatabaseConfig) -> BackupResult:
        started = time.monotonic()
        step = Step.DUMP
        artifact: BackupArtifact | None = None
        try:
            source = PostgresSource(
                db_name=db.name,
                dsn=db.dsn.get_secret_value(),
                dump_format=self.settings.pg_dump_format,
            )
            artifact = source.dump(self.backup_dir)

            step = Step.COMPRESS
            artifact = self._apply_processors(artifact, build_processors(self.settings))

            step = Step.DELIVER
            deliveries = self._deliver(artifact)

            step = Step.RETENTION
            self._apply_retention(db.name)

            duration = time.monotonic() - started
            result = BackupResult(
                db_name=db.name,
                ok=all(d.ok for d in deliveries) if deliveries else True,
                duration_seconds=duration,
                artifact=artifact,
                deliveries=deliveries,
            )
            if not result.ok:
                result.failed_step = Step.DELIVER
                result.error_summary = "; ".join(
                    f"{d.destination}: {d.detail}" for d in deliveries if not d.ok
                )
        except BackupError as exc:
            duration = time.monotonic() - started
            log.error("backup failed for %s at step %s: %s", db.name, step.value, exc)
            result = BackupResult(
                db_name=db.name,
                ok=False,
                duration_seconds=duration,
                artifact=artifact,
                failed_step=step,
                error_summary=str(exc),
            )
        except Exception as exc:  # unexpected — log full trace, still notify
            duration = time.monotonic() - started
            log.exception("unexpected error backing up %s", db.name)
            result = BackupResult(
                db_name=db.name,
                ok=False,
                duration_seconds=duration,
                artifact=artifact,
                failed_step=step,
                error_summary=f"unexpected {type(exc).__name__}: {exc}",
            )

        if self.health_state is not None:
            self.health_state.record(result)
        self._notify(result)
        return result

    def _apply_retention(self, db_name: str) -> None:
        apply_retention(
            self.backup_dir,
            db_name,
            retention_days=self.settings.retention_days,
            retention_count=self.settings.retention_count,
        )

    def _apply_processors(
        self, artifact: BackupArtifact, processors: list[BackupProcessor]
    ) -> BackupArtifact:
        for proc in processors:
            artifact = proc.process(artifact)
        return artifact

    def _deliver(self, artifact: BackupArtifact) -> list[DeliveryResult]:
        caption = self._caption(artifact)
        results: list[DeliveryResult] = []
        for dest in self.destinations:
            try:
                results.append(dest.deliver(artifact, caption))
            except BackupError as exc:
                log.error("delivery to %s failed: %s", dest.name, exc)
                results.append(DeliveryResult(destination=dest.name, ok=False, detail=str(exc)))
        return results

    def _caption(self, artifact: BackupArtifact) -> str:
        return (
            f"✅ {artifact.db_name} backup\n"
            f"size: {artifact.size_mb:.2f} MB\n"
            f"file: {artifact.path.name}\n"
            f"created: {artifact.created_at}"
        )

    def _notify(self, result: BackupResult) -> None:
        settings = self.settings
        if result.ok and not settings.notify_on_success:
            return
        if not result.ok and not settings.notify_on_failure:
            return
        for notifier in self.notifiers:
            try:
                if result.ok:
                    notifier.notify_success(result)
                else:
                    notifier.notify_failure(result)
            except Exception:  # never let notification failure mask backup outcome
                log.exception("notifier %s failed", notifier.name)
