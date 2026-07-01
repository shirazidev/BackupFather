"""Tests for configuration loading and fail-fast validation."""

from __future__ import annotations

import pytest

from backupfather.config import Compression, DumpFormat, load_settings
from backupfather.errors import ConfigError

pytestmark = pytest.mark.usefixtures("clean_env")


def _base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASES", "main:postgres://u:p@h:5432/db")


def test_minimal_valid_config(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_env(monkeypatch)
    settings = load_settings()
    assert [d.name for d in settings.databases] == ["main"]
    assert settings.pg_dump_format is DumpFormat.custom
    assert settings.compression is Compression.gzip


def test_missing_databases_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ConfigError):
        load_settings()


def test_multiple_databases_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASES",
        "main:postgres://u:p@h:5432/a, secondary:postgres://u:p@h:5432/b",
    )
    settings = load_settings()
    assert [d.name for d in settings.databases] == ["main", "secondary"]
    # DSN is a secret and must not leak via repr.
    assert "postgres://" not in repr(settings.databases[0].dsn)


def test_bad_database_entry_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASES", "no-dsn-here")
    with pytest.raises(ConfigError):
        load_settings()


def test_unknown_destination_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_env(monkeypatch)
    monkeypatch.setenv("DESTINATIONS", "carrier-pigeon")
    with pytest.raises(ConfigError):
        load_settings()


def test_telegram_requires_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_env(monkeypatch)
    monkeypatch.setenv("DESTINATIONS", "telegram")
    with pytest.raises(ConfigError):
        load_settings()


def test_telegram_valid_with_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_env(monkeypatch)
    monkeypatch.setenv("DESTINATIONS", "telegram")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    settings = load_settings()
    assert settings.destinations == ["telegram"]


def test_email_requires_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_env(monkeypatch)
    monkeypatch.setenv("DESTINATIONS", "email")
    with pytest.raises(ConfigError):
        load_settings()


def test_gpg_encryption_requires_recipient(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_env(monkeypatch)
    monkeypatch.setenv("ENCRYPTION_ENABLED", "true")
    monkeypatch.setenv("ENCRYPTION_METHOD", "gpg")
    with pytest.raises(ConfigError):
        load_settings()


def test_aes_encryption_requires_passphrase(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_env(monkeypatch)
    monkeypatch.setenv("ENCRYPTION_ENABLED", "true")
    monkeypatch.setenv("ENCRYPTION_METHOD", "aes")
    with pytest.raises(ConfigError):
        load_settings()


def test_gzip_level_upper_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_env(monkeypatch)
    monkeypatch.setenv("COMPRESSION", "gzip")
    monkeypatch.setenv("COMPRESSION_LEVEL", "15")
    with pytest.raises(ConfigError):
        load_settings()


def test_invalid_db_name_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASES", "bad name:postgres://u:p@h:5432/db")
    with pytest.raises(ConfigError):
        load_settings()
