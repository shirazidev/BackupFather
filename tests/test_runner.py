"""Integration tests for BackupRunner error handling (all I/O faked)."""

from __future__ import annotations

from pathlib import Path

import pytest

from backupfather.config import load_settings
from backupfather.destinations.base import BackupDestination
from backupfather.errors import DeliveryError, SourceError
from backupfather.models import BackupArtifact, BackupResult, DeliveryResult, Step
from backupfather.notifiers.base import Notifier
from backupfather.runner import BackupRunner
from backupfather.sources.postgres import PostgresSource


class _RecordingNotifier(Notifier):
    name = "rec"

    def __init__(self) -> None:
        self.successes: list[BackupResult] = []
        self.failures: list[BackupResult] = []

    def notify_success(self, result: BackupResult) -> None:
        self.successes.append(result)

    def notify_failure(self, result: BackupResult) -> None:
        self.failures.append(result)


class _OkDestination(BackupDestination):
    name = "ok"

    def deliver(self, artifact: BackupArtifact, caption: str) -> DeliveryResult:
        return DeliveryResult(destination=self.name, ok=True)


class _BoomDestination(BackupDestination):
    name = "boom"

    def deliver(self, artifact: BackupArtifact, caption: str) -> DeliveryResult:
        raise DeliveryError("carrier pigeon got lost")


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    for key in list(__import__("os").environ):
        if key.startswith(("DATABASES", "DESTINATIONS", "COMPRESSION", "RETENTION", "LOCAL_")):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASES", "main:postgres://u:p@h:5432/db")
    monkeypatch.setenv("COMPRESSION", "none")  # skip gzip for a plain fake dump
    monkeypatch.setenv("LOCAL_BACKUP_DIR", str(tmp_path / "backups"))
    return load_settings()


def _patch_dump(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_dump(self, dest_dir: Path) -> BackupArtifact:
        dest_dir.mkdir(parents=True, exist_ok=True)
        p = dest_dir / "main_2026-07-01T00-00-00Z.dump"
        p.write_bytes(b"fake dump")
        return BackupArtifact(
            db_name=self.db_name, path=p, size_bytes=p.stat().st_size, created_at="t"
        )

    monkeypatch.setattr(PostgresSource, "dump", fake_dump)


def test_success_path_notifies_success(monkeypatch, settings, tmp_path):  # noqa: ANN001
    _patch_dump(monkeypatch, tmp_path)
    notifier = _RecordingNotifier()
    runner = BackupRunner(settings, [_OkDestination()], [notifier])

    results = runner.run_all()

    assert results[0].ok
    assert len(notifier.successes) == 1 and not notifier.failures


def test_dump_failure_notifies_failure_with_step(monkeypatch, settings, tmp_path):  # noqa: ANN001
    def boom(self, dest_dir):  # noqa: ANN001
        raise SourceError("pg_dump exited 1: role does not exist")

    monkeypatch.setattr(PostgresSource, "dump", boom)
    notifier = _RecordingNotifier()
    runner = BackupRunner(settings, [_OkDestination()], [notifier])

    result = runner.run_all()[0]

    assert not result.ok
    assert result.failed_step is Step.DUMP
    assert notifier.failures and "role does not exist" in notifier.failures[0].error_summary


def test_delivery_failure_marks_run_failed_but_continues(
    monkeypatch, settings, tmp_path
):  # noqa: ANN001
    _patch_dump(monkeypatch, tmp_path)
    notifier = _RecordingNotifier()
    # One destination blows up, the other succeeds — both must be attempted.
    runner = BackupRunner(settings, [_BoomDestination(), _OkDestination()], [notifier])

    result = runner.run_all()[0]

    assert not result.ok
    assert result.failed_step is Step.DELIVER
    assert {d.destination: d.ok for d in result.deliveries} == {"boom": False, "ok": True}
    assert notifier.failures


def test_notifier_exception_never_masks_result(monkeypatch, settings, tmp_path):  # noqa: ANN001
    _patch_dump(monkeypatch, tmp_path)

    class _BadNotifier(Notifier):
        name = "bad"

        def notify_success(self, result: BackupResult) -> None:
            raise RuntimeError("notifier down")

        def notify_failure(self, result: BackupResult) -> None:
            raise RuntimeError("notifier down")

    runner = BackupRunner(settings, [_OkDestination()], [_BadNotifier()])
    result = runner.run_all()[0]  # must not raise
    assert result.ok
