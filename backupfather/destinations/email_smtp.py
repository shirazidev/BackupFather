"""Email (SMTP) destination — sends the backup as an attachment.

Large files are skipped with a clear failure result rather than silently
dropped or bouncing off the mail server. If a storage destination is also
configured, the operator should rely on that for oversized dumps (documented in
the README).
"""

from __future__ import annotations

import smtplib
from collections.abc import Callable
from email.message import EmailMessage

from backupfather.destinations.base import BackupDestination
from backupfather.errors import DeliveryError
from backupfather.models import BackupArtifact, DeliveryResult
from backupfather.utils.logger import get_logger
from backupfather.utils.retry import with_retry

log = get_logger(__name__)

SmtpFactory = Callable[[str, int, float], smtplib.SMTP]


def _default_smtp_factory(use_ssl: bool) -> SmtpFactory:
    cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    return lambda host, port, timeout: cls(host, port, timeout=timeout)


class EmailDestination(BackupDestination):
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
        max_attachment_mb: int = 20,
        timeout: float = 60.0,
        smtp_factory: SmtpFactory | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self._password = password
        self.sender = sender
        self.recipients = [r.strip() for r in recipients.split(",") if r.strip()]
        self.use_tls = use_tls
        self.max_attachment_bytes = max_attachment_mb * 1024 * 1024
        self.timeout = timeout
        # Port 465 implies implicit SSL; otherwise STARTTLS when use_tls is set.
        self._use_ssl = port == 465
        self._smtp_factory = smtp_factory or _default_smtp_factory(self._use_ssl)

    def deliver(self, artifact: BackupArtifact, caption: str) -> DeliveryResult:
        if artifact.size_bytes > self.max_attachment_bytes:
            msg = (
                f"{artifact.path.name} is {artifact.size_mb:.1f} MB, over the "
                f"{self.max_attachment_bytes // (1024 * 1024)} MB email limit; skipped"
            )
            log.warning("%s: %s", self.name, msg)
            return DeliveryResult(destination=self.name, ok=False, detail=msg)

        message = self._build_message(artifact, caption)
        self._send(message)
        log.info("%s: emailed %s to %s", self.name, artifact.path.name, ", ".join(self.recipients))
        return DeliveryResult(destination=self.name, ok=True, detail="sent")

    def _build_message(self, artifact: BackupArtifact, caption: str) -> EmailMessage:
        message = EmailMessage()
        message["Subject"] = f"[backupfather] {artifact.db_name} backup {artifact.created_at}"
        message["From"] = self.sender
        message["To"] = ", ".join(self.recipients)
        message.set_content(caption or f"Backup for {artifact.db_name} attached.")
        data = artifact.path.read_bytes()
        message.add_attachment(
            data,
            maintype="application",
            subtype="octet-stream",
            filename=artifact.path.name,
        )
        return message

    def _send(self, message: EmailMessage) -> None:
        @with_retry(attempts=3, exceptions=(smtplib.SMTPException, OSError))
        def _do() -> None:
            try:
                with self._smtp_factory(self.host, self.port, self.timeout) as server:
                    if self.use_tls and not self._use_ssl:
                        server.starttls()
                    if self.username:
                        server.login(self.username, self._password)
                    server.send_message(message)
            except smtplib.SMTPAuthenticationError as exc:
                # Bad creds won't fix themselves — don't waste retries.
                raise DeliveryError("SMTP authentication failed (check credentials)") from exc

        try:
            _do()
        except DeliveryError:
            raise
        except (smtplib.SMTPException, OSError) as exc:
            raise DeliveryError(f"SMTP send failed: {exc}") from exc
