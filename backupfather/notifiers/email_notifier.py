"""Email notifier — short status email, no attachment."""

from __future__ import annotations

import smtplib
from collections.abc import Callable
from email.message import EmailMessage

from backupfather.models import BackupResult
from backupfather.notifiers.base import Notifier
from backupfather.notifiers.messages import format_failure, format_success
from backupfather.utils.logger import get_logger
from backupfather.utils.retry import with_retry

log = get_logger(__name__)

SmtpFactory = Callable[[str, int, float], smtplib.SMTP]


class EmailNotifier(Notifier):
    name = "email"

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        sender: str,
        recipients: str,
        use_tls: bool = True,
        timeout: float = 30.0,
        smtp_factory: SmtpFactory | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self._password = password
        self.sender = sender
        self.recipients = [r.strip() for r in recipients.split(",") if r.strip()]
        self.use_tls = use_tls
        self.timeout = timeout
        self._use_ssl = port == 465
        cls = smtplib.SMTP_SSL if self._use_ssl else smtplib.SMTP
        self._smtp_factory = smtp_factory or (
            lambda host, port, timeout: cls(host, port, timeout=timeout)
        )

    def notify_success(self, result: BackupResult) -> None:
        self._send(f"[backupfather] OK: {result.db_name}", format_success(result))

    def notify_failure(self, result: BackupResult) -> None:
        self._send(f"[backupfather] FAILED: {result.db_name}", format_failure(result))

    def _send(self, subject: str, body: str) -> None:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.sender
        message["To"] = ", ".join(self.recipients)
        message.set_content(body)

        @with_retry(attempts=2, exceptions=(smtplib.SMTPException, OSError))
        def _do() -> None:
            with self._smtp_factory(self.host, self.port, self.timeout) as server:
                if self.use_tls and not self._use_ssl:
                    server.starttls()
                if self.username:
                    server.login(self.username, self._password)
                server.send_message(message)

        _do()
