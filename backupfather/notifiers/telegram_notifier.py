"""Telegram notifier — short status messages, independent of delivery."""

from __future__ import annotations

from backupfather.destinations.bot_api import BotApiClient
from backupfather.destinations.telegram import TELEGRAM_BASE_URL
from backupfather.models import BackupResult
from backupfather.notifiers.base import Notifier
from backupfather.notifiers.messages import format_failure, format_success
from backupfather.utils.logger import get_logger

log = get_logger(__name__)


class TelegramNotifier(Notifier):
    name = "telegram"

    def __init__(self, *, token: str, chat_id: str, base_url: str = TELEGRAM_BASE_URL) -> None:
        self._client = BotApiClient(base_url=base_url, token=token, chat_id=chat_id)

    def notify_success(self, result: BackupResult) -> None:
        self._client.send_message(format_success(result))

    def notify_failure(self, result: BackupResult) -> None:
        self._client.send_message(format_failure(result))
