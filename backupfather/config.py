"""Environment-driven configuration with fail-fast validation (pydantic).

All settings are loaded from environment variables (or a `.env` file). Invalid
or missing required configuration raises :class:`ConfigError` at startup so the
app never fails mid-backup.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from backupfather.errors import ConfigError


class DumpFormat(StrEnum):
    custom = "custom"
    plain = "plain"
    directory = "directory"


class Compression(StrEnum):
    gzip = "gzip"
    zstd = "zstd"
    none = "none"


class EncryptionMethod(StrEnum):
    gpg = "gpg"
    aes = "aes"


class DatabaseConfig(BaseSettings):
    """A single database to back up."""

    name: str
    dsn: SecretStr

    @field_validator("name")
    @classmethod
    def _safe_name(cls, v: str) -> str:
        v = v.strip()
        if not v or not all(c.isalnum() or c in "-_" for c in v):
            raise ValueError(f"database name {v!r} must be non-empty and alphanumeric/-/_ only")
        return v


def _parse_databases(raw: str) -> list[DatabaseConfig]:
    """Parse ``name:dsn,name:dsn`` into DatabaseConfig list.

    DSNs contain commas rarely but colons always (``postgres://``), so we split
    on the first colon per entry and split entries on commas that are not inside
    a DSN. Entries are comma-separated; DSNs must not contain a bare comma.
    """
    databases: list[DatabaseConfig] = []
    for entry in (e.strip() for e in raw.split(",")):
        if not entry:
            continue
        name, sep, dsn = entry.partition(":")
        if not sep or not dsn:
            raise ValueError(f"invalid DATABASES entry {entry!r}; expected 'name:dsn'")
        databases.append(DatabaseConfig(name=name.strip(), dsn=dsn.strip()))
    return databases


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # --- Source ---
    databases_raw: str = Field(default="", alias="DATABASES")
    pg_dump_format: DumpFormat = Field(default=DumpFormat.custom, alias="PG_DUMP_FORMAT")

    # --- Scheduling ---
    scheduler_enabled: bool = Field(default=True, alias="SCHEDULER_ENABLED")
    backup_cron: str = Field(default="0 3 * * *", alias="BACKUP_CRON")

    # --- Compression / encryption ---
    compression: Compression = Field(default=Compression.gzip, alias="COMPRESSION")
    compression_level: int = Field(default=6, ge=1, le=22, alias="COMPRESSION_LEVEL")
    encryption_enabled: bool = Field(default=False, alias="ENCRYPTION_ENABLED")
    encryption_method: EncryptionMethod = Field(
        default=EncryptionMethod.gpg, alias="ENCRYPTION_METHOD"
    )
    gpg_recipient: str = Field(default="", alias="GPG_RECIPIENT")
    aes_passphrase: SecretStr = Field(default=SecretStr(""), alias="AES_PASSPHRASE")

    # --- Destinations ---
    destinations_raw: str = Field(default="", alias="DESTINATIONS")
    telegram_bot_token: SecretStr = Field(default=SecretStr(""), alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")
    bale_bot_token: SecretStr = Field(default=SecretStr(""), alias="BALE_BOT_TOKEN")
    bale_chat_id: str = Field(default="", alias="BALE_CHAT_ID")

    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_user: str = Field(default="", alias="SMTP_USER")
    smtp_password: SecretStr = Field(default=SecretStr(""), alias="SMTP_PASSWORD")
    smtp_from: str = Field(default="", alias="SMTP_FROM")
    smtp_to: str = Field(default="", alias="SMTP_TO")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")
    smtp_max_attachment_mb: int = Field(default=20, ge=1, alias="SMTP_MAX_ATTACHMENT_MB")

    # --- Notifications ---
    notify_on_success: bool = Field(default=True, alias="NOTIFY_ON_SUCCESS")
    notify_on_failure: bool = Field(default=True, alias="NOTIFY_ON_FAILURE")
    notifier_telegram_chat_id: str = Field(default="", alias="NOTIFIER_TELEGRAM_CHAT_ID")
    notifier_email_enabled: bool = Field(default=False, alias="NOTIFIER_EMAIL_ENABLED")

    # --- Retention ---
    retention_days: int | None = Field(default=14, ge=0, alias="RETENTION_DAYS")
    retention_count: int | None = Field(default=None, ge=1, alias="RETENTION_COUNT")

    # --- Storage ---
    local_backup_dir: str = Field(default="/backups", alias="LOCAL_BACKUP_DIR")

    # --- Logging / health ---
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: str = Field(default="text", alias="LOG_FORMAT")
    healthcheck_enabled: bool = Field(default=True, alias="HEALTHCHECK_ENABLED")
    healthcheck_port: int = Field(default=8080, alias="HEALTHCHECK_PORT")

    # Telegram/Bale bot API upload limit (MB). Bale is typically lower.
    telegram_max_upload_mb: int = Field(default=50, alias="TELEGRAM_MAX_UPLOAD_MB")
    bale_max_upload_mb: int = Field(default=50, alias="BALE_MAX_UPLOAD_MB")

    @field_validator("destinations_raw")
    @classmethod
    def _normalize_destinations(cls, v: str) -> str:
        return v.strip()

    @property
    def databases(self) -> list[DatabaseConfig]:
        return _parse_databases(self.databases_raw)

    @property
    def destinations(self) -> list[str]:
        return [d.strip().lower() for d in self.destinations_raw.split(",") if d.strip()]

    @model_validator(mode="after")
    def _cross_field_validation(self) -> Settings:
        if not self.databases:
            raise ValueError("DATABASES must define at least one 'name:dsn' entry")

        known = {"telegram", "bale", "email", "local"}
        for dest in self.destinations:
            if dest not in known:
                raise ValueError(f"unknown destination {dest!r}; known: {sorted(known)}")

        if "telegram" in self.destinations and not (
            self.telegram_bot_token.get_secret_value() and self.telegram_chat_id
        ):
            raise ValueError(
                "telegram destination requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID"
            )
        if "bale" in self.destinations and not (
            self.bale_bot_token.get_secret_value() and self.bale_chat_id
        ):
            raise ValueError("bale destination requires BALE_BOT_TOKEN and BALE_CHAT_ID")
        if "email" in self.destinations and not (
            self.smtp_host and self.smtp_from and self.smtp_to
        ):
            raise ValueError("email destination requires SMTP_HOST, SMTP_FROM and SMTP_TO")

        if self.encryption_enabled:
            if self.encryption_method is EncryptionMethod.gpg and not self.gpg_recipient:
                raise ValueError("ENCRYPTION_METHOD=gpg requires GPG_RECIPIENT")
            if (
                self.encryption_method is EncryptionMethod.aes
                and not self.aes_passphrase.get_secret_value()
            ):
                raise ValueError("ENCRYPTION_METHOD=aes requires AES_PASSPHRASE")

        if self.compression is Compression.gzip and self.compression_level > 9:
            raise ValueError("gzip COMPRESSION_LEVEL must be between 1 and 9")

        return self


def load_settings() -> Settings:
    """Load and validate settings, converting pydantic errors to ConfigError."""
    try:
        return Settings()
    except (ValidationError, ValueError) as exc:
        raise ConfigError(f"invalid configuration:\n{exc}") from exc
