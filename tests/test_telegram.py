"""Tests for the Telegram destination and bot-API client (HTTP mocked)."""

from __future__ import annotations

from pathlib import Path

import pytest
import requests

from backupfather.destinations.bot_api import BotApiClient
from backupfather.destinations.telegram import TelegramDestination
from backupfather.errors import DeliveryError
from backupfather.models import BackupArtifact


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload


def _artifact(path: Path, size: int) -> BackupArtifact:
    return BackupArtifact(
        db_name="db", path=path, size_bytes=size, created_at="2026-07-01T00:00:00Z"
    )


def test_bot_client_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    f = tmp_path / "db.dump.gz"
    f.write_bytes(b"data")
    captured: dict = {}

    def fake_post(url, data, files, timeout):  # noqa: ANN001, ANN003
        captured["url"] = url
        captured["data"] = data
        return _FakeResponse(200, {"ok": True, "result": {"message_id": 1}})

    monkeypatch.setattr(requests, "post", fake_post)
    client = BotApiClient(base_url="https://api.telegram.org", token="SECRET", chat_id="42")
    client.send_document(f, caption="hi")

    assert captured["data"]["chat_id"] == "42"
    assert captured["data"]["caption"] == "hi"
    assert "botSECRET" in captured["url"]  # token embedded in URL, not logged


def test_bot_client_api_error_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    f = tmp_path / "db.dump.gz"
    f.write_bytes(b"data")

    def fake_post(url, data, files, timeout):  # noqa: ANN001, ANN003
        return _FakeResponse(400, {"ok": False, "description": "chat not found"})

    monkeypatch.setattr(requests, "post", fake_post)
    client = BotApiClient(base_url="https://api.telegram.org", token="x", chat_id="42", attempts=1)
    with pytest.raises(DeliveryError, match="chat not found"):
        client.send_document(f)


def test_telegram_small_file_single_send(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    f = tmp_path / "db.dump.gz"
    f.write_bytes(b"x" * 10)
    calls: list[Path] = []

    monkeypatch.setattr(
        BotApiClient, "send_document", lambda self, path, caption="": calls.append(path)
    )
    dest = TelegramDestination(token="t", chat_id="42", max_upload_mb=50)
    result = dest.deliver(_artifact(f, 10), "caption")

    assert result.ok
    assert calls == [f]


def test_telegram_oversized_file_is_chunked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = tmp_path / "db.dump.gz"
    f.write_bytes(b"y" * 2500)
    sent: list[str] = []

    def fake_send(self, path, caption=""):  # noqa: ANN001, ANN003
        sent.append(caption)

    monkeypatch.setattr(BotApiClient, "send_document", fake_send)
    # 1 MB max would be one part; force tiny limit via bytes attribute.
    dest = TelegramDestination(token="t", chat_id="42", max_upload_mb=50)
    dest.max_upload_bytes = 1000  # 3 parts for 2500 bytes
    result = dest.deliver(_artifact(f, 2500), "cap")

    assert result.ok
    assert len(sent) == 3
    assert "part 1/3" in sent[0] and "part 3/3" in sent[2]
    # Part files cleaned up.
    assert list(tmp_path.glob("*.part*")) == []
