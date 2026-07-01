"""Tests for the notifier layer (message formatting + wiring)."""

from __future__ import annotations

from pathlib import Path

import pytest

from backupfather.config import load_settings
from backupfather.destinations.bot_api import BotApiClient
from backupfather.models import BackupArtifact, BackupResult, DeliveryResult, Step
from backupfather.notifiers.messages import format_failure, format_success
from backupfather.notifiers.registry import build_notifiers
from backupfather.notifiers.telegram_notifier import TelegramNotifier


def _ok_result() -> BackupResult:
    art = BackupArtifact(
        db_name="main", path=Path("/x/main.dump.gz"), size_bytes=2_500_000, created_at="t"
    )
    return BackupResult(
        db_name="main",
        ok=True,
        duration_seconds=3.2,
        artifact=art,
        deliveries=[DeliveryResult("telegram", True), DeliveryResult("email", True)],
    )


def _fail_result() -> BackupResult:
    return BackupResult(
        db_name="main",
        ok=False,
        duration_seconds=1.0,
        failed_step=Step.DUMP,
        error_summary="pg_dump exited 1: role does not exist",
    )


def test_success_message_lists_destinations() -> None:
    msg = format_success(_ok_result())
    assert "Backup OK: main" in msg
    assert "telegram" in msg and "email" in msg
    assert "2.38 MB" in msg


def test_failure_message_has_step_and_no_trace() -> None:
    msg = format_failure(_fail_result())
    assert "FAILED: main" in msg
    assert "dump" in msg
    assert "role does not exist" in msg
    assert "Traceback" not in msg


def test_telegram_notifier_sends(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[str] = []
    monkeypatch.setattr(BotApiClient, "send_message", lambda self, text: sent.append(text))
    TelegramNotifier(token="t", chat_id="9").notify_failure(_fail_result())
    assert sent and "FAILED" in sent[0]


@pytest.mark.usefixtures("clean_env")
def test_registry_builds_telegram_notifier_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASES", "main:postgres://u:p@h:5432/db")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("NOTIFIER_TELEGRAM_CHAT_ID", "9")
    notifiers = build_notifiers(load_settings())
    assert [n.name for n in notifiers] == ["telegram"]


@pytest.mark.usefixtures("clean_env")
def test_registry_no_notifiers_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASES", "main:postgres://u:p@h:5432/db")
    assert build_notifiers(load_settings()) == []
