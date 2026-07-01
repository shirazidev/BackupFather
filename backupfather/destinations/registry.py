"""Build the configured destination objects from settings.

New destinations are registered in ``_BUILDERS`` — the runner and CLI never need
to change when a destination is added (Open/Closed principle).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from backupfather.config import Settings
from backupfather.destinations.bale import BaleDestination
from backupfather.destinations.base import BackupDestination
from backupfather.destinations.email_smtp import EmailDestination
from backupfather.destinations.local import LocalDestination
from backupfather.destinations.telegram import TelegramDestination
from backupfather.utils.logger import get_logger

log = get_logger(__name__)

Builder = Callable[[Settings], BackupDestination]


def _build_local(settings: Settings) -> BackupDestination:
    return LocalDestination(Path(settings.local_backup_dir))


def _build_telegram(settings: Settings) -> BackupDestination:
    return TelegramDestination(
        token=settings.telegram_bot_token.get_secret_value(),
        chat_id=settings.telegram_chat_id,
        max_upload_mb=settings.telegram_max_upload_mb,
    )


def _build_bale(settings: Settings) -> BackupDestination:
    return BaleDestination(
        token=settings.bale_bot_token.get_secret_value(),
        chat_id=settings.bale_chat_id,
        max_upload_mb=settings.bale_max_upload_mb,
    )


def _build_email(settings: Settings) -> BackupDestination:
    return EmailDestination(
        host=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user,
        password=settings.smtp_password.get_secret_value(),
        sender=settings.smtp_from,
        recipients=settings.smtp_to,
        use_tls=settings.smtp_use_tls,
        max_attachment_mb=settings.smtp_max_attachment_mb,
    )


_BUILDERS: dict[str, Builder] = {
    "local": _build_local,
    "telegram": _build_telegram,
    "bale": _build_bale,
    "email": _build_email,
}


def register(name: str, builder: Builder) -> None:
    _BUILDERS[name] = builder


def build_destinations(settings: Settings) -> list[BackupDestination]:
    destinations: list[BackupDestination] = []
    for name in settings.destinations:
        builder = _BUILDERS.get(name)
        if builder is None:
            log.warning("no builder registered for destination %r; skipping", name)
            continue
        destinations.append(builder(settings))
    if not destinations:
        log.warning("no destinations configured; backups will only stay in local dir")
        destinations.append(_build_local(settings))
    return destinations
