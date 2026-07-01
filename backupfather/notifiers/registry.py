"""Build the configured notifier objects from settings (phase 6 populates it)."""

from __future__ import annotations

from collections.abc import Callable

from backupfather.config import Settings
from backupfather.notifiers.base import Notifier
from backupfather.notifiers.email_notifier import EmailNotifier
from backupfather.notifiers.telegram_notifier import TelegramNotifier
from backupfather.utils.logger import get_logger

log = get_logger(__name__)

Builder = Callable[[Settings], Notifier | None]


def _build_telegram_notifier(settings: Settings) -> Notifier | None:
    token = settings.telegram_bot_token.get_secret_value()
    chat_id = settings.notifier_telegram_chat_id
    if not (token and chat_id):
        return None
    return TelegramNotifier(token=token, chat_id=chat_id)


def _build_email_notifier(settings: Settings) -> Notifier | None:
    if not settings.notifier_email_enabled:
        return None
    if not (settings.smtp_host and settings.smtp_from and settings.smtp_to):
        log.warning("NOTIFIER_EMAIL_ENABLED set but SMTP is not fully configured; skipping")
        return None
    return EmailNotifier(
        host=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user,
        password=settings.smtp_password.get_secret_value(),
        sender=settings.smtp_from,
        recipients=settings.smtp_to,
        use_tls=settings.smtp_use_tls,
    )


_BUILDERS: list[Builder] = [_build_telegram_notifier, _build_email_notifier]


def register(builder: Builder) -> None:
    _BUILDERS.append(builder)


def build_notifiers(settings: Settings) -> list[Notifier]:
    notifiers: list[Notifier] = []
    for builder in _BUILDERS:
        notifier = builder(settings)
        if notifier is not None:
            notifiers.append(notifier)
    return notifiers
