"""Tests for the Email/SMTP destination (SMTP mocked)."""

from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path

import pytest

from backupfather.destinations.email_smtp import EmailDestination
from backupfather.errors import DeliveryError
from backupfather.models import BackupArtifact


class _FakeSMTP:
    instances: list[_FakeSMTP] = []

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host = host
        self.port = port
        self.started_tls = False
        self.logged_in: tuple[str, str] | None = None
        self.sent: list[EmailMessage] = []
        _FakeSMTP.instances.append(self)

    def __enter__(self) -> _FakeSMTP:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def starttls(self) -> None:
        self.started_tls = True

    def login(self, user: str, password: str) -> None:
        self.logged_in = (user, password)

    def send_message(self, message: EmailMessage) -> None:
        self.sent.append(message)


def _artifact(path: Path, size: int) -> BackupArtifact:
    return BackupArtifact(
        db_name="db", path=path, size_bytes=size, created_at="2026-07-01T00:00:00Z"
    )


def _dest(tmp_path: Path, **kw: object) -> EmailDestination:
    defaults: dict[str, object] = {
        "host": "smtp.example.com",
        "port": 587,
        "username": "user",
        "password": "pass",
        "sender": "from@example.com",
        "recipients": "a@example.com, b@example.com",
        "use_tls": True,
        "max_attachment_mb": 1,
        "smtp_factory": lambda host, port, timeout: _FakeSMTP(host, port, timeout),
    }
    defaults.update(kw)
    return EmailDestination(**defaults)  # type: ignore[arg-type]


def setup_function() -> None:
    _FakeSMTP.instances.clear()


def test_email_sends_with_attachment(tmp_path: Path) -> None:
    f = tmp_path / "db.dump.gz"
    f.write_bytes(b"small")
    result = _dest(tmp_path).deliver(_artifact(f, 5), "caption body")

    assert result.ok
    server = _FakeSMTP.instances[-1]
    assert server.started_tls
    assert server.logged_in == ("user", "pass")
    msg = server.sent[0]
    assert msg["To"] == "a@example.com, b@example.com"
    attachments = [p for p in msg.iter_attachments()]
    assert attachments[0].get_filename() == "db.dump.gz"


def test_email_skips_oversized(tmp_path: Path) -> None:
    f = tmp_path / "big.dump.gz"
    f.write_bytes(b"x")
    result = _dest(tmp_path, max_attachment_mb=1).deliver(_artifact(f, 5 * 1024 * 1024), "cap")
    assert not result.ok
    assert "over" in result.detail
    assert _FakeSMTP.instances == []  # never connected


def test_email_auth_failure_raises(tmp_path: Path) -> None:
    import smtplib

    def bad_factory(host, port, timeout):  # noqa: ANN001, ANN003
        class Boom(_FakeSMTP):
            def login(self, user: str, password: str) -> None:
                raise smtplib.SMTPAuthenticationError(535, b"bad creds")

        return Boom(host, port, timeout)

    f = tmp_path / "db.dump.gz"
    f.write_bytes(b"data")
    with pytest.raises(DeliveryError, match="authentication failed"):
        _dest(tmp_path, smtp_factory=bad_factory).deliver(_artifact(f, 4), "cap")
