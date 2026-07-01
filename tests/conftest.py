"""Shared pytest fixtures."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Strip every env var the app reads so tests are hermetic.

    Also disables .env file loading so a developer's local .env can't leak in.
    """
    prefixes = (
        "DATABASES",
        "PG_",
        "SCHEDULER_",
        "BACKUP_",
        "COMPRESSION",
        "ENCRYPTION_",
        "GPG_",
        "AES_",
        "DESTINATIONS",
        "TELEGRAM_",
        "BALE_",
        "SMTP_",
        "NOTIFY_",
        "NOTIFIER_",
        "RETENTION_",
        "LOCAL_",
        "LOG_",
        "HEALTHCHECK_",
    )
    for key in list(os.environ):
        if key.startswith(prefixes):
            monkeypatch.delenv(key, raising=False)
    # Point pydantic-settings at a non-existent env file.
    monkeypatch.chdir(os.path.dirname(__file__))
    yield
